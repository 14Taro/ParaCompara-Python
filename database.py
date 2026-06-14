"""
database.py — Capa de datos Para&Compara
=========================================
Motor:    SQLite (archivo local paracompara.db)
Migrar a PostgreSQL: reemplazar get_connection() con psycopg2
y cambiar los placeholders ? por %s.

Tablas
------
  categorias   → Lácteos, Granos, Aseo personal…
  marcas       → Alpina, Diana, Zenú…
  tiendas      → Éxito, Jumbo, D1, Ara, Olímpica
  sucursales   → Sucursales por tienda con coordenadas
  productos    → Producto con marca, categoría, unidad
  precios      → Precio diario (producto × tienda × fecha)
"""

import math
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "paracompara.db"


# ══════════════════════════════════════════════════════════════════════
#  CONEXIÓN
# ══════════════════════════════════════════════════════════════════════
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ══════════════════════════════════════════════════════════════════════
#  DDL — ESQUEMA COMPLETO
# ══════════════════════════════════════════════════════════════════════
DDL = """
-- Categorías de producto
CREATE TABLE IF NOT EXISTS categorias (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL   -- 'Lácteos', 'Granos y cereales', …
);

-- Marcas comerciales
CREATE TABLE IF NOT EXISTS marcas (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE NOT NULL   -- 'Alpina', 'Diana', 'Zenú', …
);

-- Cadenas de supermercados
CREATE TABLE IF NOT EXISTS tiendas (
    id     TEXT PRIMARY KEY,      -- slug: 'exito', 'd1', …
    nombre TEXT NOT NULL,
    color  TEXT NOT NULL,         -- color hex para UI '#f5c842'
    bg     TEXT NOT NULL          -- color de fondo de logo
);

-- Sucursales físicas con geolocalización
CREATE TABLE IF NOT EXISTS sucursales (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tienda_id  TEXT NOT NULL REFERENCES tiendas(id) ON DELETE CASCADE,
    nombre     TEXT NOT NULL,
    direccion  TEXT NOT NULL,
    lat        REAL NOT NULL,
    lng        REAL NOT NULL
);

-- Catálogo de productos
CREATE TABLE IF NOT EXISTS productos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    clave        TEXT UNIQUE NOT NULL,  -- slug buscable: 'leche-alpina-1l'
    nombre       TEXT NOT NULL,         -- nombre de exhibición
    emoji        TEXT NOT NULL,
    marca_id     INTEGER REFERENCES marcas(id),
    categoria_id INTEGER REFERENCES categorias(id),
    unidad       TEXT NOT NULL,         -- 'g' | 'ml' | 'u'
    cantidad     INTEGER NOT NULL       -- 1000 g, 500 ml, 12 u …
);

-- Historial de precios (una fila por producto × tienda × fecha)
CREATE TABLE IF NOT EXISTS precios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    tienda_id   TEXT    NOT NULL REFERENCES tiendas(id)  ON DELETE CASCADE,
    precio      INTEGER NOT NULL,   -- COP entero, sin decimales
    fecha       TEXT    NOT NULL,   -- ISO 'YYYY-MM-DD'
    UNIQUE(producto_id, tienda_id, fecha)
);

CREATE INDEX IF NOT EXISTS idx_precios_prod  ON precios(producto_id);
CREATE INDEX IF NOT EXISTS idx_precios_tienda ON precios(tienda_id);
CREATE INDEX IF NOT EXISTS idx_precios_fecha  ON precios(fecha);
CREATE INDEX IF NOT EXISTS idx_suc_tienda     ON sucursales(tienda_id);
"""


def create_tables(conn: sqlite3.Connection):
    conn.executescript(DDL)
    conn.commit()


# ══════════════════════════════════════════════════════════════════════
#  DATOS SEMILLA
# ══════════════════════════════════════════════════════════════════════

CATEGORIAS_DATA = [
    "Aceites y grasas",
    "Granos y cereales",
    "Lácteos",
    "Proteínas",
    "Bebidas",
    "Panadería",
    "Frutas y verduras",
    "Aseo del hogar",
    "Aseo personal",
    "Condimentos",
]

MARCAS_DATA = [
    "Alpina", "Diana", "Zenú", "Sello Rojo", "Colgate",
    "Ariel", "Fabuloso", "Familia", "Quaker", "Bimbo",
    "Coca-Cola", "Hit", "Cristal", "Head & Shoulders",
    "Rama", "Carbonell", "La Cabaña", "P.A.N.", "Scott",
    "Refisal", "Doria", "Alquería", "Génesis",
]

TIENDAS_DATA = [
    ("exito",    "Éxito",    "#f5c842", "#2a2200"),
    ("jumbo",    "Jumbo",    "#ff6b7a", "#2a0007"),
    ("d1",       "D1",       "#ff9f40", "#2a1500"),
    ("olimpica", "Olímpica", "#4da6ff", "#001530"),
]

SUCURSALES_DATA = [
    # (tienda_id, nombre, direccion, lat, lng)
    # ── ÉXITO (5) ──────────────────────────────────────────────────
    ("exito","Éxito Contadora",      "Calle 31 #69-75, Contadora",                       10.4028,-75.5170),
    ("exito","Éxito Castellana",     "Av. Pedro de Heredia #30-14, Villa Sandra",         10.4195,-75.5330),
    ("exito","Éxito San Diego",      "Calle 38 #10-85, San Diego",                        10.4043,-75.5062),
    ("exito","Éxito Los Ejecutivos", "Calle 31 #57-106 local 121, C.C. Los Ejecutivos",   10.4012,-75.5245),
    ("exito","Éxito La Matuna",      "Av. Venezuela, Carrera 35 #9-41, La Matuna",        10.4001,-75.5120),
    # ── JUMBO (2) ──────────────────────────────────────────────────
    ("jumbo","Jumbo Caribe Plaza",          "Cl. 29D #22-108, C.C. Caribe Plaza",         10.4065,-75.5005),
    ("jumbo","Jumbo Mall Plaza El Castillo","Calle 13 #31A-45, C.C. Mall Plaza",           10.3892,-75.4875),
    # ── D1 (13) ────────────────────────────────────────────────────
    ("d1","D1 Barrio España",     "Cl 30B #63-43, Barrio España",                         10.4102,-75.5205),
    ("d1","D1 Campestre",         "Cl 30 #45-22, Cartagena Campestre",                    10.4080,-75.5135),
    ("d1","D1 San José Campanos", "Cll 10 #56B-227, San José de los Campanos",            10.3980,-75.4720),
    ("d1","D1 Alcibia",           "Cr 91 31I-45 Lote 16, Alcibia",                        10.4250,-75.4850),
    ("d1","D1 Fredonia",          "Cl 31 #31A-135, Fredonia",                             10.4060,-75.5060),
    ("d1","D1 Paladium",          "Cl 32B #80-45, C.C. Paladium",                         10.4130,-75.5050),
    ("d1","D1 Hipercenter",       "Cr 67 #32A-64, Hipercenter",                           10.4110,-75.5115),
    ("d1","D1 Alto Bosque",       "Cl 31D #51-55, Alto Bosque",                           10.4155,-75.5185),
    ("d1","D1 La Boquilla",       "Calle 12C #53-14, La Boquilla",                        10.4520,-75.4990),
    ("d1","D1 El Bosque",         "Sector 1B Nav 1P, El Bosque",                          10.4178,-75.5222),
    ("d1","D1 Manga",             "Cl 25 #20-45, Manga",                                  10.4058,-75.5290),
    ("d1","D1 Bocagrande",        "Calle 6 #3-59, Bocagrande",                            10.3910,-75.5530),
    ("d1","D1 Crisanto Luque",    "Diagonal 22 #40-55, Crisanto Luque",                   10.3992,-75.5268),
    # ── OLÍMPICA (19) ──────────────────────────────────────────────
    ("olimpica","Olímpica Omniplaza",         "Av. Pedro De Heredia Cl. 30, Omniplaza",         10.4048,-75.5140),
    ("olimpica","Olímpica Buenos Aires",      "Trans 54 #41-241, C.C. Buenos Aires",            10.4143,-75.4988),
    ("olimpica","Olímpica Outlet El Bosque",  "C.C. Outlet El Bosque Local 1",                  10.4172,-75.5238),
    ("olimpica","Olímpica Amberes",           "Cl. 30 #4281-42a, Amberes",                      10.4095,-75.5100),
    ("olimpica","Olímpica San Fernando",      "Carrera 83 #22B-234, San Fernando",              10.3948,-75.4790),
    ("olimpica","Olímpica Olaya Plaza",       "Transversal 66 #32-150, C.C. Olaya Plaza",       10.4085,-75.5060),
    ("olimpica","Olímpica Castellana Mall",   "Calle 30 #65-20, C.C. Castellana Mall",          10.4195,-75.5322),
    ("olimpica","Olímpica Santa Mónica",      "Carrera 71 Mz 3-112, Santa Mónica",              10.4240,-75.5140),
    ("olimpica","Olímpica SAO San Felipe",    "Calle 29B #17-109, C.C. San Felipe",             10.4008,-75.5172),
    ("olimpica","Olímpica 13 de Junio",       "Diagonal 32 #70-33, Ricaurte",                   10.4098,-75.5070),
    ("olimpica","Olímpica La Plazuela",       "Diagonal 31 #71-130, C.C. La Plazuela",          10.4030,-75.5155),
    ("olimpica","Olímpica Parque Heredia",    "Diagonal 32 #80-547, C.C. Parque Heredia",       10.4020,-75.5090),
    ("olimpica","Olímpica Bazurto",           "Av. Pedro Heredia, Calle 32 #26-104",            10.4035,-75.5200),
    ("olimpica","Olímpica La Española",       "Carrera 17 #38A, Torices",                       10.4155,-75.5350),
    ("olimpica","Olímpica Blas de Lezo",      "Carrera 3 Este #20A-19 Sur, Blas de Lezo",       10.3870,-75.4920),
    ("olimpica","Olímpica Alcibia",           "Calle 31 #39-260, Av. Pedro de Heredia",         10.4118,-75.5180),
    ("olimpica","Olímpica Villas Candelaria", "Trans. 54 #106-99, Villas de la Candelaria",     10.4195,-75.4942),
    ("olimpica","Olímpica Manga",             "Calle 26 #18B-64, Manga",                        10.4055,-75.5300),
    ("olimpica","Olímpica SAO Gran Manzana",  "Trans. 54 #91-95 local A01, La Carolina",        10.4210,-75.4940),
]

# (clave, nombre, emoji, marca, categoria, unidad, cantidad,
#  precio_exito, precio_jumbo, precio_d1, precio_ara, precio_olimpica)
PRODUCTOS_DATA = [
    # Aceites y grasas
    ("aceite-vegetal-1l",   "Aceite Vegetal 1L",             "🫙","Génesis",     "Aceites y grasas",    "ml",1000,  8900, 9400, 7800, 9100),
    ("aceite-oliva-500ml",  "Aceite de Oliva 500ml",         "🫒","Carbonell",   "Aceites y grasas",    "ml", 500, 32000, 34500, 29500, 33500),
    # Granos y cereales
    ("arroz-diana-500g",    "Arroz Blanco 500g",             "🍚","Diana",       "Granos y cereales",   "g",  500,  2850, 3100, 2600, 2950),
    ("pasta-doria-500g",    "Pasta Spaghetti 500g",          "🍝","Doria",       "Granos y cereales",   "g",  500,  2700, 2950, 2400, 2800),
    ("avena-quaker-500g",   "Avena en Hojuelas 500g",        "🌾","Quaker",      "Granos y cereales",   "g",  500,  7200, 7800, 6500, 7500),
    ("harina-pan-1kg",      "Harina de Maíz 1kg",           "🌽","P.A.N.",      "Granos y cereales",   "g", 1000,  5900, 6400, 5200, 6100),
    ("frijoles-cabana-500g","Frijoles Cargamanto 500g",      "🫘","La Cabaña",   "Granos y cereales",   "g",  500,  4800, 5200, 4200, 5000),
    ("lentejas-500g",       "Lentejas 500g",                 "🫘","Diana",       "Granos y cereales",   "g",  500,  4200, 4600, 3700, 4400),
    ("azucar-1kg",          "Azúcar Blanca 1kg",             "🍬","Génesis",     "Granos y cereales",   "g", 1000,  4100, 4400, 3700, 4200),
    ("sal-refisal-1kg",     "Sal de Mesa 1kg",               "🧂","Refisal",     "Condimentos",         "g", 1000,  1800, 1950, 1600, 1850),
    # Lácteos
    ("leche-alqueria-1l",   "Leche Entera 1L",               "🥛","Alquería",    "Lácteos",             "ml",1000,  3200, 3450, 2900, 3300),
    ("yogur-alpina-1l",     "Yogur Entero 1L",               "🥛","Alpina",      "Lácteos",             "ml",1000,  8200, 8800, 7500, 8500),
    ("mantequilla-rama-250g","Mantequilla 250g",             "🧈","Rama",        "Lácteos",             "g",  250,  7900, 8400, 7100, 8100),
    ("queso-costeno-500g",  "Queso Costeño 500g",            "🧀","Génesis",     "Lácteos",             "g",  500, 15500, 16500, 14000, 16000),
    # Proteínas
    ("atun-lata-170g",      "Atún en Lata 170g",             "🐟","Zenú",        "Proteínas",           "g",  170,  4200, 4600, 3800, 4400),
    ("huevos-x12",          "Huevos AA x12",                 "🥚","Génesis",     "Proteínas",           "u",   12,  7200, 7800, 6800, 7500),
    ("pechuga-pollo-1kg",   "Pechuga de Pollo 1kg",          "🍗","Zenú",        "Proteínas",           "g", 1000, 12800, 13500, 11500, 13100),
    ("carne-molida-1kg",    "Carne Molida 1kg",              "🥩","Génesis",     "Proteínas",           "g", 1000, 18500, 19800, 16800, 19200),
    # Bebidas
    ("agua-cristal-600ml",  "Agua Mineral 600ml",            "💧","Cristal",     "Bebidas",             "ml", 600,  1800, 2000, 1500, 1900),
    ("gaseosa-cola-1500ml", "Gaseosa Cola 1.5L",             "🥤","Coca-Cola",   "Bebidas",             "ml",1500,  5800, 6200, 5200, 6000),
    ("jugo-hit-1l",         "Jugo de Fruta 1L",              "🧃","Hit",         "Bebidas",             "ml",1000,  4500, 4900, 4000, 4700),
    ("cafe-sello-rojo-250g","Café Molido 250g",              "☕","Sello Rojo",  "Bebidas",             "g",  250,  9800, 10400, 9100, 10100),
    # Panadería
    ("pan-bimbo-500g",      "Pan Tajado 500g",               "🍞","Bimbo",       "Panadería",           "g",  500,  6500, 6900, 5800, 6700),
    # Frutas y verduras
    ("tomate-1kg",          "Tomate Chonto 1kg",             "🍅","Génesis",     "Frutas y verduras",   "g", 1000,  3500, 3800, 3000, 3600),
    ("cebolla-1kg",         "Cebolla Cabezona 1kg",          "🧅","Génesis",     "Frutas y verduras",   "g", 1000,  2800, 3100, 2400, 2900),
    ("papa-criolla-1kg",    "Papa Criolla 1kg",              "🥔","Génesis",     "Frutas y verduras",   "g", 1000,  3200, 3500, 2800, 3300),
    # Aseo del hogar
    ("detergente-ariel-1kg","Detergente en Polvo 1kg",       "🫧","Ariel",       "Aseo del hogar",      "g", 1000, 12500, 13200, 11200, 12900),
    ("desinfectante-1l",    "Desinfectante Multiusos 1L",    "🫧","Fabuloso",    "Aseo del hogar",      "ml",1000,  6900, 7400, 6200, 7200),
    ("papel-higienico-x4",  "Papel Higiénico x4 rollos",    "🧻","Scott",       "Aseo del hogar",      "u",    4,  6800, 7200, 5900, 7000),
    ("servilletas-x200",    "Servilletas x200",              "🗒️","Familia",     "Aseo del hogar",      "u",  200,  4200, 4600, 3700, 4400),
    # Aseo personal
    ("shampoo-hs-375ml",    "Shampoo Anticaspa 375ml",       "🚿","Head & Shoulders","Aseo personal",   "ml", 375, 18900, 19800, 17200, 19200),
    ("crema-dental-75ml",   "Crema Dental Blanqueadora 75ml","🦷","Colgate",     "Aseo personal",       "ml",  75,  5800, 6300, 5100, 6000),
    ("jabon-125g",          "Jabón de Baño 125g",            "🧼","Génesis",     "Aseo personal",       "g",  125,  2100, 2300, 1800, 2200),
]

# Factores de precio histórico por tienda (mes-5 → hoy)
HIST = {
    "exito":    [1.036, 1.026, 1.016, 1.008, 1.002, 1.000],
    "jumbo":    [1.040, 1.030, 1.020, 1.010, 1.003, 1.000],
    "d1":       [1.032, 1.024, 1.015, 1.007, 1.002, 1.000],
    "olimpica": [1.038, 1.028, 1.018, 1.009, 1.002, 1.000],
}


# ══════════════════════════════════════════════════════════════════════
#  INICIALIZACIÓN
# ══════════════════════════════════════════════════════════════════════
def init_db():
    """Crea las tablas y siembra los datos si la BD está vacía."""
    conn = get_connection()
    create_tables(conn)
    _seed(conn)
    conn.close()


def _seed(conn: sqlite3.Connection):
    cur = conn.cursor()
    if cur.execute("SELECT COUNT(*) FROM tiendas").fetchone()[0] > 0:
        return  # ya sembrada

    # Categorías
    cur.executemany("INSERT OR IGNORE INTO categorias(nombre) VALUES(?)",
                    [(c,) for c in CATEGORIAS_DATA])

    # Marcas
    cur.executemany("INSERT OR IGNORE INTO marcas(nombre) VALUES(?)",
                    [(m,) for m in MARCAS_DATA])

    # Tiendas
    cur.executemany("INSERT OR IGNORE INTO tiendas VALUES(?,?,?,?)", TIENDAS_DATA)

    # Sucursales
    cur.executemany(
        "INSERT INTO sucursales(tienda_id,nombre,direccion,lat,lng) VALUES(?,?,?,?,?)",
        SUCURSALES_DATA,
    )

    # Productos + precios históricos
    tienda_ids = [t[0] for t in TIENDAS_DATA]  # ara ya no está en TIENDAS_DATA
    today      = date.today()
    fechas     = [today - timedelta(days=30 * (5 - i)) for i in range(6)]

    for row in PRODUCTOS_DATA:
        clave, nombre, emoji, marca_nombre, cat_nombre, unidad, cantidad = row[:7]
        precios_hoy = dict(zip(tienda_ids, row[7:]))

        marca_id = cur.execute(
            "SELECT id FROM marcas WHERE nombre=?", (marca_nombre,)
        ).fetchone()[0]
        cat_id = cur.execute(
            "SELECT id FROM categorias WHERE nombre=?", (cat_nombre,)
        ).fetchone()[0]

        cur.execute(
            """INSERT OR IGNORE INTO productos
               (clave,nombre,emoji,marca_id,categoria_id,unidad,cantidad)
               VALUES(?,?,?,?,?,?,?)""",
            (clave, nombre, emoji, marca_id, cat_id, unidad, cantidad),
        )
        prod_id = cur.execute(
            "SELECT id FROM productos WHERE clave=?", (clave,)
        ).fetchone()[0]

        for tid, precio_actual in precios_hoy.items():
            for i, fecha in enumerate(fechas):
                precio_hist = int(round(precio_actual * HIST[tid][i]))
                cur.execute(
                    """INSERT OR IGNORE INTO precios
                       (producto_id,tienda_id,precio,fecha) VALUES(?,?,?,?)""",
                    (prod_id, tid, precio_hist, fecha.isoformat()),
                )

    conn.commit()


# ══════════════════════════════════════════════════════════════════════
#  QUERIES PÚBLICAS
# ══════════════════════════════════════════════════════════════════════
def get_tiendas() -> list[dict]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM tiendas").fetchall()]


def get_sucursales(tienda_id: str) -> list[dict]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM sucursales WHERE tienda_id=? ORDER BY nombre",
            (tienda_id,),
        ).fetchall()]


def get_sucursales_cercanas(tienda_id: str, lat: float, lng: float, top: int = 3) -> list[dict]:
    suc = get_sucursales(tienda_id)
    for s in suc:
        s["distancia"] = _haversine(lat, lng, s["lat"], s["lng"])
    return sorted(suc, key=lambda x: x["distancia"])[:top]


def buscar_productos(query: str) -> list[dict]:
    """
    Devuelve productos ordenados por relevancia:
    1. Nombre empieza con el query  → prioridad máxima
    2. Clave empieza con el query
    3. Nombre contiene el query
    4. Match en marca/categoría     → prioridad mínima
    Dentro de cada nivel, prioriza el producto con más tiendas con precio.
    """
    q_exact = query.strip().lower()
    q_like  = f"%{q_exact}%"
    q_start = f"{q_exact}%"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT p.*, m.nombre AS marca, c.nombre AS categoria,
               CASE
                 WHEN LOWER(p.nombre) LIKE ? THEN 1
                 WHEN LOWER(p.clave)  LIKE ? THEN 2
                 WHEN LOWER(p.nombre) LIKE ? THEN 3
                 ELSE 4
               END AS relevancia,
               (SELECT COUNT(DISTINCT tienda_id) FROM precios
                WHERE producto_id = p.id) AS n_tiendas
               FROM productos p
               LEFT JOIN marcas     m ON m.id = p.marca_id
               LEFT JOIN categorias c ON c.id = p.categoria_id
               WHERE LOWER(p.clave)   LIKE ?
                  OR LOWER(p.nombre)  LIKE ?
                  OR LOWER(m.nombre)  LIKE ?
                  OR LOWER(c.nombre)  LIKE ?
               ORDER BY relevancia ASC, n_tiendas DESC, LENGTH(p.nombre) ASC""",
            (q_start, q_start, q_like, q_like, q_like, q_like, q_like),
        ).fetchall()]


def get_producto_por_clave(clave: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT p.*, m.nombre AS marca, c.nombre AS categoria
               FROM productos p
               LEFT JOIN marcas     m ON m.id = p.marca_id
               LEFT JOIN categorias c ON c.id = p.categoria_id
               WHERE p.clave=?""",
            (clave,),
        ).fetchone()
        return dict(row) if row else None


def get_precios_actuales(producto_id: int) -> list[dict]:
    """Precio más reciente por tienda, ordenado de menor a mayor."""
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT pr.tienda_id, pr.precio, pr.fecha,
                      t.nombre AS tienda_nombre, t.color, t.bg
               FROM precios pr
               JOIN tiendas t ON t.id = pr.tienda_id
               WHERE pr.producto_id = ?
                 AND pr.fecha = (
                     SELECT MAX(p2.fecha) FROM precios p2
                     WHERE p2.producto_id = pr.producto_id
                       AND p2.tienda_id   = pr.tienda_id
                 )
               ORDER BY pr.precio ASC""",
            (producto_id,),
        ).fetchall()]


def get_historial(producto_id: int) -> dict[str, list[dict]]:
    """Historial completo agrupado por tienda → [{precio, fecha}, …]"""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT tienda_id, precio, fecha
               FROM precios WHERE producto_id=?
               ORDER BY tienda_id, fecha ASC""",
            (producto_id,),
        ).fetchall()
    result: dict[str, list] = {}
    for r in rows:
        result.setdefault(r["tienda_id"], []).append(
            {"precio": r["precio"], "fecha": r["fecha"]}
        )
    return result


def get_producto_por_clave(clave: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT p.*, m.nombre AS marca, c.nombre AS categoria
               FROM productos p
               LEFT JOIN marcas     m ON m.id = p.marca_id
               LEFT JOIN categorias c ON c.id = p.categoria_id
               WHERE p.clave=?""",
            (clave,),
        ).fetchone()
        return dict(row) if row else None


def get_todos_productos() -> list[dict]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT p.*, m.nombre AS marca, c.nombre AS categoria
               FROM productos p
               LEFT JOIN marcas     m ON m.id = p.marca_id
               LEFT JOIN categorias c ON c.id = p.categoria_id
               ORDER BY c.nombre, p.nombre"""
        ).fetchall()]


def get_categorias() -> list[str]:
    with get_connection() as conn:
        return [r["nombre"] for r in conn.execute(
            "SELECT nombre FROM categorias ORDER BY nombre"
        ).fetchall()]


def generar_clave(nombre: str) -> str:
    """Convierte un nombre de producto en un slug único para la columna clave."""
    import re as _re
    c = nombre.lower().strip()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n"),("ü","u")]:
        c = c.replace(a, b)
    c = _re.sub(r"[^a-z0-9\s]", "", c)
    c = _re.sub(r"\s+", "-", c.strip())
    return c[:80]


def insertar_precio(producto_id: int, tienda_id: str, precio: int, fecha: str | None = None):
    """Inserta o actualiza un precio. Úsalo desde el scraper."""
    fecha = fecha or date.today().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO precios(producto_id,tienda_id,precio,fecha) VALUES(?,?,?,?)
               ON CONFLICT(producto_id,tienda_id,fecha) DO UPDATE SET precio=excluded.precio""",
            (producto_id, tienda_id, precio, fecha),
        )
        conn.commit()


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Ejecución directa: inicializar y mostrar estadísticas ──
if __name__ == "__main__":
    init_db()
    with get_connection() as conn:
        stats = {
            "categorias": conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0],
            "marcas":      conn.execute("SELECT COUNT(*) FROM marcas").fetchone()[0],
            "tiendas":     conn.execute("SELECT COUNT(*) FROM tiendas").fetchone()[0],
            "sucursales":  conn.execute("SELECT COUNT(*) FROM sucursales").fetchone()[0],
            "productos":   conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0],
            "precios":     conn.execute("SELECT COUNT(*) FROM precios").fetchone()[0],
        }
    for k, v in stats.items():
        print(f"  {k:<12} {v:>4} registros")
    print(f"\n  DB guardada en: {DB_PATH}")
