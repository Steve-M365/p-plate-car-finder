"""Export the current database to a static, read-only site for GitHub Pages.

Run:  python scripts/export_static.py  [--out docs]

Writes:
  docs/index.html   - self-contained viewer (no build step, no backend)
  docs/data.js      - window.PPLATE_DATA = {...} (avoids fetch/CORS entirely)
  docs/.nojekyll    - stop Jekyll from touching the output

The real app (FastAPI + SQLite) cannot run on GitHub Pages because Pages is
static-only; this export is a read-only snapshot of the car list, stats and the
Victorian P-plate rules, regenerated on every push by .github/workflows/pages.yml.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from pplate.config import get_settings  # noqa: E402
from pplate.db import SessionLocal, init_db  # noqa: E402
from pplate.models import Car, RecommendationSource  # noqa: E402
from pplate.services import car_service, p_plate_compliance  # noqa: E402

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__APP_NAME__ - Victorian P-plate first-car finder</title>
<style>
:root{--bg:#0f172a;--panel:#1e293b;--panel2:#273549;--text:#e2e8f0;--muted:#94a3b8;--border:#334155;--accent:#38bdf8;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6;--radius:10px}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);line-height:1.45}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header.site{background:linear-gradient(90deg,#0b1220,#1e293b);border-bottom:1px solid var(--border);padding:.75rem 1.25rem;display:flex;gap:1rem;align-items:baseline;flex-wrap:wrap;position:sticky;top:0;z-index:10}
header.site .brand{font-weight:700}.muted{color:var(--muted)}.small{font-size:.8rem}
main{max-width:1400px;margin:0 auto;padding:1.25rem}
.disclaimer{background:#3b2f0b;border:1px solid #a16207;color:#fde68a;padding:.7rem .9rem;border-radius:var(--radius);font-size:.86rem;margin-bottom:1rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.75rem;margin-bottom:1.25rem}
.card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:.85rem 1rem}
.card .num{font-size:1.7rem;font-weight:700}.card .label{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);padding:1rem;margin-bottom:1.25rem}
.panel h2{margin-top:0;font-size:1.05rem}
.row{display:flex;gap:.6rem;flex-wrap:wrap;align-items:flex-end}
label{display:block;font-size:.78rem;color:var(--muted);margin-bottom:.2rem}
input,select{background:var(--panel2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:.45rem .55rem;font-size:.88rem;width:100%}
input[type=checkbox]{width:auto}.field{min-width:130px;flex:1 1 130px}.field.narrow{flex:0 0 120px}
button{background:var(--accent);color:#04121f;border:none;border-radius:6px;padding:.5rem .9rem;font-weight:600;cursor:pointer;font-size:.88rem}
button.secondary{background:var(--panel2);color:var(--text);border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:.86rem}
th,td{text-align:left;padding:.5rem .55rem;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:.76rem;text-transform:uppercase;letter-spacing:.03em;position:sticky;top:52px;background:var(--panel)}
tbody tr:hover{background:#223049}.table-wrap{overflow:auto;max-height:72vh;border:1px solid var(--border);border-radius:var(--radius)}
.badge{display:inline-block;padding:.15rem .5rem;border-radius:999px;font-size:.74rem;font-weight:700;white-space:nowrap}
.badge.compliant{background:#052e16;color:#86efac;border:1px solid #166534}
.badge.non_compliant{background:#450a0a;color:#fecaca;border:1px solid #991b1b}
.badge.unknown{background:#451a03;color:#ffedd5;border:1px solid #9a3412}
.badge.recommended{background:#172554;color:#bfdbfe;border:1px solid #1d4ed8}
.badge.source{background:var(--panel2);color:var(--muted);border:1px solid var(--border);font-weight:500}
.reason{color:var(--muted);font-size:.78rem;max-width:360px}
ul.clean{list-style:none;padding-left:0}ul.clean li{padding:.3rem 0;border-bottom:1px solid var(--border)}
</style>
</head>
<body>
<header class="site">
  <div class="brand">__APP_NAME__</div>
  <div class="small muted">Static read-only snapshot for GitHub Pages &middot; generated <span id="generated">__GENERATED__</span></div>
</header>
<main>
  <div class="disclaimer">
    <strong>Guidance only, not legal advice.</strong> This is a static snapshot; the live app (with editing,
    recommendation search and listing capture) runs locally. Always confirm the exact make/model/variant on the
    official <a id="ppv" href="#">probationary vehicle database</a> or with VicRoads. Listing data may be stale.
  </div>

  <div class="cards" id="cards"></div>

  <div class="panel">
    <h2>Filters</h2>
    <div class="row">
      <div class="field"><label for="q">Search</label><input id="q" placeholder="make / model"></div>
      <div class="field narrow"><label for="max_price">Max price (A$)</label><input id="max_price" type="number"></div>
      <div class="field narrow"><label for="body">Body</label><select id="body"></select></div>
      <div class="field narrow"><label for="fuel">Fuel</label><select id="fuel"></select></div>
      <div class="field narrow"><label for="trans">Transmission</label><select id="trans"></select></div>
      <div class="field narrow"><label for="compliance">P-plate</label><select id="compliance">
        <option value="">Any</option><option value="compliant">Compliant</option>
        <option value="non_compliant">Non-compliant</option><option value="unknown">Verify</option></select></div>
      <div class="field narrow"><label for="rec">Recommended</label><select id="rec">
        <option value="">Any</option><option value="true">Yes</option><option value="false">No</option></select></div>
      <div><button id="reset" class="secondary">Reset</button></div>
    </div>
  </div>

  <div class="panel">
    <h2>Cars (<span id="count">0</span>)</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Year</th><th>Car</th><th>Body</th><th>Fuel</th><th>Trans</th><th>Engine</th><th>Power</th><th>kW/t</th><th>Price</th><th>Odo</th><th>ANCAP</th><th>Location</th><th>P-plate</th><th>Rec.</th><th>Source</th></tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </div>

  <div class="panel">
    <h2>Victorian P-plate rules</h2>
    <p id="rules"></p>
    <ul class="clean" id="sources"></ul>
  </div>
</main>
<script src="data.js"></script>
<script>
const D = window.PPLATE_DATA || {cars:[],stats:{},rules:{},sources:[]};
function fmt(n){return n==null?"\\u2014":Number(n).toLocaleString("en-AU");}
function badge(status){
  const label = status==="compliant"?"Compliant":status==="non_compliant"?"Not compliant":"Verify";
  return '<span class="badge '+status+'">'+label+'</span>';
}
function fillSelect(id, values){
  const el=document.getElementById(id);
  const seen=new Set();
  values.forEach(v=>{if(v&&!seen.has(v)){seen.add(v);const o=document.createElement("option");o.value=v;o.textContent=v;el.appendChild(o);}});
}
function renderStats(){
  const s=D.stats||{};
  const items=[["Total",s.total,null],["Compliant",s.compliant,"var(--green)"],["Non-compliant",s.non_compliant,"var(--red)"],["Verify",s.unknown,"var(--amber)"],["Recommended",s.recommended,"var(--blue)"]];
  document.getElementById("cards").innerHTML=items.map(([l,v,c])=>
    '<div class="card"><div class="num"'+(c?' style="color:'+c+'"':'')+'>'+(v==null?0:v)+'</div><div class="label">'+l+'</div></div>').join("");
}
function render(){
  const q=(document.getElementById("q").value||"").toLowerCase();
  const maxp=parseFloat(document.getElementById("max_price").value);
  const body=document.getElementById("body").value, fuel=document.getElementById("fuel").value;
  const trans=document.getElementById("trans").value, comp=document.getElementById("compliance").value;
  const rec=document.getElementById("rec").value;
  const rows=D.cars.filter(c=>{
    if(q && !((c.make+" "+c.model+" "+(c.variant||"")).toLowerCase().includes(q))) return false;
    if(!isNaN(maxp) && (c.price_aud==null || c.price_aud>maxp)) return false;
    if(body && c.body_type!==body) return false;
    if(fuel && c.fuel_type!==fuel) return false;
    if(trans && c.transmission!==trans) return false;
    if(comp && c.p_plate_compliant!==comp) return false;
    if(rec==="true" && !c.recommended) return false;
    if(rec==="false" && c.recommended) return false;
    return true;
  });
  document.getElementById("count").textContent=rows.length;
  document.getElementById("rows").innerHTML=rows.map(c=>{
    const listing=c.listing_url?'<div><a class="small" href="'+c.listing_url+'" target="_blank" rel="noopener">listing &#8599;</a></div>':"";
    return '<tr>'+
      '<td>'+(c.year||"\\u2014")+'</td>'+
      '<td><strong>'+c.make+' '+c.model+'</strong>'+(c.variant?'<div class="small muted">'+c.variant+'</div>':'')+listing+'</td>'+
      '<td>'+(c.body_type||"\\u2014")+'</td>'+
      '<td>'+(c.fuel_type||"\\u2014")+'</td>'+
      '<td>'+(c.transmission||"\\u2014")+'</td>'+
      '<td>'+(c.engine_size_cc?c.engine_size_cc+" cc":"\\u2014")+'</td>'+
      '<td>'+(c.power_kw?Math.round(c.power_kw)+" kW":"\\u2014")+'</td>'+
      '<td>'+(c.power_to_weight||"\\u2014")+'</td>'+
      '<td>'+(c.price_aud?"A$ "+fmt(c.price_aud):"\\u2014")+'</td>'+
      '<td>'+(c.odometer_km?fmt(c.odometer_km)+" km":"\\u2014")+'</td>'+
      '<td>'+(c.safety_rating_stars?c.safety_rating_stars+"\\u2605":"\\u2014")+'</td>'+
      '<td>'+(c.location||"\\u2014")+'</td>'+
      '<td>'+badge(c.p_plate_compliant)+'<details><summary class="small">why</summary><div class="reason">'+(c.p_plate_reason||"")+'</div></details></td>'+
      '<td>'+(c.recommended?'<span class="badge recommended">Yes</span>':"\\u2014")+'</td>'+
      '<td><span class="badge source">'+(c.source||"\\u2014")+'</span></td>'+
    '</tr>';
  }).join("");
}
document.getElementById("generated").textContent=D.generated_at||"";
document.getElementById("ppv").href=(D.rules&&D.rules.probationary_vehicle_database)||"#";
document.getElementById("rules").textContent=(D.rules&&D.rules.summary)||"";
document.getElementById("sources").innerHTML=(D.sources||[]).map(s=>'<li><a href="'+s.url+'" target="_blank" rel="noopener">'+(s.title||s.url)+'</a></li>').join("");
fillSelect("body",D.cars.map(c=>c.body_type));
fillSelect("fuel",D.cars.map(c=>c.fuel_type));
fillSelect("trans",D.cars.map(c=>c.transmission));
["q","max_price","body","fuel","trans","compliance","rec"].forEach(id=>document.getElementById(id).addEventListener("input",render));
document.getElementById("reset").addEventListener("click",()=>{
  ["q","max_price","body","fuel","trans","compliance","rec"].forEach(id=>document.getElementById(id).value="");
  render();
});
renderStats(); render();
</script>
</body>
</html>
"""


def _serialise_car(car: Car) -> dict:
    return {
        "id": car.id,
        "year": car.year,
        "make": car.make,
        "model": car.model,
        "variant": car.variant,
        "body_type": car.body_type,
        "fuel_type": car.fuel_type,
        "transmission": car.transmission,
        "engine_size_cc": car.engine_size_cc,
        "power_kw": car.power_kw,
        "weight_kg": car.weight_kg,
        "power_to_weight": car.power_to_weight,
        "price_aud": car.price_aud,
        "odometer_km": car.odometer_km,
        "location": car.location,
        "safety_rating_stars": car.safety_rating_stars,
        "safety_rating_year": car.safety_rating_year,
        "listing_url": car.listing_url,
        "source": car.source.value if car.source else None,
        "p_plate_compliant": car.p_plate_compliant.value if car.p_plate_compliant else "unknown",
        "p_plate_reason": car.p_plate_reason,
        "recommended": bool(car.recommended),
        "notes": car.notes,
    }


def export(out_dir: Path) -> dict:
    init_db()
    db = SessionLocal()
    try:
        cars = db.scalars(select(Car).order_by(Car.make.asc(), Car.model.asc(), Car.year.asc())).all()
        sources = db.scalars(
            select(RecommendationSource).order_by(RecommendationSource.fetched_at.desc())
        ).all()
        payload = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "app": get_settings().app_name,
            "stats": car_service.stats(db),
            "rules": {
                "summary": p_plate_compliance.RULES_SUMMARY,
                "sources": p_plate_compliance.RULES_SOURCE_URLS,
                "probationary_vehicle_database": p_plate_compliance.PPV_DATABASE_URL,
            },
            "sources": [
                {"url": s.url, "title": s.title, "category": s.category} for s in sources
            ],
            "cars": [_serialise_car(c) for c in cars],
        }
    finally:
        db.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data.js").write_text(
        "window.PPLATE_DATA = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )
    html = (
        INDEX_HTML.replace("__APP_NAME__", payload["app"]).replace(
            "__GENERATED__", payload["generated_at"]
        )
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a static site to docs/ for GitHub Pages.")
    parser.add_argument("--out", default="docs", help="output directory (default: docs)")
    args = parser.parse_args()
    payload = export(Path(args.out))
    print(
        f"Exported {len(payload['cars'])} cars to {args.out}/ "
        f"(compliant={payload['stats']['compliant']}, "
        f"non_compliant={payload['stats']['non_compliant']}, "
        f"unknown={payload['stats']['unknown']})"
    )


if __name__ == "__main__":
    main()
