# Para&Compara 🛒

**Comparador de precios de supermercados en Cartagena de Indias**

Universidad de Cartagena · Facultad de Ingeniería · Ingeniería de Sistemas · Semestre V · 2026

**Autores:** Daniel A. Almanza Morales · Lautaro A. Altamirano
**Docente:** Julio Cesar Rodriguez Ribon

---

## ¿Qué hace la app?

Para&Compara permite a los usuarios comparar precios de productos de la canasta familiar en los principales supermercados de Cartagena (Éxito, Jumbo, D1, Ara y Olímpica). Sus funciones principales son:

- **Búsqueda individual** — buscá cualquier producto por nombre, marca o categoría y ve los precios ordenados de menor a mayor con el precio por unidad de medida ($/g, $/ml)
- **Historial de precios** — gráfica interactiva de los últimos 6 meses por tienda para identificar tendencias y validar promociones
- **Lista de compras** — ingresá tu lista completa y la app calcula en qué tienda te sale más barato el total, con el porcentaje de productos más baratos, el ahorro en pesos y la sucursal más cercana
- **Geolocalización** — detecta tu ubicación y muestra la distancia a cada sucursal usando la fórmula Haversine, sin depender de APIs de mapas

---

## Estructura del proyecto

```
paracompara_app/
├── main.py          ← Servidor web Flask (interfaz de usuario)
├── database.py      ← Base de datos SQLite, esquema y queries
├── scraper.py       ← Scraper automático de precios (gratuito)
├── paracompara.db   ← Base de datos (se genera automáticamente)
├── scraper.log      ← Registro de ejecuciones del scraper
└── README.md        ← Este archivo
```

---

## GUÍA DE INSTALACIÓN Y USO PASO A PASO

### PASO 1 — Verificar Python

Abrí el **Símbolo del sistema (CMD)** en Windows y ejecutá:

```cmd
python --version
```

Necesitás **Python 3.10 o superior**. Si no lo tenés instalado:

1. Entrá a **python.org/downloads**
2. Descargá el instalador de Windows
3. Durante la instalación, **tildá la opción "Add Python to PATH"** — esto es importante
4. Completá la instalación y cerrá el CMD
5. Abrí un CMD nuevo y volvé a ejecutar `python --version`

---

### PASO 2 — Ubicar los archivos del proyecto

Copiá los archivos del proyecto en una carpeta fácil de encontrar, por ejemplo:

```
C:\paracompara\
    ├── main.py
    ├── database.py
    ├── scraper.py
    └── README.md
```

---

### PASO 3 — Abrir CMD en la carpeta del proyecto

Tenés dos opciones:

**Opción A:** En el Explorador de Windows, navegá hasta `C:\paracompara`, hacé clic en la barra de direcciones, escribí `cmd` y presioná Enter.

**Opción B:** Abrí CMD normalmente y escribí:
```cmd
cd C:\paracompara
```

---

### PASO 4 — Instalar las dependencias

Ejecutá estos comandos uno por uno:

```cmd
pip install flask
pip install beautifulsoup4
pip install requests
pip install schedule
pip install lxml
```

Si vas a usar el scraper con D1 y Ara, también instalá Playwright:

```cmd
pip install playwright
python -m playwright install chromium
```

> **Nota:** La instalación de Chromium descarga ~150 MB. Solo se hace una vez.

---

### PASO 5 — Inicializar la base de datos

Este comando crea el archivo `paracompara.db` con todas las tablas, tiendas, sucursales, productos y precios iniciales:

```cmd
python database.py
```

Deberías ver algo así:

```
  categorias     10 registros
  marcas         23 registros
  tiendas         5 registros
  sucursales     48 registros
  productos      34 registros
  precios       990 registros

  DB guardada en: C:\paracompara\paracompara.db
```

---

### PASO 6 — Correr la aplicación

```cmd
python main.py
```

Deberías ver:

```
==================================================
  Para&Compara corriendo en:
  http://localhost:8080
==================================================
```

Abrí el navegador y entrá a **http://localhost:8080**

La app ya está funcionando. Podés buscar productos, comparar precios y usar la lista de compras con los datos semilla que vienen cargados.

> Para acceder desde el celular (si está en la misma red WiFi): buscá la IP de tu PC con `ipconfig` en CMD y entrá a `http://[IP-de-tu-PC]:8080` desde el celular.

---

### PASO 7 — Actualizar precios con el scraper

El scraper visita las páginas web de cada supermercado y actualiza los precios en la base de datos. Tiene dos modos:

**Modo rápido — solo actualiza precios de productos ya registrados (~10-15 min):**
```cmd
python scraper.py --only-prices
```

**Modo completo — actualiza precios Y descubre productos nuevos (~35 min):**
```cmd
python scraper.py --discover
```

**Probar que una tienda funciona antes de correr todo:**
```cmd
python scraper.py --test exito --query "leche"
python scraper.py --test jumbo --query "arroz"
python scraper.py --test d1    --query "aceite"
python scraper.py --test ara   --query "huevos"
```

**Programar ejecución automática todos los días a las 3 AM (dejar la PC encendida):**
```cmd
python scraper.py --hora 03:00
```

---

## Flujo de uso diario

```
┌─────────────────────────────────────────────────────┐
│  Cuando quieran datos frescos (recomendado 1x/día): │
│    1. Abrir CMD en C:\paracompara                   │
│    2. python scraper.py --only-prices               │
│       (esperar ~15 minutos)                         │
│                                                     │
│  Para ver la app:                                   │
│    1. Abrir CMD en C:\paracompara                   │
│    2. python main.py                                │
│    3. Abrir http://localhost:8080                   │
└─────────────────────────────────────────────────────┘
```

---

## Diseño de la base de datos

La base de datos tiene **6 tablas** con responsabilidades bien separadas:

```
categorias          marcas
──────────          ──────
id   PK             id   PK
nombre              nombre
  │                   │
  └──────┐   ┌────────┘
         ▼   ▼
       productos
       ─────────────────────────
       id            PK
       clave          ← slug buscable ('leche-alqueria-1l')
       nombre         ← nombre de exhibición
       emoji
       marca_id       FK → marcas.id
       categoria_id   FK → categorias.id
       unidad         ← 'g' | 'ml' | 'u'
       cantidad       ← 1000, 500, 12…
           │
           ▼
         precios
         ─────────────────────────
         id            PK
         producto_id   FK → productos.id
         tienda_id     FK → tiendas.id
         precio        ← COP entero (sin decimales)
         fecha         ← 'YYYY-MM-DD'
         UNIQUE(producto_id, tienda_id, fecha)

tiendas              sucursales
───────              ──────────────────────
id   PK ◄─────────── tienda_id   FK
nombre               id          PK
color                nombre
bg                   direccion
                     lat
                     lng
```

### Explicación de cada tabla

**`categorias`** — agrupa los productos por tipo (Lácteos, Granos, Aseo…). Se guarda una vez y se referencia por ID para evitar inconsistencias.

**`marcas`** — almacena las marcas comerciales (Alpina, Diana, Zenú…). Separada para poder buscar por marca y evitar errores de escritura.

**`tiendas`** — una fila por cadena de supermercados. El ID es un slug de texto (`'exito'`, `'d1'`) para hacer las queries más legibles. Los colores hex se usan directamente en la interfaz.

**`sucursales`** — cada tienda tiene N sucursales físicas con coordenadas `lat`/`lng`. La distancia al usuario se calcula con la fórmula **Haversine** en Python, sin depender de APIs de mapas externas.

**`productos`** — el catálogo de artículos. `clave` es un slug único buscable. `unidad` + `cantidad` permiten calcular el precio por gramo o mililitro para comparaciones justas entre distintas presentaciones del mismo producto.

**`precios`** — la tabla central del sistema. Cada fila es el precio de un producto en una tienda en una fecha concreta. La restricción `UNIQUE(producto_id, tienda_id, fecha)` evita duplicados. Para obtener el precio actual se consulta el `MAX(fecha)` por tienda, y el historial completo alimenta la gráfica de evolución de precios.

---

## Cómo funciona el scraper

El scraper usa **dos estrategias gratuitas** según la tienda:

| Tienda | Método | Descripción |
|--------|--------|-------------|
| Éxito | VTEX API pública | Endpoint JSON sin autenticación |
| Jumbo | VTEX Intelligent Search | API JSON pública, versión nueva |
| Olímpica | VTEX API pública | Mismo endpoint que Éxito |
| D1 | Playwright (Chromium local) | Navegador headless sin costo |
| Ara | Playwright (Chromium local) | Navegador headless sin costo |

**¿Qué pasa cuando encuentra un producto nuevo?**

En modo `--discover`, si el scraper encuentra un producto que no está en la BD, lo analiza automáticamente:
1. Verifica que sea un producto de supermercado (descarta electrónica, ropa, etc.)
2. Infiere la categoría por palabras clave
3. Extrae la marca del nombre
4. Parsea la cantidad y unidad (`'1L'` → 1000ml, `'500g'` → 500g)
5. Lo inserta en la BD con todos sus datos

El catálogo crece solo con cada ejecución sin necesidad de carga manual.

---

## Agregar un precio manualmente (desde código)

Si necesitás ingresar un precio de forma manual sin usar el scraper:

```python
from database import insertar_precio, buscar_productos

# Buscar el producto
prod = buscar_productos("leche alqueria")[0]

# Insertar precio del día
insertar_precio(
    producto_id = prod["id"],
    tienda_id   = "exito",      # exito | jumbo | d1 | ara | olimpica
    precio      = 3150,         # COP entero
    fecha       = "2026-05-20", # opcional, por defecto usa la fecha de hoy
)
```

---

## Solución de problemas comunes

**`python` no se reconoce como comando**
→ Python no está en el PATH. Reinstalarlo tildando "Add Python to PATH" durante la instalación.

**`playwright` no se reconoce**
→ Usar `python -m playwright install chromium` en vez de `playwright install chromium`.

**La app no abre en el navegador**
→ Verificar que `python main.py` esté corriendo, luego abrir manualmente `http://localhost:8080`.

**El scraper no encuentra precios en D1 o Ara**
→ Los selectores CSS pueden cambiar cuando el sitio se actualiza. Revisar con:
```cmd
python scraper.py --test d1 --query "leche"
```
Si no muestra resultados, los selectores en `PLAYWRIGHT_STORES` dentro de `scraper.py` necesitan actualizarse inspeccionando el HTML del sitio con las DevTools del navegador (F12 → clic derecho en el precio → Inspeccionar).

**El puerto 8080 ya está en uso**
→ Cambiar el puerto en la última línea de `main.py`:
```python
app.run(host="0.0.0.0", port=8081, debug=False)
```
Y abrir `http://localhost:8081`.
