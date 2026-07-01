"""
build_dashboard.py -- generate a self-contained, deployable HTML dashboard from
the early-vote performance matrix. Excel-like: sortable columns, search/group
filter, conditional color formatting, state tabs, drill from summary -> counties.

No backend, no build step, no dependencies: it writes ONE static file
(web/index.html) with the data baked in. Deploy by dropping it on any static host
(GitHub Pages, Netlify, Vercel) or just double-click to open locally.

Run:  python web/build_dashboard.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analytics"))
from turnout_compare import compare, group_deviation              # noqa: E402
from performance_matrix import overall_turnout, SPLIT             # noqa: E402

STATES = ["GA", "NC"]


def state_data(state):
    ref_years, basis, rows, hist, cur, lean = compare(state)
    gd = group_deviation(state, SPLIT)
    cur_total, ov = overall_turnout(state)

    counties = []
    for r in rows:
        ld = r["lean_dem"]
        rec = {"county": r["county"].title(), "lean": ld,
               "group": "D" if (ld or 0) >= SPLIT else "R",
               "share": r["cur_share"]}
        for y in ref_years:
            rec[f"vs{y}"] = r[f"vs_{y}"]
        counties.append(rec)

    dem, rep = gd["groups"]["Blue-leaning"], gd["groups"]["Red-leaning"]
    groups = {
        "Dem": {"n": dem["n"], "share": dem["cur_share"], "dev": dem["dev"]},
        "Rep": {"n": rep["n"], "share": rep["cur_share"], "dev": rep["dev"]},
    }
    net = {}
    for y in ref_years:
        b, r = dem["dev"].get(y), rep["dev"].get(y)
        net[y] = (b - r) if (b is not None and r is not None) else None

    return {
        "state": state, "ref_years": ref_years, "basis": basis,
        "cur_total": cur_total,
        "overall": {y: ov[y]["pct_of"] for y in ref_years},
        "groups": groups, "net": net, "counties": counties,
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Early-Vote Performance Matrix</title>
<style>
  :root{
    --bg:#0f1420; --panel:#171e2e; --panel2:#1d2638; --line:#2a3447;
    --ink:#e7ecf5; --muted:#93a0b8; --dem:#3b82f6; --rep:#ef4444;
    --pos:#16a34a; --neg:#dc2626; --accent:#fbbf24;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.4 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  header{padding:18px 22px;border-bottom:1px solid var(--line);background:var(--panel)}
  h1{margin:0;font-size:19px}
  .sub{color:var(--muted);font-size:12.5px;margin-top:4px}
  .wrap{padding:18px 22px;max-width:1100px;margin:0 auto}
  .tabs{display:flex;gap:8px;margin-bottom:16px}
  .tab{padding:8px 18px;border:1px solid var(--line);background:var(--panel);
    color:var(--ink);border-radius:8px;cursor:pointer;font-weight:600}
  .tab.on{background:var(--accent);color:#1a1300;border-color:var(--accent)}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:18px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
  .card .lab{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
  .card .big{font-size:26px;font-weight:700;margin-top:6px}
  .card .note{color:var(--muted);font-size:12px;margin-top:6px}
  .toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
  input,select{background:var(--panel2);border:1px solid var(--line);color:var(--ink);
    padding:8px 10px;border-radius:8px;font-size:13px}
  input{min-width:200px}
  table{width:100%;border-collapse:collapse;background:var(--panel);
    border:1px solid var(--line);border-radius:10px;overflow:hidden}
  th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
  th:first-child,td:first-child{text-align:left}
  thead th{position:sticky;top:0;background:var(--panel2);cursor:pointer;
    user-select:none;font-size:12px;color:var(--muted)}
  thead th:hover{color:var(--ink)}
  th .arw{opacity:.5;font-size:10px}
  tbody tr:hover{background:#1b2435}
  .badge{display:inline-block;min-width:20px;text-align:center;padding:1px 7px;border-radius:6px;
    font-weight:700;font-size:12px}
  .badge.D{background:rgba(59,130,246,.18);color:#93c5fd}
  .badge.R{background:rgba(239,68,68,.18);color:#fca5a5}
  .tablewrap{max-height:60vh;overflow:auto;border-radius:10px}
  .foot{color:var(--muted);font-size:12px;margin-top:14px;line-height:1.6}
  .pill{display:inline-block;padding:1px 7px;border-radius:6px;font-weight:600}
</style>
</head>
<body>
<header>
  <h1>Early-Vote Performance Matrix <span style="color:var(--accent)">&middot; 2026</span></h1>
  <div class="sub">Are Democratic- or Republican-leaning counties over/under-performing in early voting vs 2020 &amp; 2022 &mdash; by share of the statewide vote (normalized %, not raw counts).</div>
</header>
<div class="wrap">
  <div class="tabs" id="tabs"></div>
  <div class="cards" id="cards"></div>
  <div class="toolbar">
    <input id="q" placeholder="Filter counties by name...">
    <select id="grp">
      <option value="">All counties</option>
      <option value="D">Dem-leaning only</option>
      <option value="R">Rep-leaning only</option>
    </select>
    <span class="sub" id="count"></span>
  </div>
  <div class="tablewrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
  <div class="foot" id="foot"></div>
</div>
<script>
const DATA = __DATA__;
let cur = "__FIRST__", sortKey="share", sortDir=-1;

function pct(x,signed){ if(x===null||x===undefined) return "&mdash;";
  const v=(x*100); return (signed&&v>0?"+":"")+v.toFixed(1)+"%"; }
function colour(x){ if(x===null||x===undefined) return "";
  const v=x*100, a=Math.min(Math.abs(v)/15,1).toFixed(2);
  return v>=0 ? `background:rgba(22,163,74,${a*0.55});` : `background:rgba(220,38,38,${a*0.55});`; }

function tabs(){ document.getElementById("tabs").innerHTML =
  Object.keys(DATA).map(s=>`<div class="tab ${s===cur?'on':''}" onclick="pick('${s}')">${s}</div>`).join(""); }
function pick(s){ cur=s; sortKey="share"; sortDir=-1; tabs(); cards(); render(); }

function cards(){
  const d=DATA[cur], ys=d.ref_years;
  const netCard=(y)=>{ const n=d.net[y]; if(n===null) return "";
    const who=n>0?"Democratic":"Republican", col=n>0?"var(--dem)":"var(--rep)";
    return `<div class="card"><div class="lab">Net turnout edge vs ${y}</div>
      <div class="big" style="color:${col}">${(n*100>0?'+':'')}${(n*100).toFixed(1)} pts</div>
      <div class="note">toward <b>${who}</b> turnout &mdash; Dem-leaning ${pct(d.groups.Dem.dev[y],1)} vs Rep-leaning ${pct(d.groups.Rep.dev[y],1)}</div></div>`; };
  const turnout = ys.map(y=>`${y}: <b>${(d.overall[y]*100).toFixed(0)}%</b>`).join(" &nbsp;|&nbsp; ");
  document.getElementById("cards").innerHTML =
    `<div class="card"><div class="lab">Early ballots so far (2026)</div>
       <div class="big">${d.cur_total.toLocaleString()}</div>
       <div class="note">as % of each year's full early vote &mdash; ${turnout}<br>(progress gauge, not a turnout-rate)</div></div>`
    + (d.net[2022]!==undefined?netCard(2022):"") + (d.net[2020]!==undefined?netCard(2020):"");
}

function header(){
  const ys=DATA[cur].ref_years;
  const cols=[["county","County"],["lean","Lean"],["group","Grp"],["share","2026 share"]]
    .concat(ys.map(y=>["vs"+y,"vs "+y]));
  document.querySelector("#tbl thead").innerHTML = "<tr>"+cols.map(([k,l])=>{
    const ar = k===sortKey ? (sortDir>0?"&#9650;":"&#9660;") : "";
    return `<th onclick="sortBy('${k}')">${l} <span class="arw">${ar}</span></th>`;}).join("")+"</tr>";
}
function sortBy(k){ if(k===sortKey) sortDir*=-1; else {sortKey=k; sortDir=(k==='county'?1:-1);} render(); }

function render(){
  header();
  const d=DATA[cur], ys=d.ref_years;
  const q=document.getElementById("q").value.trim().toLowerCase();
  const g=document.getElementById("grp").value;
  let rows=d.counties.filter(c=>(!q||c.county.toLowerCase().includes(q))&&(!g||c.group===g));
  rows.sort((a,b)=>{ let x=a[sortKey],y=b[sortKey];
    if(sortKey==='county'){return x<y?-sortDir:x>y?sortDir:0;}
    x=(x===null||x===undefined)?-1e9:x; y=(y===null||y===undefined)?-1e9:y;
    return (x-y)*sortDir; });
  document.querySelector("#tbl tbody").innerHTML = rows.map(c=>{
    const vs = ys.map(y=>`<td style="${colour(c['vs'+y])}">${pct(c['vs'+y],1)}</td>`).join("");
    return `<tr><td>${c.county}</td><td>${(c.lean*100).toFixed(0)}%</td>
      <td><span class="badge ${c.group}">${c.group}</span></td>
      <td>${(c.share*100).toFixed(2)}%</td>${vs}</tr>`;}).join("");
  document.getElementById("count").textContent = rows.length+" counties";
  const b=Object.entries(d.basis).map(([y,v])=>`${y}=${v}`).join(", ");
  document.getElementById("foot").innerHTML =
    `<b>How to read:</b> each "vs YEAR" cell = how much bigger (<span class="pill" style="background:rgba(22,163,74,.4)">green</span>) `
    +`or smaller (<span class="pill" style="background:rgba(220,38,38,.4)">red</span>) a slice of the early vote that county is now, vs that year. `
    +`Dem-leaning counties going green + Rep-leaning going red = Democratic turnout edge.<br>`
    +`Data basis per year: ${b}. &nbsp; <b>Note:</b> 2026 figures are synthetic stand-ins until real early voting opens (~Oct 2026); `
    +`partisan lean from county results; this measures WHERE early voters come from, not who they voted for.`;
}
tabs(); cards(); render();
document.getElementById("q").addEventListener("input",render);
document.getElementById("grp").addEventListener("change",render);
</script>
</body>
</html>
"""


def main():
    data = {s: state_data(s) for s in STATES}
    html = (TEMPLATE
            .replace("__DATA__", json.dumps(data))
            .replace("__FIRST__", STATES[0]))
    out = Path(__file__).resolve().parent / "index.html"
    out.write_text(html, encoding="utf-8")
    # widget partial (body only) for inline preview
    body = html.split("<body>", 1)[1].split("</body>", 1)[0]
    (out.parent / "_widget.html").write_text(body, encoding="utf-8")
    print(f"  wrote {out}  ({out.stat().st_size//1024} KB, {sum(len(d['counties']) for d in data.values())} counties)")


if __name__ == "__main__":
    main()
