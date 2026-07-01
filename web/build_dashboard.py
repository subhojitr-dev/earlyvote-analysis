"""
build_dashboard.py -- generate a self-contained, deployable HTML dashboard from
the early-vote performance matrix. Excel-like: sortable columns, search/group
filter, two table views (partisan shift / turnout progress), conditional color,
state tabs, plus aggregate panels (partisan trajectory + turnout progress bars).

No backend, no build step, no dependencies: it writes ONE static file
(web/index.html) with the data baked in. Deploy on any static host (Vercel,
GitHub Pages, Netlify) or just double-click to open locally.

Run:  python web/build_dashboard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analytics"))
from turnout_compare import (compare, group_deviation, composite_lean,   # noqa: E402
                             turnout_progress)
from performance_matrix import overall_turnout, SPLIT             # noqa: E402

STATES = ["GA", "NC"]


def state_data(state):
    ref_years, basis, rows, hist, cur, lean = compare(state)
    gd = group_deviation(state, SPLIT)
    cur_total, ov = overall_turnout(state)
    _cy, cl = composite_lean(state)
    _py, per, pagg = turnout_progress(state)

    counties = []
    for r in rows:
        name = r["county"]
        ld = r["lean_dem"]
        rec = {"county": name.title(), "lean": ld,
               "group": "D" if (ld or 0) >= SPLIT else "R",
               "share": r["cur_share"]}
        for y in ref_years:
            rec[f"vs{y}"] = r[f"vs_{y}"]
            rec[f"p{y}"] = per.get(name, {}).get(y)
        counties.append(rec)

    dem, rep = gd["groups"]["Blue-leaning"], gd["groups"]["Red-leaning"]
    groups = {"Dem": {"n": dem["n"], "share": dem["cur_share"], "dev": dem["dev"]},
              "Rep": {"n": rep["n"], "share": rep["cur_share"], "dev": rep["dev"]}}
    net = {}
    for y in ref_years:
        b, r = dem["dev"].get(y), rep["dev"].get(y)
        net[y] = (b - r) if (b is not None and r is not None) else None

    return {
        "state": state, "ref_years": ref_years, "basis": basis,
        "cur_total": cur_total,
        "overall": {y: ov[y]["pct_of"] for y in ref_years},
        "groups": groups, "net": net, "counties": counties,
        "complean": {str(y): cl[y] for y in _cy} | {"cur": cl["cur"]},
        "progress": {str(y): pagg[y] for y in _py},
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Early-Vote Performance Matrix</title>
<style>
  :root{--bg:#0f1420;--panel:#171e2e;--panel2:#1d2638;--line:#2a3447;--ink:#e7ecf5;
    --muted:#93a0b8;--dem:#3b82f6;--rep:#ef4444;--pos:#22c55e;--neg:#ef4444;--accent:#fbbf24;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
  header{padding:16px 22px;border-bottom:1px solid var(--line);background:var(--panel)}
  h1{margin:0;font-size:19px}
  .sub{color:var(--muted);font-size:12.5px;margin-top:4px}
  .wrap{padding:18px 22px;max-width:1160px;margin:0 auto}
  .tabs{display:flex;gap:8px;margin-bottom:16px}
  .tab{padding:8px 20px;border:1px solid var(--line);background:var(--panel);color:var(--ink);
    border-radius:8px;cursor:pointer;font-weight:600}
  .tab.on{background:var(--accent);color:#1a1300;border-color:var(--accent)}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px}
  .card .lab{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}
  .card .big{font-size:25px;font-weight:700;margin-top:5px}
  .card .note{color:var(--muted);font-size:11.5px;margin-top:5px;line-height:1.5}
  .panels{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
  @media(max-width:760px){.panels{grid-template-columns:1fr}}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
  .panel h3{margin:0 0 4px;font-size:13.5px}
  .panel .ph{color:var(--muted);font-size:11.5px;margin-bottom:11px;line-height:1.5}
  .brow{display:flex;align-items:center;gap:10px;margin:7px 0}
  .brow .yl{width:38px;color:var(--muted);font-size:12px;flex:none}
  .track{flex:1;height:16px;background:var(--panel2);border-radius:5px;position:relative;overflow:hidden}
  .fill{height:100%;border-radius:5px}
  .brow .vl{width:70px;text-align:right;font-size:12.5px;font-weight:600;flex:none}
  .mark{position:absolute;top:0;bottom:0;width:2px;background:var(--muted);opacity:.6}
  .verdict{margin-top:10px;font-size:12px;line-height:1.5;padding:8px 10px;border-radius:8px;
    background:var(--panel2)}
  .toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:9px}
  input,select{background:var(--panel2);border:1px solid var(--line);color:var(--ink);
    padding:8px 10px;border-radius:8px;font-size:13px}
  input{min-width:190px}
  .seg{display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .seg button{background:var(--panel2);color:var(--muted);border:none;padding:8px 14px;cursor:pointer;font-size:12.5px;font-weight:600}
  .seg button.on{background:var(--accent);color:#1a1300}
  .tablewrap{max-height:60vh;overflow:auto;border:1px solid var(--line);border-radius:10px}
  table{width:100%;border-collapse:collapse}
  th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
  th:first-child,td:first-child{text-align:left}
  thead th{position:sticky;top:0;background:var(--panel2);cursor:pointer;user-select:none;
    font-size:11.5px;color:var(--muted)}
  thead th:hover{color:var(--ink)}
  tbody tr:hover{background:#1b2435}
  .badge{display:inline-block;min-width:20px;text-align:center;padding:1px 7px;border-radius:6px;font-weight:700;font-size:12px}
  .badge.D{background:rgba(59,130,246,.18);color:#93c5fd}
  .badge.R{background:rgba(239,68,68,.18);color:#fca5a5}
  .pbar{display:inline-block;width:52px;height:9px;border-radius:3px;background:var(--panel2);
    position:relative;vertical-align:middle;margin-left:7px;overflow:hidden}
  .pbar i{position:absolute;left:0;top:0;bottom:0;border-radius:3px}
  .foot{color:var(--muted);font-size:12px;margin-top:14px;line-height:1.6}
  .pill{display:inline-block;padding:1px 7px;border-radius:6px;font-weight:600}
</style>
</head>
<body>
<header>
  <h1>Early-Vote Performance Matrix <span style="color:var(--accent)">&middot; 2026</span></h1>
  <div class="sub">County-level early-voting signal vs 2020, 2022 &amp; 2024 &mdash; partisan share shift, aggregate Dem tilt, and turnout progress.</div>
</header>
<div class="wrap">
  <div class="tabs" id="tabs"></div>
  <div class="cards" id="cards"></div>
  <div class="panels" id="panels"></div>
  <div class="toolbar">
    <div class="seg" id="viewSeg">
      <button data-v="partisan" class="on">Partisan shift</button>
      <button data-v="turnout">Turnout progress</button>
    </div>
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
let cur = "__FIRST__", sortKey="share", sortDir=-1, view="partisan";

const pct=(x,s)=>x==null?"&mdash;":((s&&x*100>0?"+":"")+(x*100).toFixed(1)+"%");
const p0=(x)=>x==null?"&mdash;":Math.round(x*100)+"%";
function shiftBg(x){if(x==null)return"";const a=(Math.min(Math.abs(x)/0.15,1)*0.55).toFixed(2);
  return x>=0?`background:rgba(34,197,94,${a})`:`background:rgba(239,68,68,${a})`;}

function tabs(){document.getElementById("tabs").innerHTML=
  Object.keys(DATA).map(s=>`<div class="tab ${s===cur?'on':''}" onclick="pick('${s}')">${s}</div>`).join("");}
function pick(s){cur=s;sortKey="share";sortDir=-1;tabs();cards();panels();render();}

function cards(){const d=DATA[cur],ys=d.ref_years;
  const nc=y=>{const n=d.net[y];if(n==null)return"";const dem=n>0,col=dem?"var(--dem)":"var(--rep)";
    return `<div class="card"><div class="lab">Net turnout edge vs ${y}</div>
      <div class="big" style="color:${col}">${(n*100>0?'+':'')}${(n*100).toFixed(1)} pts</div>
      <div class="note">toward <b>${dem?'Democratic':'Republican'}</b> &middot; Dem-lean ${pct(d.groups.Dem.dev[y],1)}, Rep-lean ${pct(d.groups.Rep.dev[y],1)}</div></div>`;};
  const ov=ys.map(y=>`${y}: <b>${Math.round(d.overall[y]*100)}%</b>`).join(" &middot; ");
  document.getElementById("cards").innerHTML=
    `<div class="card"><div class="lab">Early ballots so far (2026)</div>
       <div class="big">${d.cur_total.toLocaleString()}</div>
       <div class="note">of each year's full early vote &middot; ${ov}</div></div>`+nc(2022)+nc(2020);}

function panels(){const d=DATA[cur];
  const cl=d.complean, cy=d.ref_years.concat(["cur"]);
  const lab=y=>y==="cur"?"2026":y;
  const clScale=v=>Math.max(0,Math.min(1,(v-0.44)/(0.12)))*100;
  const clRows=cy.map(y=>{const v=cl[y];const is26=y==="cur";
    return `<div class="brow"><span class="yl">${lab(y)}</span>
      <div class="track"><div class="fill" style="width:${clScale(v).toFixed(0)}%;background:${is26?'var(--accent)':'var(--dem)'}"></div>
      <div class="mark" style="left:${clScale(0.50).toFixed(0)}%"></div></div>
      <span class="vl" style="${is26?'color:var(--accent)':''}">${(v*100).toFixed(1)}% D</span></div>`;}).join("");
  const dv=(cl.cur-cl["2024"])*100, best=cl.cur>=Math.max(cl["2020"],cl["2022"],cl["2024"]);
  const clRead=`2026 early electorate is <b>${(cl.cur*100).toFixed(1)}% Dem-tilted</b> &mdash; `+
    `${pct(cl.cur-cl["2020"],1)} vs 2020, ${pct(cl.cur-cl["2022"],1)} vs 2022, ${pct(cl.cur-cl["2024"],1)} vs 2024. `+
    (best?`Above all three &mdash; the +${dv.toFixed(1)}pt jump vs 2024 <b>erases the 2024 dip</b>.`:`Mixed vs prior cycles.`);

  const pr=d.progress, py=d.ref_years;
  const prScale=v=>Math.min(v,1.5)/1.5*100;
  const prRows=py.map(y=>{const v=pr[y];const over=v>=1;
    return `<div class="brow"><span class="yl">${y}</span>
      <div class="track"><div class="fill" style="width:${prScale(v).toFixed(0)}%;background:${over?'var(--pos)':'var(--accent)'}"></div>
      <div class="mark" style="left:${(100/1.5).toFixed(0)}%"></div></div>
      <span class="vl" style="${over?'color:var(--pos)':''}">${Math.round(v*100)}%</span></div>`;}).join("");
  const prRead=`Marker = 100% (a full prior turnout). Bars past it = 2026 early vote alone has <b>already exceeded</b> that year's total turnout. Climbs daily as early voting runs.`;

  document.getElementById("panels").innerHTML=
    `<div class="panel"><h3>Aggregate Dem tilt of the early electorate</h3>
       <div class="ph">Dem two-party lean weighted by where the early votes come from. Higher = early voters from more-Democratic places.</div>
       ${clRows}<div class="verdict">${clRead}</div></div>
     <div class="panel"><h3>Turnout progress vs full prior turnout</h3>
       <div class="ph">2026 early ballots so far as a % of each county-summed TOTAL turnout in that year.</div>
       ${prRows}<div class="verdict">${prRead}</div></div>`;}

function header(){const ys=DATA[cur].ref_years;
  let cols=[["county","County"],["lean","Lean"],["group","Grp"],["share","2026 share"]];
  cols=cols.concat(view==="partisan"
    ? ys.map(y=>["vs"+y,"vs "+y])
    : ys.map(y=>["p"+y,"% of "+y]));
  document.querySelector("#tbl thead").innerHTML="<tr>"+cols.map(([k,l])=>{
    const ar=k===sortKey?(sortDir>0?"&#9650;":"&#9660;"):"";
    return `<th onclick="sortBy('${k}')">${l} ${ar}</th>`;}).join("")+"</tr>";}
function sortBy(k){if(k===sortKey)sortDir*=-1;else{sortKey=k;sortDir=(k==='county'?1:-1);}render();}

function render(){header();const d=DATA[cur],ys=d.ref_years;
  const q=document.getElementById("q").value.trim().toLowerCase();
  const g=document.getElementById("grp").value;
  let rows=d.counties.filter(c=>(!q||c.county.toLowerCase().includes(q))&&(!g||c.group===g));
  rows.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];
    if(sortKey==='county')return x<y?-sortDir:x>y?sortDir:0;
    x=(x==null)?-1e9:x;y=(y==null)?-1e9:y;return(x-y)*sortDir;});
  document.querySelector("#tbl tbody").innerHTML=rows.map(c=>{
    let cells;
    if(view==="partisan"){cells=ys.map(y=>`<td style="${shiftBg(c['vs'+y])}">${pct(c['vs'+y],1)}</td>`).join("");}
    else{cells=ys.map(y=>{const v=c['p'+y];const w=v==null?0:Math.min(v,1.5)/1.5*100;
      const col=v>=1?'var(--pos)':'var(--accent)';
      return `<td>${p0(v)}<span class="pbar"><i style="width:${w.toFixed(0)}%;background:${col}"></i></span></td>`;}).join("");}
    return `<tr><td>${c.county}</td><td>${Math.round(c.lean*100)}%</td>
      <td><span class="badge ${c.group}">${c.group}</span></td>
      <td>${(c.share*100).toFixed(2)}%</td>${cells}</tr>`;}).join("");
  document.getElementById("count").textContent=rows.length+" counties";
  const foot=view==="partisan"
    ? `<b>Partisan shift:</b> each cell = how much bigger (<span class="pill" style="background:rgba(34,197,94,.4)">green</span>) or smaller (<span class="pill" style="background:rgba(239,68,68,.4)">red</span>) a slice of the early vote that county is now, vs that year. Dem-leaning green + Rep-leaning red = Democratic edge.`
    : `<b>Turnout progress:</b> 2026 early ballots as a % of that county's FULL turnout in the given year. <span class="pill" style="background:rgba(34,197,94,.4)">Green bar</span> = already past 100% (exceeded that whole election).`;
  document.getElementById("foot").innerHTML=foot+`<br>2026 figures are synthetic stand-ins until real early voting opens (~Oct 2026). Partisan lean from county results; share metrics measure WHERE early voters come from, not who they voted for.`;}

document.getElementById("viewSeg").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;view=b.dataset.v;
  document.querySelectorAll("#viewSeg button").forEach(x=>x.classList.toggle("on",x===b));
  if((view==="turnout"&&sortKey.startsWith("vs"))||(view==="partisan"&&sortKey.startsWith("p")))sortKey="share";
  render();});
document.getElementById("q").addEventListener("input",render);
document.getElementById("grp").addEventListener("change",render);
tabs();cards();panels();render();
</script>
</body>
</html>
"""


def main():
    data = {s: state_data(s) for s in STATES}
    html = TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__FIRST__", STATES[0])
    out = Path(__file__).resolve().parent / "index.html"
    out.write_text(html, encoding="utf-8")
    body = html.split("<body>", 1)[1].split("</body>", 1)[0]
    (out.parent / "_widget.html").write_text(body, encoding="utf-8")
    print(f"  wrote {out}  ({out.stat().st_size//1024} KB, "
          f"{sum(len(d['counties']) for d in data.values())} counties)")


if __name__ == "__main__":
    main()
