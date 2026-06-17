"""Генерация интерактивной карты плотности организаций (HTML, Leaflet).

  * каждая организация — точка; цвет соответствует классу (категории поиска);
  * наложение на реальную карту (OSM + спутник Esri, переключаются);
  * линии сетки (lattice 180 м) + круг радиуса 2500 м + центр;
  * легенда-фильтр: клик по классу включает/выключает его точки.

Ключ Google Maps не нужен. Результат: analytics_out/density_map.html

Запуск:  PYTHONIOENCODING=utf-8 python 04_density_map.py
"""

from __future__ import annotations

import colorsys
import json
import math
from collections import Counter
from pathlib import Path

CENTER_LAT = 59.914403
CENTER_LON = 30.327319
RADIUS_M = 2500.0
EFFECTIVE_STEP_M = 180.0

DATA_DIR = Path(__file__).parent / "data"
OUT_DIR = Path(__file__).parent / "analytics_out"


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def palette(n: int) -> list[str]:
    """n визуально различимых цветов (равномерно по HSL)."""
    cols = []
    for i in range(n):
        h = (i / n)
        s = 0.72 if i % 2 == 0 else 0.95
        light = 0.45 if i % 3 else 0.58
        r, g, b = colorsys.hls_to_rgb(h, light, s)
        cols.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
    return cols


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = json.load((DATA_DIR / "organizations.json").open(encoding="utf-8"))
    orgs = data["organizations"]

    # класс = первая поисковая категория, под которой нашли орг
    def org_class(o) -> str:
        q = o.get("_search_queries") or []
        if q:
            return q[0]
        cats = o.get("categories") or []
        return cats[0].get("name", "прочее") if cats else "прочее"

    class_counts = Counter(org_class(o) for o in orgs)
    classes = [c for c, _ in class_counts.most_common()]
    colors = dict(zip(classes, palette(len(classes))))

    # точки для JS
    points = []
    for o in orgs:
        c = o.get("coordinates") or {}
        if c.get("lat") is None or c.get("lon") is None:
            continue
        cls = org_class(o)
        points.append({
            "lat": c["lat"], "lon": c["lon"],
            "t": o.get("title", "")[:80],
            "a": (o.get("address") or o.get("fullAddress") or "")[:90],
            "r": o.get("rating"),
            "rc": o.get("reviewsCount"),
            "d": o.get("_distance_m"),
            "c": cls,
        })

    # линии сетки (lattice): рисуем как набор горизонтальных и вертикальных
    # линий через узлы решётки, ограниченных bounding box ~ radius + запас.
    lat_step = EFFECTIVE_STEP_M / 111320.0
    lon_step = EFFECTIVE_STEP_M / (111320.0 * math.cos(math.radians(CENTER_LAT)))
    n = math.ceil(RADIUS_M / EFFECTIVE_STEP_M) + 1
    lat_min = CENTER_LAT - n * lat_step
    lat_max = CENTER_LAT + n * lat_step
    lon_min = CENTER_LON - n * lon_step
    lon_max = CENTER_LON + n * lon_step
    grid_lines = []  # [[lat1,lon1],[lat2,lon2]]
    for i in range(-n, n + 1):
        lat = CENTER_LAT + i * lat_step
        grid_lines.append([[lat, lon_min], [lat, lon_max]])      # горизонталь
    for j in range(-n, n + 1):
        lon = CENTER_LON + j * lon_step
        grid_lines.append([[lat_min, lon], [lat_max, lon]])      # вертикаль

    legend_html = "".join(
        f'<div class="leg-item" data-cls="{c}">'
        f'<span class="sw" style="background:{colors[c]}"></span>'
        f'{c} <b>({class_counts[c]})</b></div>'
        for c in classes
    )

    payload = {
        "center": [CENTER_LAT, CENTER_LON],
        "radius_m": RADIUS_M,
        "points": points,
        "grid_lines": grid_lines,
        "colors": colors,
    }

    html = _TEMPLATE.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False)) \
                    .replace("__LEGEND__", legend_html) \
                    .replace("__NPTS__", str(len(points))) \
                    .replace("__NCLS__", str(len(classes)))

    out = OUT_DIR / "density_map.html"
    out.write_text(html, encoding="utf-8")
    print(f"[+] Карта: {out}")
    print(f"    точек: {len(points)}, классов: {len(classes)}, "
          f"линий сетки: {len(grid_lines)}")
    return 0


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Плотность организаций — Яндекс.Карты грид</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  html,body{margin:0;height:100%;font-family:system-ui,Arial,sans-serif}
  #map{position:absolute;inset:0}
  #panel{position:absolute;top:10px;right:10px;z-index:1000;background:#fff;
    padding:10px 12px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.3);
    max-height:88vh;overflow:auto;width:240px;font-size:12px}
  #panel h3{margin:0 0 6px;font-size:13px}
  .leg-item{cursor:pointer;padding:2px 3px;border-radius:4px;user-select:none;
    display:flex;align-items:center;gap:6px;white-space:nowrap}
  .leg-item:hover{background:#eef}
  .leg-item.off{opacity:.32;text-decoration:line-through}
  .sw{display:inline-block;width:12px;height:12px;border-radius:50%;
    border:1px solid #0003;flex:0 0 auto}
  .ctl{margin:6px 0;font-size:12px}
  .ctl label{cursor:pointer}
  #stats{font-size:11px;color:#555;margin-top:6px;border-top:1px solid #ddd;padding-top:6px}
  .leg-btns{display:flex;gap:6px;margin:4px 0}
  .leg-btns button{flex:1;font-size:11px;cursor:pointer}
</style>
</head>
<body>
<div id="map"></div>
<div id="panel">
  <h3>Организации: __NPTS__</h3>
  <div class="ctl"><label><input type="checkbox" id="tGrid" checked> сетка 180 м</label></div>
  <div class="ctl"><label><input type="checkbox" id="tCircle" checked> радиус 2500 м</label></div>
  <div class="ctl"><label><input type="checkbox" id="tHeat"> размер ∝ отзывам</label></div>
  <div class="leg-btns"><button id="allOn">все</button><button id="allOff">снять</button></div>
  <div><b>Классы (__NCLS__):</b></div>
  <div id="legend">__LEGEND__</div>
  <div id="stats"></div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D = __PAYLOAD__;
const map = L.map('map').setView(D.center, 15);

const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19, attribution:'© OpenStreetMap'});
const sat = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {maxZoom:19, attribution:'© Esri'});
osm.addTo(map);
L.control.layers({'Схема (OSM)':osm,'Спутник (Esri)':sat}).addTo(map);

// центр + радиус
L.circleMarker(D.center,{radius:6,color:'#000',weight:2,fillColor:'#fff',
  fillOpacity:1}).addTo(map).bindPopup('Центр поиска');
const circle = L.circle(D.center,{radius:D.radius_m,color:'#d22',weight:2,
  fill:false,dashArray:'6 6'}).addTo(map);

// сетка
const gridLayer = L.layerGroup(
  D.grid_lines.map(g => L.polyline(g,{color:'#3577cc',weight:0.5,opacity:0.45}))
).addTo(map);

// точки по классам
const groups = {};       // cls -> layerGroup
const visible = {};      // cls -> bool
let heat = false;
function radiusFor(p){
  if(!heat) return 4;
  const rc = p.rc || 0;
  return 3 + Math.min(11, Math.sqrt(rc));
}
function build(){
  Object.values(groups).forEach(g=>g.clearLayers());
  D.points.forEach(p=>{
    if(!groups[p.c]){groups[p.c]=L.layerGroup().addTo(map);visible[p.c]=true;}
    const col = D.colors[p.c] || '#888';
    const m = L.circleMarker([p.lat,p.lon],{radius:radiusFor(p),color:col,
      weight:1,fillColor:col,fillOpacity:0.8});
    m.bindPopup(`<b>${p.t}</b><br>${p.a}<br>`+
      `класс: ${p.c}<br>рейтинг: ${p.r??'—'} (${p.rc??0} отз.)<br>`+
      `${p.d!=null?p.d+' м от центра':''}`);
    groups[p.c].addLayer(m);
  });
}
build();

function refreshStats(){
  let n=0; for(const c in visible){ if(visible[c]) n += groups[c].getLayers().length; }
  document.getElementById('stats').innerHTML =
    `Показано точек: <b>${n}</b> / ${D.points.length}`;
}
refreshStats();

// легенда-фильтр
document.querySelectorAll('.leg-item').forEach(el=>{
  el.addEventListener('click',()=>{
    const c = el.dataset.cls;
    visible[c] = !visible[c];
    el.classList.toggle('off',!visible[c]);
    if(visible[c]) groups[c].addTo(map); else map.removeLayer(groups[c]);
    refreshStats();
  });
});
document.getElementById('allOn').onclick=()=>{
  document.querySelectorAll('.leg-item').forEach(el=>{
    const c=el.dataset.cls; visible[c]=true; el.classList.remove('off');
    groups[c].addTo(map);}); refreshStats();
};
document.getElementById('allOff').onclick=()=>{
  document.querySelectorAll('.leg-item').forEach(el=>{
    const c=el.dataset.cls; visible[c]=false; el.classList.add('off');
    map.removeLayer(groups[c]);}); refreshStats();
};

document.getElementById('tGrid').onchange=e=>{
  if(e.target.checked) gridLayer.addTo(map); else map.removeLayer(gridLayer);};
document.getElementById('tCircle').onchange=e=>{
  if(e.target.checked) circle.addTo(map); else map.removeLayer(circle);};
document.getElementById('tHeat').onchange=e=>{
  heat=e.target.checked; build();
  for(const c in visible){ if(!visible[c]) map.removeLayer(groups[c]); }
  refreshStats();
};
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
