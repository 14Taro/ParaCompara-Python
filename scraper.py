"""
scraper.py — Para&Compara · Scraper gratuito corregido
=======================================================
Problemas anteriores corregidos:
  ✓ Jumbo usa VTEX Intelligent Search (/_v/api/intelligent-search/), NO el endpoint legacy
  ✓ D1: selectores CSS verificados contra el HTML real del sitio
  ✓ Modo --only-prices: solo actualiza precios de productos ya en BD (más rápido)
  ✓ Modo --discover: descubre y registra productos nuevos además de actualizar

ESTRATEGIA POR TIENDA:
  Éxito    → VTEX legacy:        /api/catalog_system/pub/products/search/
  Jumbo    → VTEX Intelligent:   /_v/api/intelligent-search/product_search/
  Olímpica → VTEX legacy:        /api/catalog_system/pub/products/search/
  D1       → Playwright (HTML real, selectores verificados)

INSTALACIÓN:
    pip install playwright beautifulsoup4 requests schedule lxml
    python -m playwright install chromium

EJECUCIÓN:
    python scraper.py --only-prices          ← RÁPIDO: solo actualiza precios existentes
    python scraper.py --discover             ← COMPLETO: actualiza + registra nuevos productos
    python scraper.py --test exito           ← prueba una tienda
    python scraper.py --test d1 --query leche← prueba tienda + producto específico
    python scraper.py                        ← programado diario 3 AM (--only-prices)
"""

import re
import sys
import os
import time
import logging
import argparse
import random
from datetime import date
from typing import Optional

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from bs4 import BeautifulSoup
import schedule

sys.path.insert(0, os.path.dirname(__file__))
from database import (
    init_db, get_connection, get_todos_productos,
    insertar_precio, get_precios_actuales, generar_clave,
)

# ══════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("paracompara")

# ══════════════════════════════════════════════════════════════════════
#  CONSTANTES
# ══════════════════════════════════════════════════════════════════════
DELAY_MIN = 2.0
DELAY_MAX = 4.0
PAGE_SIZE = 50

HEADERS_JSON = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "es-CO,es;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}
HEADERS_HTML = {**HEADERS_JSON, "Accept": "text/html,application/xhtml+xml"}

# ══════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN TIENDAS
# ══════════════════════════════════════════════════════════════════════

# ── VTEX LEGACY (Éxito, Olímpica) ─────────────────────────────────────
# Endpoint: /api/catalog_system/pub/products/search/?ft=QUERY&_from=0&_to=49
VTEX_LEGACY = {
    "exito": {
        "nombre":   "Éxito",
        "search":   "https://www.exito.com/api/catalog_system/pub/products/search/",
        "categorias": [
            # Categorías amplias
            "Despensa", "Lacteos", "Carnes", "Frutas", "Verduras",
            "Bebidas", "Pan", "Aseo", "Cuidado Personal",
            # Productos específicos de alta rotación
            "leche", "arroz", "aceite", "huevos", "pollo", "carne",
            "yogur", "queso", "mantequilla", "jugo", "agua", "cafe",
            "pasta", "azucar", "sal", "atun", "jabon", "shampoo",
            "detergente", "papel higienico", "servilletas", "galleta",
            "avena", "frijol", "lentejas", "harina maiz", "gaseosa",
        ],
    },
    "olimpica": {
        "nombre":   "Olímpica",
        "search":   "https://www.olimpica.com/api/catalog_system/pub/products/search/",
        "categorias": ["Alimentos", "Lacteos", "Carnes Aves",
                       "Frutas Verduras", "Bebidas", "Panaderia",
                       "Aseo", "Higiene Personal"],
    },
}

# ── VTEX INTELLIGENT SEARCH (Jumbo) ───────────────────────────────────
# Endpoint: /_v/api/intelligent-search/product_search/?query=QUERY&page=1&count=50
VTEX_IS = {
    "jumbo": {
        "nombre":   "Jumbo",
        "search":   "https://tiendasjumbo.co/_v/api/intelligent-search/product_search/",
        "categorias": ["despensa", "lacteos", "carnes", "frutas verduras",
                       "bebidas", "panaderia", "aseo hogar", "cuidado personal"],
    },
}

# ── PLAYWRIGHT (D1, Ara) ───────────────────────────────────────────────
# Selectores verificados inspeccionando el HTML real de cada sitio
PLAYWRIGHT_STORES = {
    "d1": {
        "nombre":   "D1",
        # URLs verificadas del sitio de domicilios de D1 (junio 2025)
        "categorias_url": [
            "https://domicilios.tiendasd1.com/ca/lacteos/L%C3%81CTEOS",
            "https://domicilios.tiendasd1.com/ca/congelados/CONGELADOS",
            "https://domicilios.tiendasd1.com/ca/alimentos%20y%20despensa/ALIMENTOS%20Y%20DESPENSA",
            "https://domicilios.tiendasd1.com/ca/aseo%20hogar/ASEO%20HOGAR",
            "https://domicilios.tiendasd1.com/ca/aseo%20y%20cuidado%20personal/ASEO%20Y%20CUIDADO%20PERSONAL",
            "https://domicilios.tiendasd1.com/ca/bebidas/BEBIDAS",
        ],
        "search_url": "https://domicilios.tiendasd1.com/se/{query}",
        # Selectores verificados contra HTML real de domicilios.tiendasd1.com (junio 2025)
        "item_sel":   "[class*='product-card']",
        "name_sel":   "h3[class*='prod__name']",
        "price_sel":  "p[class*='base__price']",
        "wait_ms":    6000,   # D1 usa Next.js, necesita tiempo para renderizar
    },
}

# ══════════════════════════════════════════════════════════════════════
#  CLASIFICACIÓN AUTOMÁTICA (para modo --discover)
# ══════════════════════════════════════════════════════════════════════
# Mapa keyword → categoría interna BD
# Ordenadas de más específica a más genérica para evitar falsos positivos
KEYWORD_CAT = [
    # Aceites y grasas
    ("aceite de oliva",  "Aceites y grasas"),
    ("aceite vegetal",   "Aceites y grasas"),
    ("aceite girasol",   "Aceites y grasas"),
    ("aceite canola",    "Aceites y grasas"),
    ("aceite soya",      "Aceites y grasas"),
    ("aceite ",          "Aceites y grasas"),
    ("margarina",        "Aceites y grasas"),
    ("manteca",          "Aceites y grasas"),
    ("crema de leche",   "Lácteos"),
    ("leche ",           "Lácteos"),
    ("yogur",            "Lácteos"),
    ("yoghurt",          "Lácteos"),
    ("queso ",           "Lácteos"),
    ("mantequilla",      "Lácteos"),
    ("kumis",            "Lácteos"),
    ("avena ",           "Granos y cereales"),
    ("arroz ",           "Granos y cereales"),
    ("pasta ",           "Granos y cereales"),
    ("fideo",            "Granos y cereales"),
    ("harina ",          "Granos y cereales"),
    ("maíz",             "Granos y cereales"),
    ("maiz",             "Granos y cereales"),
    ("frijol",           "Granos y cereales"),
    ("lenteja",          "Granos y cereales"),
    ("garbanzo",         "Granos y cereales"),
    ("cereal",           "Granos y cereales"),
    ("granola",          "Granos y cereales"),
    ("azúcar",           "Granos y cereales"),
    ("azucar",           "Granos y cereales"),
    ("sal ",             "Condimentos"),
    ("vinagre",          "Condimentos"),
    ("salsa ",           "Condimentos"),
    ("mayonesa",         "Condimentos"),
    ("mostaza",          "Condimentos"),
    ("ketchup",          "Condimentos"),
    ("café ",            "Bebidas"),
    ("cafe ",            "Bebidas"),
    ("agua ",            "Bebidas"),
    ("gaseosa",          "Bebidas"),
    ("coca-cola",        "Bebidas"),
    ("coca cola",        "Bebidas"),
    ("pepsi",            "Bebidas"),
    ("sprite",           "Bebidas"),
    ("fanta",            "Bebidas"),
    ("manzana postobón", "Bebidas"),
    ("colombiana",       "Bebidas"),
    ("bretaña",          "Bebidas"),
    ("red bull",         "Bebidas"),
    ("pony malta",       "Bebidas"),
    ("jugo ",            "Bebidas"),
    ("bebida ",          "Bebidas"),
    ("chocolate ",       "Bebidas"),
    ("té ",              "Bebidas"),
    ("cerveza",          "Bebidas"),
    ("pan ",             "Panadería"),
    ("galleta",          "Panadería"),
    ("arepa",            "Panadería"),
    ("tostada",          "Panadería"),
    ("tomate",           "Frutas y verduras"),
    ("cebolla",          "Frutas y verduras"),
    ("papa ",            "Frutas y verduras"),
    ("zanahoria",        "Frutas y verduras"),
    ("lechuga",          "Frutas y verduras"),
    ("aguacate",         "Frutas y verduras"),
    ("banano",           "Frutas y verduras"),
    ("manzana",          "Frutas y verduras"),
    ("naranja",          "Frutas y verduras"),
    ("limón",            "Frutas y verduras"),
    ("limon",            "Frutas y verduras"),
    ("mango ",           "Frutas y verduras"),
    ("piña",             "Frutas y verduras"),
    ("pina ",            "Frutas y verduras"),
    ("fruta ",           "Frutas y verduras"),
    ("verdura",          "Frutas y verduras"),
    ("vegetal",          "Frutas y verduras"),
    ("espinaca",         "Frutas y verduras"),
    ("brocoli",          "Frutas y verduras"),
    ("brócoli",          "Frutas y verduras"),
    ("pepino",           "Frutas y verduras"),
    ("ahuyama",          "Frutas y verduras"),
    ("yuca ",            "Frutas y verduras"),
    ("ñame ",            "Frutas y verduras"),
    ("name ",            "Frutas y verduras"),
    ("platano",          "Frutas y verduras"),
    ("plátano",          "Frutas y verduras"),
    ("uva ",             "Frutas y verduras"),
    ("fresa ",           "Frutas y verduras"),
    ("maracuya",         "Frutas y verduras"),
    ("mora ",            "Frutas y verduras"),
    ("pera ",            "Frutas y verduras"),
    ("melon",            "Frutas y verduras"),
    ("sandia",           "Frutas y verduras"),
    ("sandía",           "Frutas y verduras"),
    ("pollo",            "Proteínas"),
    ("carne ",           "Proteínas"),
    ("cerdo",            "Proteínas"),
    ("atún",             "Proteínas"),
    ("atun",             "Proteínas"),
    ("huevo",            "Proteínas"),
    ("salchicha",        "Proteínas"),
    ("jamón",            "Proteínas"),
    ("jamon",            "Proteínas"),
    ("chorizo",          "Proteínas"),
    ("pescado",          "Proteínas"),
    ("sardina",          "Proteínas"),
    ("mortadela",        "Proteínas"),
    ("salami",           "Proteínas"),
    ("longaniza",        "Proteínas"),
    ("chicharrón",       "Proteínas"),
    ("chicharron",       "Proteínas"),
    ("mariscos",         "Proteínas"),
    ("camarón",          "Proteínas"),
    ("camaron",          "Proteínas"),
    ("tilapia",          "Proteínas"),
    ("trucha",           "Proteínas"),
    ("lomo ",            "Proteínas"),
    ("pechuga",          "Proteínas"),
    ("muslo ",           "Proteínas"),
    ("costilla",         "Proteínas"),
    # Snacks y dulces
    ("maní",             "Snacks y dulces"),
    ("mani ",            "Snacks y dulces"),
    ("bocadillo",        "Snacks y dulces"),
    ("chocolate ",       "Snacks y dulces"),
    ("bombón",           "Snacks y dulces"),
    ("caramelo",         "Snacks y dulces"),
    ("chicle",           "Snacks y dulces"),
    ("papas fritas",     "Snacks y dulces"),
    ("chitos",           "Snacks y dulces"),
    ("maíz pira",        "Snacks y dulces"),
    ("palomitas",        "Snacks y dulces"),
    ("gomitas",          "Snacks y dulces"),
    ("detergente",       "Aseo del hogar"),
    ("blanqueador",      "Aseo del hogar"),
    ("desinfectante",    "Aseo del hogar"),
    ("limpiador",        "Aseo del hogar"),
    ("papel higiénico",  "Aseo del hogar"),
    ("papel higienico",  "Aseo del hogar"),
    ("servilleta",       "Aseo del hogar"),
    ("toalla cocina",    "Aseo del hogar"),
    ("bolsa basura",     "Aseo del hogar"),
    ("jabón ropa",       "Aseo del hogar"),
    ("jabón ",           "Aseo personal"),
    ("jabon ",           "Aseo personal"),
    ("shampoo",          "Aseo personal"),
    ("champú",           "Aseo personal"),
    ("champu",           "Aseo personal"),
    ("crema dental",     "Aseo personal"),
    ("pasta dental",     "Aseo personal"),
    ("desodorante",      "Aseo personal"),
    ("crema corporal",   "Aseo personal"),
    ("pañal",            "Aseo personal"),
    ("panal",            "Aseo personal"),
]

EXCLUIR = [
    # Electrónica y tecnología
    "televisor", "tv ", " tv,", "smart tv", "celular", "smartphone", "tablet",
    "laptop", "computador", "portatil", "portátil", "monitor", "teclado",
    "mouse ", "audífono", "audifono", "audifonos", "auricular", "parlante",
    "bocina", "altavoz", "cámara", "camara", "impresora", "escaner",
    "router", "modem", "cable usb", "cargador", "batería externa",
    "memoria usb", "disco duro", "proyector", "drone", "consola",
    "videojuego", "control remoto",

    # Electrodomésticos
    "nevera", "refrigerador", "lavadora", "secadora", "microondas",
    "licuadora", "batidora", "tostadora", "cafetera", "plancha ropa",
    "plancha cabello", "secador cabello", "secador pelo", "aspiradora",
    "ventilador", "aire acondicionado", "calentador", "estufa",
    "horno ", "lavavajillas", "extractor", "sanduchera", "waflera",
    "freidora de aire", "freidora ",

    # Ropa y accesorios
    "ropa ", "camisa", "camiseta", "pantalón", "pantalon", "jean",
    "vestido", "falda", "blusa", "chaqueta", "abrigo", "zapato",
    "zapatilla", "tenis ", "bota ", "sandalia", "bolso", "cartera",
    "maleta ", "mochila", "cinturón", "cinturon", "corbata", "bufanda",
    "guante", "gorro ", "sombrero", "gafas ", "reloj ",

    # Muebles y hogar
    "silla ", "mesa ", "escritorio", "colchón", "colchon", "almohada",
    "cobija", "sábana", "sabana ", "toalla baño", "cortina", "alfombra",
    "tapete", "estante", "mueble", "lámpara", "lampara", "espejo",

    # Juguetes y deportes
    "juguete", "muñeca", "muneca", "lego ", "pelota ", "bicicleta",
    "patineta", "patín", "patin ", "raqueta", "gimnasio", "pesa ",
    "colchoneta", "tabla surf",

    # Papelería y libros
    "libro ", "libros ", "cuaderno", "lapicero", "bolígrafo", "boligrafo",
    "lápiz", "lapiz ", "marcador", "carpeta", "agenda ", "revista ",

    # Medicamentos y suplementos
    "medicamento", "medicina", "pastilla", "cápsula", "capsula",
    "jarabe ", "vitamina", "suplemento", "proteína en polvo",
    "creatina", "antibiótico", "antibiotic", "analgésico",

    # Utensilios de cocina (no comida)
    "olla ", "sartén", "sarten", "cuchillo ", "tenedor ", "cuchara ",
    "vaso ", "taza ", "plato ", "bowl ", "termo ", "termos",
    "recipiente", "tupperware", "contenedor", "jarra ", "licuadora",

    # Mascotas (no consumo humano)
    "perro ", "gato ", "mascota", "para perro", "para gato",
    "alimento perro", "alimento gato", "collar ", "correa ",

    # Otros no alimentarios
    "pintura ", "pegante", "silicona", "lija ", "herramienta",
    "tornillo", "foco ", "bombillo", "linterna", "pila aa",
    "pilas ", "batería aa", "encendedor", "vela ", "veladora",
    "flores ", "planta ", "maceta", "abono ", "insecticida",
    "raticida", "trampa raton",
]

MARCAS_CONOCIDAS = [
    "Alpina","Alquería","Colanta","Diana","Doria","Quaker","Bimbo","Noel",
    "Zenú","Rica","Colanta","FUD","Coca-Cola","Pepsi","Hit","Postobón",
    "Cristal","Brisa","Sello Rojo","Colcafé","Nescafé","Águila Roja",
    "Ariel","Fab","Surf","Skip","Axion","Fabuloso","Mr. Músculo","Olimpia",
    "Colgate","Oral-B","Head & Shoulders","Pantene","Dove","Familia","Scott",
    "Tisu","Elite","Ramo","Nutresa","Mazola","Coroli","Carbonell","Refisal",
    "La Cabaña","P.A.N.","Rama","Génesis","Nobrand",
]
MARCAS_LOWER = {m.lower(): m for m in MARCAS_CONOCIDAS}

EMOJIS_CAT = {
    "Lácteos": "🥛", "Granos y cereales": "🌾", "Condimentos": "🧂",
    "Aceites y grasas": "🫙", "Bebidas": "🧃", "Panadería": "🍞",
    "Frutas y verduras": "🥦", "Proteínas": "🥩",
    "Aseo del hogar": "🧹", "Aseo personal": "🧴",
    "Snacks y dulces": "🍬",
}


# ══════════════════════════════════════════════════════════════════════
#  UTILIDADES GENERALES
# ══════════════════════════════════════════════════════════════════════
def pausa(extra: float = 0):
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX) + extra)


def limpiar_precio(texto: str) -> Optional[int]:
    """
    Convierte texto de precio colombiano a entero COP.
    Formatos soportados:
      '$12.900'       → 12900
      '12.900,00'     → 12900  (punto=miles, coma=decimal)
      '12,900.00'     → 12900  (coma=miles, punto=decimal — algunos sitios)
      '12900'         → 12900
      '$ 3.450'       → 3450
    """
    if not texto:
        return None
    t = re.sub(r"[^\d.,]", "", texto.strip())
    if not t:
        return None

    if "." in t and "," in t:
        # Determinar cuál es el separador decimal mirando el último separador
        ultimo_punto = t.rfind(".")
        ultima_coma  = t.rfind(",")
        if ultima_coma > ultimo_punto:
            # Formato colombiano: 12.900,00 → punto=miles, coma=decimal
            t = t.replace(".", "").split(",")[0]
        else:
            # Formato anglosajón: 12,900.00 → coma=miles, punto=decimal
            t = t.replace(",", "").split(".")[0]
    elif "." in t:
        partes = t.split(".")
        if len(partes) == 2 and len(partes[1]) <= 2:
            # 3.45 podría ser precio bajo, pero en COP 12.900 es miles
            # Si la parte entera tiene más de 2 dígitos → miles
            if len(partes[0]) >= 2:
                t = t.replace(".", "")   # 12.900 → 12900
            else:
                t = partes[0]            # 3.45 → 3 (raro en COP, descartar decimal)
        else:
            t = t.replace(".", "")       # 12.900.000 → 12900000
    elif "," in t:
        # 12900,00 → descartar decimales
        t = t.split(",")[0]

    val = int(t) if t.isdigit() else None
    return val if val and 100 < val < 100_000_000 else None


def normalizar(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def es_supermercado(nombre: str) -> bool:
    n = normalizar(nombre)
    for ex in EXCLUIR:
        if ex in n:
            return False
    for kw, _ in KEYWORD_CAT:
        if kw in n:
            return True
    return False


def inferir_categoria(nombre: str) -> str:
    n = normalizar(nombre)
    for kw, cat in KEYWORD_CAT:   # ya están ordenadas de específica a genérica
        if kw in n:
            return cat
    return "Granos y cereales"


def extraer_marca(nombre: str, marca_api: str = "") -> str:
    if marca_api:
        for ml, mo in MARCAS_LOWER.items():
            if ml in marca_api.lower():
                return mo
    n = normalizar(nombre)
    for ml, mo in MARCAS_LOWER.items():
        if ml in n:
            return mo
    palabras = nombre.split()
    for p in palabras:
        if p.istitle() and len(p) > 2:
            return p
    return "Génesis"


def extraer_cantidad_unidad(nombre: str) -> tuple[int, str]:
    n = nombre.lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kg\b", n)
    if m:
        return int(float(m.group(1).replace(",", ".")) * 1000), "g"
    m = re.search(r"(\d+)\s*gr?\b", n)
    if m:
        return int(m.group(1)), "g"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*lit(?:ros?)?\b", n)
    if m:
        return int(float(m.group(1).replace(",", ".")) * 1000), "ml"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*l\b", n)
    if m:
        return int(float(m.group(1).replace(",", ".")) * 1000), "ml"
    m = re.search(r"(\d+)\s*ml\b", n)
    if m:
        return int(m.group(1)), "ml"
    m = re.search(r"[x×]\s*(\d+)|(\d+)\s*(?:und|uni|u\b|pack|paq)", n)
    if m:
        return int(m.group(1) or m.group(2)), "u"
    return 1, "u"


def limpiar_nombre(raw: str) -> str:
    n = raw.strip()
    if n == n.upper():
        n = n.title()
    n = re.sub(r"\s+(bolsa|caja|paquete|und\.?|unidad)\s*$", "", n, flags=re.IGNORECASE)
    return n.strip()


# ══════════════════════════════════════════════════════════════════════
#  MATCHING producto BD ↔ resultado scrapeado
# ══════════════════════════════════════════════════════════════════════
def score_match(prod: dict, nombre_scrap: str, precio: int) -> int:
    nb = normalizar(prod["nombre"])
    ns = normalizar(nombre_scrap)
    marca = normalizar(prod.get("marca") or "")
    score = 0
    palabras = [p for p in nb.split() if len(p) > 3]
    if palabras:
        score += int(sum(1 for p in palabras if p in ns) / len(palabras) * 50)
    if marca and marca in ns:
        score += 25
    cant = str(prod["cantidad"])
    if cant in ns or (cant + prod["unidad"]) in ns.replace(" ", ""):
        score += 15
    refs = list((prod.get("_p") or {}).values())
    if refs:
        prom = sum(refs) / len(refs)
        if prom * 0.4 < precio < prom * 1.8:
            score += 10
    return score


def mejor_match(productos: list[dict], nombre: str, precio: int) -> Optional[dict]:
    mejor, mejor_s = None, 45
    for p in productos:
        s = score_match(p, nombre, precio)
        if s > mejor_s:
            mejor_s, mejor = s, p
    return mejor


def enrich(productos: list[dict]):
    for p in productos:
        if "_p" not in p:
            rows = get_precios_actuales(p["id"])
            p["_p"] = {r["tienda_id"]: r["precio"] for r in rows}


# ══════════════════════════════════════════════════════════════════════
#  REGISTRO PRODUCTO NUEVO (modo --discover)
# ══════════════════════════════════════════════════════════════════════
def registrar_nuevo(nombre_raw: str, marca_api: str,
                    productos: list[dict]) -> Optional[int]:
    nombre = limpiar_nombre(nombre_raw)
    if not es_supermercado(nombre):
        return None
    clave = generar_clave(nombre)
    conn  = get_connection()
    try:
        existe = conn.execute("SELECT id FROM productos WHERE clave=?", (clave,)).fetchone()
        if existe:
            return existe["id"]
        cat   = inferir_categoria(nombre)
        marca = extraer_marca(nombre, marca_api)
        cant, uni = extraer_cantidad_unidad(nombre)
        emoji = EMOJIS_CAT.get(cat, "🛒")
        conn.execute("INSERT OR IGNORE INTO marcas(nombre) VALUES(?)", (marca,))
        conn.execute("INSERT OR IGNORE INTO categorias(nombre) VALUES(?)", (cat,))
        marca_id = conn.execute("SELECT id FROM marcas WHERE nombre=?", (marca,)).fetchone()["id"]
        cat_id   = conn.execute("SELECT id FROM categorias WHERE nombre=?", (cat,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO productos(clave,nombre,emoji,marca_id,categoria_id,unidad,cantidad) VALUES(?,?,?,?,?,?,?)",
            (clave, nombre, emoji, marca_id, cat_id, uni, cant),
        )
        conn.commit()
        pid = conn.execute("SELECT id FROM productos WHERE clave=?", (clave,)).fetchone()["id"]
        log.info(f"  ➕ NUEVO: '{nombre[:50]}' | {marca} | {cat} | {cant}{uni}")
        # Agregar a lista en memoria
        from database import get_producto_por_clave
        np = get_producto_por_clave(clave)
        if np:
            np["_p"] = {}
            productos.append(np)
        return pid
    except Exception as exc:
        log.error(f"  Error registrando '{nombre[:40]}': {exc}")
        conn.rollback()
        return None
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
#  VTEX LEGACY — Éxito, Olímpica
# ══════════════════════════════════════════════════════════════════════
def vtex_legacy_pagina(url: str, query: str, desde: int,
                        _intentos: int = 0) -> list[dict]:
    """
    Consulta el endpoint VTEX legacy. Si la respuesta está vacía o no es JSON
    (rate limiting), espera y reintenta hasta 2 veces. Si falla las 3 veces,
    devuelve [] sin seguir reintentando.
    """
    MAX_REINTENTOS = 2
    try:
        r = requests.get(url, headers=HEADERS_JSON, params={
            "ft": query, "_from": desde, "_to": desde + PAGE_SIZE - 1,
        }, timeout=25)
        if r.status_code not in (200, 206):
            log.warning(f"  VTEX legacy HTTP {r.status_code} para '{query}'")
            return []
        # Verificar que la respuesta es JSON antes de parsear
        content = r.text.strip()
        if not content or content[0] not in ('[', '{'):
            if _intentos < MAX_REINTENTOS:
                espera = 30 * (_intentos + 1)  # 30s, 60s
                log.warning(f"  VTEX legacy respuesta vacía para '{query}' — esperando {espera}s")
                time.sleep(espera)
                return vtex_legacy_pagina(url, query, desde, _intentos + 1)
            log.warning(f"  VTEX legacy sin respuesta válida tras {MAX_REINTENTOS+1} intentos: '{query}'")
            return []
        items = []
        for prod in (r.json() or []):
            nombre = prod.get("productName", "")
            marca  = prod.get("brand", "")
            precio = None
            for sku in prod.get("items", []):
                for seller in sku.get("sellers", []):
                    p = seller.get("commertialOffer", {}).get("Price", 0)
                    if p > 0:
                        precio = int(round(p))
                        break
                if precio:
                    break
            if nombre and precio:
                items.append({"nombre": nombre, "marca": marca, "precio": precio})
        return items
    except Exception as exc:
        if _intentos < MAX_REINTENTOS:
            espera = 30 * (_intentos + 1)
            log.warning(f"  VTEX legacy error: {exc} — reintentando en {espera}s")
            time.sleep(espera)
            return vtex_legacy_pagina(url, query, desde, _intentos + 1)
        log.warning(f"  VTEX legacy error definitivo para '{query}': {exc}")
        return []


def scrape_vtex_legacy(tienda_id: str, productos: list[dict],
                        discover: bool) -> tuple[dict, int]:
    cfg    = VTEX_LEGACY[tienda_id]
    precios: dict[int, int] = {}
    nuevos = 0
    enrich(productos)
    log.info(f"▶ {cfg['nombre']} (VTEX legacy)")

    for cat in cfg["categorias"]:
        pagina = 0
        while True:
            items = vtex_legacy_pagina(cfg["search"], cat, pagina * PAGE_SIZE)
            if not items:
                break
            for it in items:
                prod = mejor_match(productos, it["nombre"], it["precio"])
                if prod:
                    if prod["id"] not in precios:
                        precios[prod["id"]] = it["precio"]
                elif discover:
                    pid = registrar_nuevo(it["nombre"], it["marca"], productos)
                    if pid and pid not in precios:
                        precios[pid] = it["precio"]
                        nuevos += 1
            if len(items) < PAGE_SIZE:
                break
            pagina += 1
            pausa()
        pausa()

    log.info(f"  {cfg['nombre']}: {len(precios)} precios · {nuevos} nuevos")
    return precios, nuevos


# ══════════════════════════════════════════════════════════════════════
#  VTEX INTELLIGENT SEARCH — Jumbo
# ══════════════════════════════════════════════════════════════════════
def vtex_is_pagina(url: str, query: str, pagina: int) -> list[dict]:
    """
    VTEX Intelligent Search API.
    Endpoint: /_v/api/intelligent-search/product_search/
    Params:   query, page, count, locale
    Respuesta: { products: [ { productName, brand, priceRange: { sellingPrice: { highValue } } } ] }
    """
    try:
        r = requests.get(url, headers=HEADERS_JSON, params={
            "query":  query,
            "page":   pagina,
            "count":  PAGE_SIZE,
            "locale": "es-CO",
            "hideUnavailableItems": "true",
        }, timeout=20, verify=False)
        if r.status_code != 200:
            log.warning(f"  VTEX IS HTTP {r.status_code} para '{query}' p{pagina}")
            return []
        data = r.json()
        prods = data.get("products", [])
        items = []
        for prod in prods:
            nombre = prod.get("productName", "")
            marca  = prod.get("brand", "")
            # Precio en priceRange.sellingPrice.highValue (en centavos × 100 algunas veces)
            precio = None
            pr = prod.get("priceRange", {})
            sp = pr.get("sellingPrice", {})
            hv = sp.get("highValue") or sp.get("lowValue")
            if hv:
                precio = int(round(float(hv)))
            # Fallback: items[0].sellers[0].commertialOffer.Price
            if not precio:
                for item in prod.get("items", []):
                    for seller in item.get("sellers", []):
                        p = seller.get("commertialOffer", {}).get("Price", 0)
                        if p > 0:
                            precio = int(round(p))
                            break
                    if precio:
                        break
            if nombre and precio:
                items.append({"nombre": nombre, "marca": marca, "precio": precio})
        return items
    except Exception as exc:
        log.warning(f"  VTEX IS error: {exc}")
        return []


def scrape_vtex_is(tienda_id: str, productos: list[dict],
                    discover: bool) -> tuple[dict, int]:
    cfg    = VTEX_IS[tienda_id]
    precios: dict[int, int] = {}
    nuevos = 0
    enrich(productos)
    log.info(f"▶ {cfg['nombre']} (VTEX Intelligent Search)")

    for cat in cfg["categorias"]:
        pagina = 1
        while True:
            items = vtex_is_pagina(cfg["search"], cat, pagina)
            if not items:
                break
            for it in items:
                prod = mejor_match(productos, it["nombre"], it["precio"])
                if prod:
                    if prod["id"] not in precios:
                        precios[prod["id"]] = it["precio"]
                elif discover:
                    pid = registrar_nuevo(it["nombre"], it["marca"], productos)
                    if pid and pid not in precios:
                        precios[pid] = it["precio"]
                        nuevos += 1
            if len(items) < PAGE_SIZE:
                break
            pagina += 1
            pausa()
        pausa()

    log.info(f"  {cfg['nombre']}: {len(precios)} precios · {nuevos} nuevos")
    return precios, nuevos


# ══════════════════════════════════════════════════════════════════════
#  PLAYWRIGHT — D1, Ara
# ══════════════════════════════════════════════════════════════════════
def scrape_playwright(tienda_id: str, productos: list[dict],
                       discover: bool) -> tuple[dict, int]:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    cfg    = PLAYWRIGHT_STORES[tienda_id]
    precios: dict[int, int] = {}
    nuevos = 0
    enrich(productos)
    log.info(f"▶ {cfg['nombre']} (Playwright)")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx  = browser.new_context(
            user_agent=HEADERS_HTML["User-Agent"],
            locale="es-CO",
            timezone_id="America/Bogota",
            viewport={"width": 1366, "height": 768},
            extra_http_headers={"Accept-Language": "es-CO,es;q=0.9"},
        )
        # Bloquear recursos pesados para ir más rápido
        ctx.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf,mp4,mp3}",
                  lambda r: r.abort())
        page = ctx.new_page()

        for cat_url in cfg["categorias_url"]:
            log.info(f"  URL: {cat_url}")
            num_pag = 1
            while True:
                # D1 usa ?currentPage=N para paginación
                url = f"{cat_url}?currentPage={num_pag}" if num_pag > 1 else cat_url
                log.info(f"    Página {num_pag}: {url}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=40_000)
                except PWTimeout:
                    log.warning(f"  Timeout en {url}")
                    break

                # Esperar a que carguen los productos
                page.wait_for_timeout(cfg["wait_ms"])
                # Scroll para activar lazy loading dentro de la página
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, 0)")

                soup       = BeautifulSoup(page.content(), "html.parser")
                items_html = soup.select(cfg["item_sel"])

                if not items_html:
                    log.info(f"    → Sin productos en página {num_pag}, fin de categoría")
                    break

                log.info(f"    → {len(items_html)} productos en página {num_pag}")
                for item in items_html:
                    nt = item.select_one(cfg["name_sel"])
                    pt = item.select_one(cfg["price_sel"])
                    if not nt or not pt:
                        continue
                    nombre = nt.get_text(strip=True)
                    precio = limpiar_precio(pt.get("content") or pt.get_text())
                    if not nombre or not precio:
                        continue
                    prod = mejor_match(productos, nombre, precio)
                    if prod:
                        if prod["id"] not in precios:
                            precios[prod["id"]] = precio
                    elif discover:
                        pid = registrar_nuevo(nombre, "", productos)
                        if pid and pid not in precios:
                            precios[pid] = precio
                            nuevos += 1

                # Si devolvió menos de 20 productos, es la última página
                if len(items_html) < 20:
                    break
                num_pag += 1
                pausa()
            pausa()

        browser.close()

    log.info(f"  {cfg['nombre']}: {len(precios)} precios · {nuevos} nuevos")
    return precios, nuevos


# ══════════════════════════════════════════════════════════════════════
#  MODO ONLY-PRICES: solo actualiza productos ya en BD (más rápido)
# ══════════════════════════════════════════════════════════════════════
def scrape_only_prices(tienda_id: str, productos: list[dict]) -> dict[int, int]:
    """
    Busca cada producto de la BD directamente por nombre+marca.
    No descubre productos nuevos. Mucho más rápido que recorrer categorías.
    """
    precios: dict[int, int] = {}
    enrich(productos)

    if tienda_id in VTEX_LEGACY:
        cfg    = VTEX_LEGACY[tienda_id]
        search = cfg["search"]
        log.info(f"▶ {cfg['nombre']} (only-prices, VTEX legacy)")
        errores_consec = 0
        for prod in productos:
            if errores_consec >= 5:
                log.warning(f"  ⚠ {cfg['nombre']}: 5 errores consecutivos, pausando 2 min")
                time.sleep(120)
                errores_consec = 0
            query = f"{prod.get('marca','')} {prod['nombre'].split()[0]}".strip()
            items = vtex_legacy_pagina(search, query, 0)
            if items:
                errores_consec = 0
                for it in items[:10]:
                    if score_match(prod, it["nombre"], it["precio"]) >= 45:
                        precios[prod["id"]] = it["precio"]
                        break
            else:
                errores_consec += 1
            pausa(0.5)

    elif tienda_id in VTEX_IS:
        cfg    = VTEX_IS[tienda_id]
        search = cfg["search"]
        log.info(f"▶ {cfg['nombre']} (only-prices, VTEX IS)")
        errores_consec = 0
        for prod in productos:
            if errores_consec >= 5:
                log.warning(f"  ⚠ {cfg['nombre']}: 5 errores consecutivos, pausando 2 min")
                time.sleep(120)
                errores_consec = 0
            query = f"{prod.get('marca','')} {prod['nombre'].split()[0]}".strip()
            items = vtex_is_pagina(search, query, 1)
            if items:
                errores_consec = 0
                for it in items[:10]:
                    if score_match(prod, it["nombre"], it["precio"]) >= 45:
                        precios[prod["id"]] = it["precio"]
                        break
            else:
                errores_consec += 1
            pausa(0.5)

    elif tienda_id in PLAYWRIGHT_STORES:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        cfg = PLAYWRIGHT_STORES[tienda_id]
        log.info(f"▶ {cfg['nombre']} (only-prices, categorías)")

        # Para D1 usamos las categorías en vez de la búsqueda por texto
        # porque el buscador de D1 devuelve resultados poco precisos
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage",
                      "--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(
                user_agent=HEADERS_HTML["User-Agent"],
                locale="es-CO", timezone_id="America/Bogota",
                viewport={"width": 1366, "height": 768},
            )
            ctx.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
                      lambda r: r.abort())
            page = ctx.new_page()

            for cat_url in cfg["categorias_url"]:
                log.info(f"  Categoría: {cat_url.split('/')[-1]}")
                num_pag = 1
                while True:
                    url = f"{cat_url}?currentPage={num_pag}" if num_pag > 1 else cat_url
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=40_000)
                        page.wait_for_timeout(cfg["wait_ms"])
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(2000)
                        page.evaluate("window.scrollTo(0, 0)")
                    except PWTimeout:
                        log.warning(f"  Timeout en {url}")
                        break

                    soup       = BeautifulSoup(page.content(), "html.parser")
                    items_html = soup.select(cfg["item_sel"])
                    if not items_html:
                        break

                    log.info(f"  → {len(items_html)} productos en página {num_pag}")
                    for item in items_html:
                        nt = item.select_one(cfg["name_sel"])
                        pt = item.select_one(cfg["price_sel"])
                        if not nt or not pt:
                            continue
                        nombre_scrap = nt.get_text(strip=True)
                        precio = limpiar_precio(pt.get("content") or pt.get_text())
                        if not precio:
                            continue
                        for prod in productos:
                            if prod["id"] in precios:
                                continue
                            if score_match(prod, nombre_scrap, precio) >= 45:
                                precios[prod["id"]] = precio
                                log.info(f"  ✓ {prod['nombre']:<35} → ${precio:,}")
                                break

                    if len(items_html) < 20:
                        break
                    num_pag += 1
                    pausa()
                pausa()

            browser.close()

    log.info(f"  Encontrados: {len(precios)}/{len(productos)}")
    return precios


# ══════════════════════════════════════════════════════════════════════
#  GUARDAR EN BD
# ══════════════════════════════════════════════════════════════════════
def guardar(tienda_id: str, precios: dict[int, int]):
    """Guarda precios filtrando outliers vs historial propio y otras tiendas."""
    from database import get_connection as _gc
    hoy  = date.today().isoformat()
    ok   = 0
    rech = 0
    conn = _gc()
    for pid, precio in precios.items():
        # Validar vs historial propio de este producto/tienda
        hist = conn.execute(
            "SELECT AVG(precio) as a FROM precios WHERE producto_id=? AND tienda_id=? AND fecha<?",
            (pid, tienda_id, hoy)
        ).fetchone()["a"]
        if hist and (precio > hist * 4.0 or precio < hist * 0.25):
            log.warning(f"  ✗ Precio rechazado prod {pid} {tienda_id}: ${precio:,} (hist=${int(hist):,})")
            rech += 1
            continue
        try:
            insertar_precio(pid, tienda_id, precio, hoy)
            ok += 1
        except Exception as exc:
            log.error(f"  BD error prod {pid}: {exc}")
    conn.close()
    log.info(f"  ✔ {ok} precios guardados, {rech} rechazados → '{tienda_id}'")


# ══════════════════════════════════════════════════════════════════════
#  JOB PRINCIPAL
# ══════════════════════════════════════════════════════════════════════
def run(only_prices: bool = True, tienda_filter: str | None = None):
    modo = "SOLO PRECIOS" if only_prices else "DESCUBRIMIENTO COMPLETO"
    log.info("╔══════════════════════════════════════════════════╗")
    log.info(f"║  Para&Compara — Scraping [{modo}]")
    log.info(f"║  Fecha: {date.today().isoformat()}")
    log.info("╚══════════════════════════════════════════════════╝")

    init_db()
    productos = get_todos_productos()
    log.info(f"Productos en BD: {len(productos)}")

    resumen: dict[str, dict] = {}
    todas = list(VTEX_LEGACY) + list(VTEX_IS) + list(PLAYWRIGHT_STORES)
    if tienda_filter:
        todas = [t for t in todas if t == tienda_filter]
        if not todas:
            log.error(f"Tienda '{tienda_filter}' no existe. Opciones: exito, jumbo, olimpica, d1")
            return

    for tid in todas:
        try:
            if only_prices:
                precios = scrape_only_prices(tid, productos)
                nuevos  = 0
            elif tid in VTEX_LEGACY:
                precios, nuevos = scrape_vtex_legacy(tid, productos, discover=True)
            elif tid in VTEX_IS:
                precios, nuevos = scrape_vtex_is(tid, productos, discover=True)
            else:
                precios, nuevos = scrape_playwright(tid, productos, discover=True)
            guardar(tid, precios)
            resumen[tid] = {"precios": len(precios), "nuevos": nuevos}
        except Exception as exc:
            log.error(f"Error en {tid}: {exc}", exc_info=True)
            resumen[tid] = {"precios": 0, "nuevos": 0}
        pausa()

    productos_final = get_todos_productos()
    log.info("=" * 55)
    log.info("  RESUMEN")
    all_cfg = {**VTEX_LEGACY, **VTEX_IS, **PLAYWRIGHT_STORES}
    for tid, d in resumen.items():
        metodo = "VTEX" if tid in {**VTEX_LEGACY, **VTEX_IS} else "Playwright"
        log.info(f"  {all_cfg[tid]['nombre']:<12}  {d['precios']:>4} precios  "
                 f"{d['nuevos']:>4} nuevos  [{metodo}]")
    log.info(f"  {'─'*48}")
    tot_p = sum(d['precios'] for d in resumen.values())
    tot_n = sum(d['nuevos'] for d in resumen.values())
    log.info(f"  {'TOTAL':<12}  {tot_p:>4} precios  {tot_n:>4} nuevos")
    log.info(f"  Catálogo: {len(productos)} → {len(productos_final)} productos")
    log.info("=" * 55)


# ══════════════════════════════════════════════════════════════════════
#  MODO TEST
# ══════════════════════════════════════════════════════════════════════
def run_test(tienda_id: str, query: str):
    all_cfg = {**VTEX_LEGACY, **VTEX_IS, **PLAYWRIGHT_STORES}
    if tienda_id not in all_cfg:
        print(f"Tienda desconocida. Opciones: {list(all_cfg)}")
        return
    print(f"\n{'='*60}\n  TEST '{query}' en '{tienda_id}'\n{'='*60}")

    if tienda_id in VTEX_LEGACY:
        items = vtex_legacy_pagina(VTEX_LEGACY[tienda_id]["search"], query, 0)
        metodo = "VTEX legacy"
    elif tienda_id in VTEX_IS:
        items = vtex_is_pagina(VTEX_IS[tienda_id]["search"], query, 1)
        metodo = "VTEX Intelligent Search"
    else:
        from playwright.sync_api import sync_playwright
        cfg = PLAYWRIGHT_STORES[tienda_id]
        url = cfg["search_url"].format(query=query.replace(" ", "+"))
        print(f"  Abriendo {url}…")
        with sync_playwright() as pw:
            br   = pw.chromium.launch(headless=True)
            ctx  = br.new_context(user_agent=HEADERS_HTML["User-Agent"])
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=35_000)
            page.wait_for_timeout(cfg["wait_ms"])
            soup = BeautifulSoup(page.content(), "html.parser")
            br.close()
        items = []
        for item in soup.select(cfg["item_sel"])[:20]:
            nt = item.select_one(cfg["name_sel"])
            pt = item.select_one(cfg["price_sel"])
            if nt and pt:
                p = limpiar_precio(pt.get("content") or pt.get_text())
                if p:
                    items.append({"nombre": nt.get_text(strip=True), "precio": p, "marca": ""})
        metodo = "Playwright"

    print(f"  Método : {metodo}")
    print(f"  Items  : {len(items)}\n")
    for it in items[:15]:
        es  = "✓" if es_supermercado(it["nombre"]) else "✗"
        cat = inferir_categoria(it["nombre"]) if es == "✓" else "—"
        print(f"  ${it['precio']:>9,}  {es}  {cat:<22}  {it['nombre'][:40]}")
    print()


# ══════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Para&Compara · Scraper gratuito")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--only-prices", action="store_true",
                     help="Actualizar solo precios de productos ya registrados (RÁPIDO)")
    grp.add_argument("--discover",    action="store_true",
                     help="Actualizar precios + registrar productos nuevos (COMPLETO)")
    grp.add_argument("--test",        metavar="TIENDA",
                     help="Probar una tienda: exito, jumbo, olimpica, d1")
    parser.add_argument("--query", metavar="TEXTO", default="leche",
                        help="Producto para modo --test")
    parser.add_argument("--hora",  default="03:00",
                        help="Hora diaria HH:MM cuando se usa sin flags (default: 03:00)")
    parser.add_argument("--tienda", metavar="TIENDA",
                        help="Limitar a una tienda: exito, jumbo, olimpica, d1")
    args = parser.parse_args()

    if args.test:
        run_test(args.test.lower(), args.query)
    elif args.only_prices:
        run(only_prices=True, tienda_filter=args.tienda)
    elif args.discover:
        run(only_prices=False, tienda_filter=args.tienda)
    else:
        # Sin flags → programar diario en modo only-prices
        log.info(f"Scraper programado todos los días a las {args.hora} (--only-prices)")
        log.info("Para descubrimiento completo usá: python scraper.py --discover")
        log.info("Ctrl+C para detener.")
        schedule.every().day.at(args.hora).do(lambda: run(only_prices=True))
        while True:
            schedule.run_pending()
            time.sleep(30)
