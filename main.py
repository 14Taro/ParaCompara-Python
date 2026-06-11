"""
main.py — Para&Compara · Flask + HTML
======================================
Servidor web Flask que sirve la app directamente en el navegador.
Sin Flutter, sin Canvas, sin bloques grises.

EJECUTAR:
    python main.py
    Abrir: http://localhost:8080

DEPENDENCIAS:
    pip install flask
"""

import math
import json
from flask import Flask, jsonify, request, render_template_string
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (
    init_db, get_tiendas, buscar_productos,
    get_precios_actuales, get_historial,
    get_todos_productos, get_sucursales_cercanas,
    get_categorias,
)

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@app.route("/api/buscar")
def api_buscar():
    import re as _re
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    # Rechazar si es solo números, símbolos o muy corto
    if len(q) < 2:
        return jsonify([])
    if _re.fullmatch(r"[\d\s\.\,\-\+\*\/\(\)\#\@\!\?\%]+", q):
        return jsonify([])
    # Rechazar si no tiene ninguna letra
    if not _re.search(r"[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]", q):
        return jsonify([])
    results = buscar_productos(q)
    return jsonify([dict(r) for r in results[:10]])

@app.route("/api/precios/<int:producto_id>")
def api_precios(producto_id):
    rows = get_precios_actuales(producto_id)
    return jsonify([dict(r) for r in rows])

@app.route("/api/historial/<int:producto_id>")
def api_historial(producto_id):
    hist = get_historial(producto_id)
    return jsonify(hist)

@app.route("/api/tiendas")
def api_tiendas():
    return jsonify([dict(t) for t in get_tiendas()])

@app.route("/api/productos")
def api_productos():
    prods = get_todos_productos()
    return jsonify([dict(p) for p in prods])

@app.route("/api/sucursales_cercanas")
def api_sucursales():
    tienda_id = request.args.get("tienda_id")
    lat = float(request.args.get("lat", 0))
    lng = float(request.args.get("lng", 0))
    top = int(request.args.get("top", 3))
    if not tienda_id or not lat or not lng:
        return jsonify([])
    rows = get_sucursales_cercanas(tienda_id, lat, lng, top)
    return jsonify([dict(r) for r in rows])

@app.route("/api/lista", methods=["POST"])
def api_lista():
    data    = request.get_json()
    items   = data.get("items", [])
    user_lat = data.get("lat")
    user_lng = data.get("lng")
    tiendas = {t["id"]: dict(t) for t in get_tiendas()}
    tids    = list(tiendas.keys())
    result  = []

    for inp in items:
        prods = buscar_productos(inp)
        if not prods:
            result.append({"input": inp, "found": False})
            continue
        prod   = dict(prods[0])
        precios_map = {r["tienda_id"]: r["precio"]
                       for r in get_precios_actuales(prod["id"])}
        prod["precios"] = precios_map
        result.append({"input": inp, "found": True, "producto": prod})

    # Totales por tienda
    totals = {}
    for tid in tids:
        totals[tid] = sum(
            it["producto"]["precios"].get(tid, 0)
            for it in result if it["found"]
        )

    sorted_t   = sorted(totals.items(), key=lambda x: x[1])
    best_id    = sorted_t[0][0]
    best_total = sorted_t[0][1]
    worst_total = sorted_t[-1][1]
    ahorro     = worst_total - best_total
    pct_ahorro = round(ahorro / worst_total * 100) if worst_total else 0

    found_items = [it for it in result if it["found"]]
    cheaper = sum(
        1 for it in found_items
        if it["producto"]["precios"] and
           min(it["producto"]["precios"].items(), key=lambda x: x[1])[0] == best_id
    )
    pct_cheaper = round(cheaper / len(found_items) * 100) if found_items else 0

    # Sucursales cercanas
    nearest = {}
    if user_lat and user_lng:
        for tid in tids:
            suc = get_sucursales_cercanas(tid, user_lat, user_lng, 3)
            nearest[tid] = [dict(s) for s in suc]

    return jsonify({
        "items":       result,
        "totals":      totals,
        "sorted":      sorted_t,
        "best_id":     best_id,
        "best_total":  best_total,
        "worst_total": worst_total,
        "ahorro":      ahorro,
        "pct_ahorro":  pct_ahorro,
        "pct_cheaper": pct_cheaper,
        "nearest":     nearest,
        "tiendas":     tiendas,
    })


# ══════════════════════════════════════════════════════════════════════
#  HTML FRONTEND
# ══════════════════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Para&amp;Compara · Cartagena</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#06101e;--sur:#0d1a2e;--sur2:#091525;--brd:#1a2e48;--acc:#00e5a0;--acc2:#0066ff;--txt:#e8f0ff;--mut:#4a6a8a;--mut2:#2a3e58;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--txt);font-family:'DM Sans',sans-serif;min-height:100vh;}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 60% 40% at 15% 5%,rgba(0,229,160,.06) 0%,transparent 60%),radial-gradient(ellipse 50% 50% at 85% 80%,rgba(0,100,255,.05) 0%,transparent 60%);pointer-events:none;z-index:0;}
.wrap{max-width:960px;margin:0 auto;padding:0 20px;position:relative;z-index:1;}

/* HEADER */
header{border-bottom:1px solid var(--brd);padding:16px 0;}
.header-inner{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;}
.logo{display:flex;align-items:center;gap:10px;}
.logo-icon{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,var(--acc),var(--acc2));display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}
.logo-text{font-family:'Syne',sans-serif;font-weight:800;font-size:1.3rem;line-height:1;}
.logo-text span{color:var(--acc);}
.logo-sub{font-size:10px;color:var(--mut2);letter-spacing:.8px;text-transform:uppercase;margin-top:2px;}
.geo-btn{background:var(--sur);border:1px solid var(--brd);border-radius:20px;padding:7px 14px;font-size:12px;color:var(--mut);cursor:pointer;transition:all .2s;display:flex;align-items:center;gap:6px;}
.geo-btn:hover{border-color:var(--acc);color:var(--acc);}
.geo-btn.active{border-color:var(--acc);color:var(--acc);background:rgba(0,229,160,.08);}

/* HERO */
.hero{padding:40px 0 28px;text-align:center;}
.hero-tag{font-size:10px;color:var(--acc);text-transform:uppercase;letter-spacing:2.5px;font-weight:600;margin-bottom:12px;}
.hero h1{font-family:'Syne',sans-serif;font-size:clamp(1.8rem,5vw,2.8rem);font-weight:800;line-height:1.12;letter-spacing:-1.5px;margin-bottom:10px;}
.hero h1 em{font-style:normal;color:var(--acc);}
.hero p{color:var(--mut);font-size:14px;max-width:460px;margin:0 auto;line-height:1.75;}

/* MAIN TABS */
.main-tabs{display:flex;gap:4px;background:var(--sur);border:1px solid var(--brd);border-radius:13px;padding:4px;width:fit-content;margin:24px auto;}
.main-tab{background:none;border:none;border-radius:10px;padding:9px 20px;color:var(--mut);font-family:'DM Sans',sans-serif;font-size:14px;cursor:pointer;font-weight:500;transition:all .2s;}
.main-tab.active{background:var(--acc);color:#06101e;font-weight:700;}

/* PAGES */
.page{display:none;}
.page.active{display:block;}

/* SEARCH */
.search-row{display:flex;gap:10px;margin-bottom:12px;}
.search-input-wrap{flex:1;position:relative;}
.search-input-wrap svg{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--mut);pointer-events:none;}
#searchInput{width:100%;background:var(--sur);border:1.5px solid var(--brd);border-radius:12px;padding:12px 14px 12px 42px;color:var(--txt);font-family:'DM Sans',sans-serif;font-size:15px;outline:none;transition:border-color .2s;}
#searchInput:focus{border-color:var(--acc);}
#searchInput::placeholder{color:var(--mut2);}
.btn{background:var(--acc);color:#06101e;border:none;border-radius:12px;padding:12px 22px;font-family:'Syne',sans-serif;font-weight:800;font-size:14px;cursor:pointer;transition:transform .15s,box-shadow .2s;white-space:nowrap;}
.btn:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(0,229,160,.3);}
.btn-outline{background:var(--sur);border:1.5px solid var(--brd);border-radius:12px;padding:11px 18px;color:var(--mut);font-size:13px;cursor:pointer;transition:all .2s;white-space:nowrap;}
.btn-outline:hover{border-color:var(--acc);color:var(--acc);}

/* CHIPS */
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:24px;}
.chip{background:var(--sur);border:1px solid var(--brd);border-radius:20px;padding:5px 13px;font-size:13px;color:var(--mut);cursor:pointer;transition:all .2s;}
.chip:hover{border-color:var(--acc);color:var(--acc);background:rgba(0,229,160,.06);}

/* INNER TABS */
.inner-tabs{display:flex;gap:4px;background:var(--sur);border:1px solid var(--brd);border-radius:11px;padding:4px;width:fit-content;margin-bottom:20px;}
.inner-tab{background:none;border:none;border-radius:8px;padding:7px 16px;color:var(--mut);font-size:13px;cursor:pointer;font-weight:500;transition:all .2s;}
.inner-tab.active{background:var(--acc);color:#06101e;font-weight:700;}

/* STORE CARDS */
.store-card{background:var(--sur);border:1.5px solid var(--brd);border-radius:15px;padding:15px 18px;display:flex;align-items:center;gap:13px;cursor:pointer;position:relative;overflow:hidden;transition:transform .18s,box-shadow .18s;margin-bottom:10px;}
.store-card:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(0,0,0,.3);}
.store-card.best{border-color:var(--acc);background:linear-gradient(135deg,rgba(0,229,160,.07),var(--sur));}
.store-card.best::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--acc),var(--acc2));}
.best-badge{background:var(--acc);color:#06101e;font-size:10px;font-weight:800;padding:3px 9px;border-radius:20px;letter-spacing:.4px;white-space:nowrap;display:inline-block;margin-bottom:4px;}
.rank{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;flex-shrink:0;}
.rank-1{background:rgba(0,229,160,.18);color:var(--acc);}
.rank-2{background:rgba(77,166,255,.16);color:#4da6ff;}
.rank-3{background:rgba(255,159,64,.14);color:#ff9f40;}
.rank-n{background:rgba(255,255,255,.06);color:var(--mut);}
.store-logo{width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;flex-shrink:0;}
.store-info{flex:1;min-width:0;}
.store-name{font-weight:700;font-size:14px;margin-bottom:2px;}
.store-prod{font-size:12px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.price-block{text-align:right;flex-shrink:0;}
.price-main{font-family:'Syne',sans-serif;font-weight:800;font-size:20px;line-height:1;}
.price-unit{font-size:11px;color:var(--mut);margin-top:2px;}
.price-unit strong{color:var(--acc);}

/* TAGS */
.tag{display:inline-block;background:var(--sur2);border:1px solid var(--brd);border-radius:6px;padding:2px 8px;font-size:10px;color:var(--mut);margin-right:5px;}
.tag.accent{color:var(--acc);}

/* HISTORIAL */
.chart-wrap{background:var(--sur);border:1.5px solid var(--brd);border-radius:16px;padding:22px;margin-bottom:16px;}
.chart-header{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;margin-bottom:18px;}
.chart-title{font-family:'Syne',sans-serif;font-weight:700;font-size:15px;}
.chart-title span{color:var(--acc);}
.chart-sub{font-size:11px;color:var(--mut);margin-top:3px;}
.store-filters{display:flex;flex-wrap:wrap;gap:6px;}
.f-chip{padding:4px 11px;border-radius:20px;font-size:11px;font-weight:500;cursor:pointer;border:1.5px solid;transition:all .18s;opacity:.4;}
.f-chip.on{opacity:1;}
.stats-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px;}
.stat-box{background:var(--sur2);border:1px solid var(--brd);border-radius:10px;padding:12px;text-align:center;}
.stat-label{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;}
.stat-val{font-family:'Syne',sans-serif;font-weight:800;font-size:16px;}

/* LISTA */
.lista-wrap{background:var(--sur);border:1.5px solid var(--brd);border-radius:16px;padding:18px;margin-bottom:20px;}
.lista-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;}
.label-xs{font-size:10px;color:var(--mut2);text-transform:uppercase;letter-spacing:1.2px;font-weight:600;margin-bottom:4px;}
#listaInput{width:100%;background:var(--sur2);border:1.5px solid var(--brd);border-radius:12px;padding:12px 14px;color:var(--txt);font-family:'DM Sans',sans-serif;font-size:14px;outline:none;resize:vertical;min-height:140px;line-height:1.7;}
#listaInput:focus{border-color:var(--acc);}
#listaInput::placeholder{color:var(--mut2);}
.lista-btns{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap;}
.catalog-chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:12px;}
.cat-chip{background:var(--sur2);border:1px solid var(--brd);border-radius:7px;padding:3px 8px;font-size:10px;color:var(--mut);}

/* RESULTADO LISTA */
.banner{background:rgba(0,229,160,.08);border:1.5px solid var(--acc);border-radius:16px;padding:22px;margin-bottom:18px;position:relative;overflow:hidden;}
.banner::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--acc),var(--acc2));}
.banner-inner{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;}
.banner-left{}
.banner-winner{font-family:'Syne',sans-serif;font-weight:800;font-size:26px;line-height:1;margin:6px 0;}
.banner-pct{font-size:13px;color:var(--mut);margin-top:4px;}
.banner-pct strong{color:var(--txt);}
.nearest-box{background:rgba(0,0,0,.25);border-radius:10px;padding:10px 12px;margin-top:10px;font-size:12px;color:var(--txt);white-space:pre-line;}
.banner-right{text-align:right;}
.banner-label{font-size:11px;color:var(--mut);margin-bottom:3px;}
.banner-total{font-family:'Syne',sans-serif;font-weight:800;font-size:26px;color:var(--acc);}
.banner-vs{font-size:11px;color:var(--mut);margin-top:3px;}
.savings-badge{background:rgba(0,229,160,.12);border:1px solid rgba(0,229,160,.25);border-radius:10px;padding:5px 12px;display:inline-block;margin-top:6px;}
.savings-badge strong{color:var(--acc);font-size:14px;}
.savings-badge span{color:var(--mut);font-size:11px;}

/* TABLE */
.table-wrap{background:var(--sur);border:1px solid var(--brd);border-radius:14px;overflow:hidden;margin-bottom:18px;}
.table-title{padding:13px 18px;border-bottom:1px solid var(--brd);font-family:'Syne',sans-serif;font-weight:700;font-size:14px;}
.price-table{width:100%;border-collapse:collapse;font-size:13px;}
.price-table th{padding:9px 12px;text-align:left;color:var(--mut);font-size:10px;text-transform:uppercase;letter-spacing:.8px;background:var(--sur2);border-bottom:1px solid var(--brd);font-weight:600;}
.price-table td{padding:11px 12px;border-bottom:1px solid rgba(30,45,72,.5);vertical-align:middle;}
.price-table tr:last-child td{border-bottom:none;}
.price-table tr:hover td{background:rgba(255,255,255,.02);}
.price-table .total-row td{background:var(--sur2);font-weight:700;border-top:2px solid var(--brd);}
.cell-cheap{background:rgba(0,229,160,.1);border:1px solid rgba(0,229,160,.3);border-radius:7px;padding:4px 8px;display:inline-block;text-align:center;}
.cell-cheap .price{color:var(--acc);font-weight:700;}
.cell-cheap .min-tag{font-size:9px;color:var(--acc);font-weight:700;display:block;}
.cell-normal{text-align:center;color:var(--mut);}
.cell-best{text-align:center;color:var(--txt);}
.total-best{color:var(--acc);font-size:15px;font-weight:800;}
.total-ok{color:var(--mut);font-size:12px;}
.prod-cell{display:flex;align-items:center;gap:8px;}
.prod-emoji{font-size:16px;}
.prod-name{font-weight:500;color:#c8d8f0;font-size:12px;}
.prod-meta{font-size:10px;color:var(--mut);}

/* RANKING */
.ranking-title{font-family:'Syne',sans-serif;font-weight:700;font-size:14px;margin-bottom:12px;}
.rank-card{border-radius:12px;padding:14px 16px;margin-bottom:10px;border:1px solid var(--brd);background:var(--sur2);}
.rank-card.winner{background:rgba(0,229,160,.05);border-color:var(--acc);}
.rank-top{display:flex;align-items:center;gap:12px;}
.rank-num-big{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;flex-shrink:0;}
.rank-logo{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:11px;flex-shrink:0;}
.rank-info{flex:1;}
.rank-store-name{font-weight:700;font-size:14px;}
.rank-bar-wrap{height:4px;background:var(--brd);border-radius:2px;margin-top:5px;overflow:hidden;}
.rank-bar{height:100%;border-radius:2px;transition:width .6s ease;}
.rank-total{text-align:right;font-family:'Syne',sans-serif;font-weight:800;font-size:15px;}
.rank-diff{font-size:11px;color:var(--mut);}
.rank-branches{margin-top:10px;display:flex;flex-direction:column;gap:4px;}
.branch-row{display:flex;align-items:center;gap:8px;background:rgba(0,0,0,.18);border-radius:8px;padding:6px 10px;}
.branch-dot{width:3px;height:22px;border-radius:2px;flex-shrink:0;}
.branch-name{flex:1;font-size:11px;}
.branch-dist{font-size:12px;font-weight:700;white-space:nowrap;}

/* LOADER */
.loader{text-align:center;padding:40px 0;display:none;}
.dots{display:flex;gap:8px;justify-content:center;}
.dot{width:9px;height:9px;border-radius:50%;background:var(--acc);animation:pulse 1.2s ease infinite;}
.dot:nth-child(2){animation-delay:.2s;}.dot:nth-child(3){animation-delay:.4s;}
@keyframes pulse{0%,100%{transform:scale(.6);opacity:.4}50%{transform:scale(1);opacity:1}}

/* FOOTER */
footer{border-top:1px solid var(--brd);padding:18px 0;text-align:center;margin-top:40px;}
footer p{color:var(--mut2);font-size:11px;margin-bottom:3px;}
footer strong{color:var(--acc);}

/* SCROLLBAR */
::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--sur2);}::-webkit-scrollbar-thumb{background:var(--brd);border-radius:3px;}

/* OVERFLOW */
.overflow-x{overflow-x:auto;}

@media(max-width:640px){
  .banner-inner{flex-direction:column;}
  .stats-row{grid-template-columns:1fr 1fr;}
  .search-row{flex-direction:column;}
}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <div class="header-inner">
      <div class="logo">
        <div class="logo-icon">🛒</div>
        <div>
          <div class="logo-text">Para<span>&</span>Compara</div>
          <div class="logo-sub">Cartagena de Indias · 2026</div>
        </div>
      </div>
      <button class="geo-btn" id="geoBtn" onclick="pedirUbicacion()">
        <span id="geoIcon">📍</span> <span id="geoLabel">Usar mi ubicación</span>
      </button>
    </div>
  </div>
</header>

<div class="wrap">
  <section class="hero">
    <div class="hero-tag">⚡ Comparador de precios en tiempo real</div>
    <h1>Compra <em>inteligente</em>,<br>ahorra de verdad</h1>
    <p>Éxito · Jumbo · D1 · Ara · Olímpica<br>Buscá por nombre, marca o categoría.</p>
  </section>

  <div class="main-tabs">
    <button class="main-tab active" onclick="setMainTab('individual',this)">🔍 Producto individual</button>
    <button class="main-tab" onclick="setMainTab('lista',this)">🛍️ Lista de compras</button>
  </div>

  <!-- ── INDIVIDUAL ── -->
  <div class="page active" id="page-individual">
    <div class="search-row">
      <div class="search-input-wrap">
        <svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        <input id="searchInput" type="text" placeholder="ej: leche Alquería, arroz, aceite vegetal…" onkeydown="if(event.key==='Enter')doSearch()">
      </div>
      <button class="btn" onclick="doSearch()">Buscar</button>
    </div>

    <div class="loader" id="searchLoader"><div class="dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div><p style="color:var(--mut);font-size:13px;margin-top:12px;">Consultando precios…</p></div>

    <div id="searchResult"></div>
  </div>

  <!-- ── LISTA ── -->
  <div class="page" id="page-lista">
    <div class="lista-wrap">
      <div class="lista-header">
        <div>
          <div class="label-xs">📋 Tu lista de compras</div>
          <div style="font-size:13px;color:var(--mut);">Un producto por línea</div>
        </div>
        <button class="btn-outline" onclick="usarEjemplo()">Lista de ejemplo</button>
      </div>
      <textarea id="listaInput" placeholder="arroz&#10;leche&#10;aceite vegetal&#10;huevos&#10;pasta"></textarea>
      <div class="lista-btns">
        <button class="btn" style="flex:1" onclick="analizarLista()">Analizar lista →</button>
        <button class="btn-outline" onclick="pedirUbicacion()">📍 Ubicación</button>
      </div>
    </div>
    <div class="loader" id="listaLoader"><div class="dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div><p style="color:var(--mut);font-size:13px;margin-top:12px;">Comparando en todas las tiendas…</p></div>
    <div id="listaResult"></div>
  </div>
</div>

<footer>
  <div class="wrap">
    <p>Para&amp;Compara · Universidad de Cartagena · <strong>Ingeniería de Sistemas</strong> · Semestre V · 2026</p>
    <p>Daniel A. Almanza Morales · Lautaro A. Altamirano · Docente: Julio Cesar Rodriguez Ribon</p>
  </div>
</footer>

<script>
// ── CONFIG TIENDAS ────────────────────────────────────────────────
const STORE_STYLES = {
  exito:    {color:'#f5c842', bg:'#2a2200', text:'#f5c842'},
  jumbo:    {color:'#ff6b7a', bg:'#2a0007', text:'#ff6b7a'},
  d1:       {color:'#ff9f40', bg:'#2a1500', text:'#ff9f40'},
  ara:      {color:'#00d96a', bg:'#002218', text:'#00d96a'},
  olimpica: {color:'#4da6ff', bg:'#001530', text:'#4da6ff'},
};

let userLat = null, userLng = null;
let allProds = [], allTiendas = [];
let chartInstance = null;
let activeFilters = {};

// ── INIT ──────────────────────────────────────────────────────────
async function init() {
  const [prods, tiendas] = await Promise.all([
    fetch('/api/productos').then(r => r.json()),
    fetch('/api/tiendas').then(r => r.json()),
  ]);
  allProds   = prods;
  allTiendas = tiendas;
}

// ── TABS ──────────────────────────────────────────────────────────
function setMainTab(tab, btn) {
  document.querySelectorAll('.main-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + tab).classList.add('active');
}

// ── GEO ───────────────────────────────────────────────────────────
function pedirUbicacion() {
  if (!navigator.geolocation) return;
  document.getElementById('geoLabel').textContent = 'Obteniendo…';
  navigator.geolocation.getCurrentPosition(pos => {
    userLat = pos.coords.latitude;
    userLng = pos.coords.longitude;
    document.getElementById('geoBtn').classList.add('active');
    document.getElementById('geoIcon').textContent = '✓';
    document.getElementById('geoLabel').textContent = 'Ubicación activa';
  }, () => {
    document.getElementById('geoLabel').textContent = 'No disponible';
  });
}

// ── CHIPS ─────────────────────────────────────────────────────────
function usarEjemplo() {
  document.getElementById('listaInput').value = 'arroz\nleche\naceite vegetal\nhuevos\npasta\nazúcar\npollo\nqueso costeño';
}

// ── BÚSQUEDA INDIVIDUAL ───────────────────────────────────────────
async function doSearch() {
  const q = document.getElementById('searchInput').value.trim();
  if (!q) return;
  // Rechazar si es solo números, símbolos o no tiene letras
  if (!/[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]/i.test(q)) {
    document.getElementById('searchLoader').style.display = 'none';
    document.getElementById('searchResult').innerHTML =
      '<p style="color:var(--mut);font-size:13px;padding:10px 0;">⚠ Ingresá el nombre de un producto para buscar.</p>';
    return;
  }
  if (q.length < 2) return;

  document.getElementById('searchLoader').style.display = 'block';
  document.getElementById('searchResult').innerHTML = '';

  const results = await fetch('/api/buscar?q=' + encodeURIComponent(q)).then(r => r.json());
  document.getElementById('searchLoader').style.display = 'none';

  if (!results.length) {
    document.getElementById('searchResult').innerHTML =
      '<p style="color:var(--mut);font-size:13px;">No se encontró ningún producto.</p>';
    return;
  }

  const prod = results[0];
  const [precios, historial] = await Promise.all([
    fetch('/api/precios/' + prod.id).then(r => r.json()),
    fetch('/api/historial/' + prod.id).then(r => r.json()),
  ]);

  const altHtml = results.length > 1
    ? `<p style="font-size:11px;color:var(--mut);margin-bottom:6px;">También encontrado:</p>
       <div class="chips">${results.slice(1,5).map(r =>
         `<span class="chip" onclick="loadProd(${r.id})">${r.emoji} ${r.nombre}</span>`
       ).join('')}</div>` : '';

  document.getElementById('searchResult').innerHTML = `
    <div class="inner-tabs">
      <button class="inner-tab active" id="itab-comp" onclick="setInnerTab('comp',this)">📊 Comparar precios</button>
      <button class="inner-tab" id="itab-hist" onclick="setInnerTab('hist',this)">📈 Historial</button>
    </div>
    <div id="inner-comp">${renderComparar(prod, precios)}</div>
    <div id="inner-hist" style="display:none">${renderHistorial(prod, historial)}</div>
    ${altHtml}
  `;

  // Init chart
  initChart(prod, historial);
  window.scrollTo({top: document.getElementById('searchResult').offsetTop - 20, behavior:'smooth'});
}

async function loadProd(id) {
  const prod = allProds.find(p => p.id === id);
  if (!prod) return;
  const [precios, historial] = await Promise.all([
    fetch('/api/precios/' + id).then(r => r.json()),
    fetch('/api/historial/' + id).then(r => r.json()),
  ]);
  document.getElementById('inner-comp').innerHTML = renderComparar(prod, precios);
  document.getElementById('inner-hist').innerHTML = renderHistorial(prod, historial);
  initChart(prod, historial);
}

function setInnerTab(tab, btn) {
  document.querySelectorAll('.inner-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('inner-comp').style.display = tab === 'comp' ? 'block' : 'none';
  document.getElementById('inner-hist').style.display = tab === 'hist' ? 'block' : 'none';
  if (tab === 'hist') setTimeout(() => {
    const c = document.getElementById('priceChart');
    if (c && c._chartInstance) c._chartInstance.resize();
  }, 50);
}

// ── RENDER COMPARAR ───────────────────────────────────────────────
function renderComparar(prod, precios) {
  const rankClasses = ['rank-1','rank-2','rank-3','rank-n','rank-n'];
  return precios.map((p, i) => {
    const s = STORE_STYLES[p.tienda_id] || {color:'#fff',bg:'#111',text:'#fff'};
    const pu = (p.precio / prod.cantidad).toFixed(1);
    const isBest = i === 0;
    return `
      <div class="store-card${isBest ? ' best' : ''}">
        <div class="rank ${rankClasses[i] || 'rank-n'}">#${i+1}</div>
        <div class="store-logo" style="background:${s.bg};color:${s.text}">${p.tienda_nombre.slice(0,2)}</div>
        <div class="store-info">
          <div class="store-name" style="color:${s.color}">${p.tienda_nombre}</div>
          <div class="store-prod">${prod.nombre}</div>
        </div>
        <div class="price-block">
          ${isBest ? '<div class="best-badge">🏆 MEJOR PRECIO</div>' : ''}
          <div class="price-main">${fmt(p.precio)}</div>
          <div class="price-unit"><strong>${fmt(pu)}/${prod.unidad}</strong></div>
        </div>
      </div>`;
  }).join('');
}

// ── RENDER HISTORIAL ──────────────────────────────────────────────
function renderHistorial(prod, historial) {
  const tids = Object.keys(historial);
  const filters = tids.map(tid => {
    const s = STORE_STYLES[tid] || {color:'#fff'};
    const t = allTiendas.find(t => t.id === tid);
    return `<span class="f-chip on" id="fc-${tid}"
      style="color:${s.color};border-color:${s.color};background:${s.color}22"
      onclick="toggleFilter('${tid}','${prod.id}')">${t ? t.nombre : tid}</span>`;
  }).join('');

  const last = tids.map(tid => historial[tid].slice(-1)[0]?.precio || 0);
  const mn = Math.min(...last), mx = Math.max(...last);
  const avg = Math.round(last.reduce((a,b)=>a+b,0)/last.length);

  return `
    <div class="chart-wrap">
      <div class="chart-header">
        <div>
          <div class="chart-title">Evolución — <span>${prod.nombre}</span></div>
          <div class="chart-sub">Últimos 6 meses · <span class="tag accent">${prod.marca || ''}</span> <span class="tag">${prod.categoria || ''}</span></div>
        </div>
        <div class="store-filters">${filters}</div>
      </div>
      <canvas id="priceChart" height="240"></canvas>
      <div class="stats-row">
        <div class="stat-box"><div class="stat-label">Precio mínimo</div><div class="stat-val" style="color:var(--acc)">${fmt(mn)}</div></div>
        <div class="stat-box"><div class="stat-label">Precio promedio</div><div class="stat-val">${fmt(avg)}</div></div>
        <div class="stat-box"><div class="stat-label">Ahorro máximo</div><div class="stat-val" style="color:var(--acc)">${fmt(mx-mn)}</div></div>
      </div>
    </div>`;
}

// ── CHART ─────────────────────────────────────────────────────────
function fmtAxis(v) {
  if (v >= 1000000) return '$' + (v/1000000).toFixed(1) + 'M';
  if (v >= 10000)   return '$' + (v/1000).toFixed(1) + 'k';
  return '$' + Math.round(v).toLocaleString('es-CO');
}
function calcYAxis(hist) {
  const vals = Object.values(hist).flatMap(arr => arr.map(d => d.precio));
  if (!vals.length) return {};
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const rng = mx - mn || 1000;
  const mag = Math.pow(10, Math.floor(Math.log10(rng / 5)));
  const step = Math.ceil((rng / 5) / mag) * mag;
  return {
    min: Math.floor((mn - step * 0.5) / step) * step,
    max: Math.ceil((mx  + step * 0.5) / step) * step,
    ticks: { stepSize: step, color:'#4a6a8a', font:{family:'DM Sans'}, callback: v => fmtAxis(v), maxTicksLimit: 7 }
  };
}
const MESES = ['Oct','Nov','Dic','Ene','Feb','Mar'];
const SC = {exito:'#f5c842',jumbo:'#ff6b7a',d1:'#ff9f40',ara:'#00d96a',olimpica:'#4da6ff'};
let currentHistorial = {}, currentProdId = null;

function initChart(prod, historial) {
  currentHistorial = historial;
  currentProdId    = prod.id;
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  const canvas = document.getElementById('priceChart');
  if (!canvas) return;
  const datasets = Object.entries(historial).map(([tid, data]) => ({
    label:           allTiendas.find(t=>t.id===tid)?.nombre || tid,
    data:            data.map(d => d.precio),
    borderColor:     SC[tid] || '#fff',
    backgroundColor: (SC[tid] || '#fff') + '18',
    borderWidth:     2.5,
    pointBackgroundColor: SC[tid] || '#fff',
    pointRadius:     4,
    pointHoverRadius:7,
    tension:         0.4,
  }));
  chartInstance = new Chart(canvas, {
    type: 'line',
    data: { labels: MESES, datasets },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0d1525',
          borderColor: '#1a2e48',
          borderWidth: 1,
          titleColor: '#e8f0ff',
          bodyColor: '#4a6a8a',
          padding: 12,
          callbacks: { label: c => ` ${c.dataset.label}: ${fmt(c.parsed.y)}` }
        }
      },
      scales: {
        x: { grid:{color:'#1a2e48'}, ticks:{color:'#4a6a8a',font:{family:'DM Sans'}} },
        y: { grid:{color:'#1a2e48'}, ...calcYAxis(historial) }
      }
    }
  });
}

function toggleFilter(tid) {
  const chip = document.getElementById('fc-' + tid);
  const isOn = chip.classList.contains('on');
  const onCount = document.querySelectorAll('.f-chip.on').length;
  if (isOn && onCount === 1) return;
  chip.classList.toggle('on');
  chip.style.background = chip.classList.contains('on')
    ? (SC[tid]||'#fff') + '22' : 'transparent';
  // Rebuild chart with active filters
  const active = [...document.querySelectorAll('.f-chip.on')].map(c => c.id.replace('fc-',''));
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  const canvas = document.getElementById('priceChart');
  if (!canvas) return;
  const datasets = active.map(t => ({
    label:           allTiendas.find(x=>x.id===t)?.nombre || t,
    data:            (currentHistorial[t]||[]).map(d => d.precio),
    borderColor:     SC[t] || '#fff',
    backgroundColor: (SC[t]||'#fff') + '18',
    borderWidth: 2.5,
    pointBackgroundColor: SC[t]||'#fff',
    pointRadius: 4, pointHoverRadius: 7, tension: 0.4,
  }));
  chartInstance = new Chart(canvas, {
    type:'line', data:{labels:MESES, datasets},
    options:{responsive:true,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{backgroundColor:'#0d1525',borderColor:'#1a2e48',borderWidth:1,titleColor:'#e8f0ff',bodyColor:'#4a6a8a',padding:12,callbacks:{label:c=>` ${c.dataset.label}: ${fmt(c.parsed.y)}`}}},
      scales:{x:{grid:{color:'#1a2e48'},ticks:{color:'#4a6a8a',font:{family:'DM Sans'}}},
              y:{grid:{color:'#1a2e48'},...calcYAxis(currentHistorial)}}}
  });
}

// ── LISTA DE COMPRAS ──────────────────────────────────────────────
async function analizarLista() {
  const raw = document.getElementById('listaInput').value
    .split(/[\n,;]+/).map(s=>s.trim()).filter(Boolean);
  if (!raw.length) return;

  document.getElementById('listaLoader').style.display = 'block';
  document.getElementById('listaResult').innerHTML = '';

  const data = await fetch('/api/lista', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ items: raw, lat: userLat, lng: userLng }),
  }).then(r => r.json());

  document.getElementById('listaLoader').style.display = 'none';
  document.getElementById('listaResult').innerHTML = renderListaResult(data);
  window.scrollTo({top: document.getElementById('listaResult').offsetTop - 20, behavior:'smooth'});
}

function renderListaResult(d) {
  const { items, totals, sorted, best_id, best_total, worst_total,
          ahorro, pct_ahorro, pct_cheaper, nearest, tiendas } = d;

  const bestT  = tiendas[best_id];
  const bestS  = STORE_STYLES[best_id] || {color:'#fff'};
  const worstT = tiendas[sorted[sorted.length-1][0]];

  // Nearest branch
  let nearestHtml = '';
  if (nearest && nearest[best_id] && nearest[best_id].length) {
    const nb = nearest[best_id][0];
    nearestHtml = `<div class="nearest-box">📍 ${nb.nombre}\n${nb.direccion}\na ${nb.distancia.toFixed(1)} km de tu ubicación</div>`;
  } else if (!userLat) {
    nearestHtml = `<p style="font-size:12px;color:var(--mut2);margin-top:8px;">📍 Activa la ubicación para ver distancias</p>`;
  }

  // Banner
  const banner = `
    <div class="banner">
      <div class="banner-inner">
        <div class="banner-left">
          <div class="label-xs">🏆 Mejor opción para tu lista</div>
          <div class="banner-winner" style="color:${bestS.color}">${bestT.nombre}</div>
          <div class="banner-pct"><strong>${pct_cheaper}% de los productos</strong> son más baratos aquí</div>
          ${nearestHtml}
        </div>
        <div class="banner-right">
          <div class="banner-label">Total estimado</div>
          <div class="banner-total">${fmt(best_total)}</div>
          <div class="banner-vs">vs ${fmt(worst_total)} en ${worstT.nombre}</div>
          <div class="savings-badge"><strong>Ahorras ${fmt(ahorro)}</strong> <span>(${pct_ahorro}%)</span></div>
        </div>
      </div>
    </div>`;

  // Tabla
  const tids = sorted.map(([tid]) => tid);
  const thCells = tids.map(tid => {
    const s = STORE_STYLES[tid] || {color:'#fff'};
    return `<th style="color:${s.color}">${tiendas[tid].nombre}</th>`;
  }).join('');

  const bodyRows = items.map(it => {
    if (!it.found) return `
      <tr><td><span style="color:var(--mut2)">❓ ${it.input}</span></td>
      ${tids.map(() => '<td style="text-align:center;color:var(--mut2)">—</td>').join('')}</tr>`;
    const p = it.producto;
    const minP = Math.min(...Object.values(p.precios || {}).filter(x => x > 0));
    const priceCells = tids.map(tid => {
      const price = p.precios?.[tid] || 0;
      if (!price) return '<td style="text-align:center;color:var(--mut2)">—</td>';
      const cheap = price === minP;
      if (cheap) return `<td><div class="cell-cheap"><span class="price">${fmt(price)}</span><span class="min-tag">↓ MÁS BAJO</span></div></td>`;
      const cls = tid === best_id ? 'cell-best' : 'cell-normal';
      return `<td><div class="${cls}">${fmt(price)}</div></td>`;
    }).join('');
    return `<tr>
      <td><div class="prod-cell"><span class="prod-emoji">${p.emoji}</span>
        <div><div class="prod-name">${p.nombre}</div>
        <div class="prod-meta">${p.marca || ''} · ${p.cantidad}${p.unidad}</div></div>
      </div></td>${priceCells}</tr>`;
  }).join('');

  const totalCells = tids.map(tid => {
    const isBest = tid === best_id;
    const tot = totals[tid] || 0;
    return isBest
      ? `<td><div class="total-best">${fmt(tot)}<div style="font-size:9px;color:var(--acc);font-weight:700">✓ MEJOR</div></div></td>`
      : `<td><div class="total-ok">${fmt(tot)}</div></td>`;
  }).join('');

  const tabla = `
    <div class="table-wrap">
      <div class="table-title">Desglose por producto</div>
      <div class="overflow-x">
        <table class="price-table">
          <thead><tr><th>Producto</th>${thCells}</tr></thead>
          <tbody>${bodyRows}</tbody>
          <tfoot><tr class="total-row"><td>TOTAL</td>${totalCells}</tr></tfoot>
        </table>
      </div>
    </div>`;

  // Ranking
  const rankingTitle = `<div class="ranking-title">Ranking de tiendas${userLat ? ' · sucursales más cercanas' : ''}</div>`;
  const rankingCards = sorted.map(([tid, total], i) => {
    const t = tiendas[tid];
    const s = STORE_STYLES[tid] || {color:'#fff', bg:'#111', text:'#fff'};
    const pct = worst_total ? (total / worst_total * 100).toFixed(0) : 0;
    const isWinner = i === 0;
    const diff = i > 0 ? `<div class="rank-diff">+${fmt(total - best_total)}</div>` : '';

    let branchesHtml = '';
    if (nearest && nearest[tid] && nearest[tid].length) {
      branchesHtml = `<div class="rank-branches">` +
        nearest[tid].slice(0,3).map((b, bi) => `
          <div class="branch-row">
            <div class="branch-dot" style="background:${bi===0?s.color:'var(--brd)'}"></div>
            <div class="branch-name" style="color:${bi===0?s.color:'var(--mut)'};font-weight:${bi===0?'700':'400'}">${b.nombre}</div>
            <div class="branch-dist" style="color:${bi===0?'var(--acc)':'var(--mut)'}">${b.distancia.toFixed(1)} km</div>
          </div>`).join('') + `</div>`;
    } else if (!userLat) {
      branchesHtml = `<p style="font-size:11px;color:var(--mut2);margin-top:6px;">Activa la ubicación para ver sucursales</p>`;
    }

    return `
      <div class="rank-card${isWinner?' winner':''}">
        <div class="rank-top">
          <div class="rank-num-big" style="background:${isWinner?'rgba(0,229,160,.18)':'rgba(255,255,255,.05)'};color:${isWinner?'var(--acc)':'var(--mut)'}">
            #${i+1}
          </div>
          <div class="rank-logo" style="background:${s.bg};color:${s.text}">${t.nombre.slice(0,2)}</div>
          <div class="rank-info">
            <div class="rank-store-name" style="color:${s.color}">${t.nombre}</div>
            <div class="rank-bar-wrap">
              <div class="rank-bar" style="width:${pct}%;background:${isWinner?'var(--acc)':s.color}"></div>
            </div>
          </div>
          <div style="text-align:right">
            <div class="rank-total" style="color:${isWinner?'var(--acc)':'var(--txt)'}">${fmt(total)}</div>
            ${diff}
          </div>
        </div>
        ${branchesHtml}
      </div>`;
  }).join('');

  return banner + tabla + rankingTitle + rankingCards;
}

// ── UTILS ─────────────────────────────────────────────────────────
function fmt(n) {
  return '$' + Math.round(n).toLocaleString('es-CO').replace(/\./g, '.');
}

// ── START ─────────────────────────────────────────────────────────
init();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    init_db()
    print("\n" + "="*50)
    print("  Para&Compara corriendo en:")
    print("  http://localhost:8080")
    print("="*50 + "\n")
    app.run(host="0.0.0.0", port=8080, debug=False)
