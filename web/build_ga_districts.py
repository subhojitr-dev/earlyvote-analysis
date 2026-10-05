"""
build_ga_districts.py — data for the State House / State Senate drill-down pages:
Georgia (web/ga/) and North Carolina (web/nc/). Same method for both states.

Combines
  data/ga_districts/early_{2022,2024,2026}.csv   (from ingestor/ga_districts.py)
  data/ga_districts/redraw.csv                   (lines-unchanged proxy)
  data/ga_districts/xwalk_2024.csv               (precinct -> district weights; no longer used for lean)
  data/raw/medsl/ga24.csv  MIT Election Lab 2024 GA precinct results, all offices (lean + 2024 race)
  Census 2024 cartographic boundaries in data/raw/geo/  (counties, SLDL, SLDU)
into
  web/ga/state.json            county outlines + statewide summary
  web/ga/county/{KEY}.json     one county: its district pieces (clipped to the
                               county) + whole-district stats for every district
                               that touches it

THE COMPARISON RULE (agreed with the user)
  * District lines largely unchanged since the 2022 election (>= SAME_MIN of
    voters who voted early in both years kept the same district number)
      -> compare against Nov 2022 (last midterm, same lines).
  * Otherwise "redrawn before 2024" -> compare against Nov 2024 only.
  * Dec 2022 runoff is never used.
  Headline = district's SHARE of Georgia's early vote vs its share at the same
  number of days before Election Day in the comparison year:
      pace = share_now / share_then - 1      ("ahead / behind pace by X%")
  The same pace is also worked out separately for early in-person votes and for
  mail votes (each as a share of Georgia's in-person / mail total), shown under
  the overall headline. Too-small samples (< MIN_MODE_BALLOTS) show no pace.

DEMO MODE
  Until in-person early voting opens (Oct 13 2026) the real 2026 file is tiny,
  so a clearly-labelled synthetic snapshot is also built (each district's
  comparison-year pattern a week into early voting, seeded random tilt per district).

DEMOGRAPHICS (states whose files carry them — North Carolina)
  data/{st}_districts/demo_{year}.csv (race, age, gender, party of early voters).
  Each district gets the make-up of its early voters now vs the same day in its
  comparison year (same comparison rule as above), shown as shares; groups with
  < MIN_GROUP voters are not shown separately.

Run:  python web/build_ga_districts.py        (Georgia)
      python web/build_ga_districts.py NC     (North Carolina)
"""
from __future__ import annotations

import csv
import json
import random
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import shapefile  # pyshp
from shapely.geometry import shape as to_shape, mapping
from shapely.ops import polylabel

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "data" / "raw" / "geo"
RACE = {}
STATES = {
    "GA": {"name": "Georgia", "fips": "13", "ev_start": "Oct 13",
           "source": "Georgia Secretary of State absentee file"},
    "NC": {"name": "North Carolina", "fips": "37", "ev_start": "Oct 15",
           "source": "NC State Board of Elections absentee file"},
    # Texas: districts from the Texas Legislative Council (current plans), lean from its
    # Red-206 district election reports; congressional map redrawn in 2025.
    "TX": {"name": "Texas", "fips": "48", "ev_start": "Oct 19",
           "source": "Texas Secretary of State early-voting rosters",
           "chambers": {"house": ("tlc:PLANH2316", "District", "HD"),
                        "senate": ("tlc:PLANS2168", "District", "SD"),
                        "congress": ("tlc:PLANC2333", "District", "CD")},
           "lean": "tlc",
           "min_county_share": 0,       # votes are placed by precinct, so there is no stray-address noise to hide
           "reason": {"congress": "Redrawn in 2025; 2024 votes re-counted on the new lines"}},
}
ST = (sys.argv[1] if len(sys.argv) > 1 else "GA").upper()
CFG = STATES[ST]
DATA = ROOT / "data" / f"{ST.lower()}_districts"
# MIT Election Lab 2024 precinct results, all offices: github.com/MEDSL/2024-elections-official ({st}24.zip)
MEDSL24 = ROOT / "data" / "raw" / "medsl" / f"{ST.lower()}24.csv"
OUT = ROOT / "web" / ST.lower()
MIN_GROUP = 10           # demographic groups with fewer voters are folded into "Other / not shown"

SAME_MIN = 0.90          # >= 90% same voters => "lines unchanged" (movers add ~2-4% noise)
DEMO_DAYS_OUT = 15       # demo snapshot = one week into early voting
STATE_TOL = 0.004        # geometry simplification (degrees) for the state map
COUNTY_TOL = 0.0006      # finer for the single-county map
MIN_COUNTY_SHARE = CFG.get("min_county_share", 0.005)  # hide counties with < 0.5% of a district's ballots (address noise)
MIN_PIECE = 0.003        # drop district pieces < 0.3% of the county's area (slivers)
CHAMBERS = CFG.get("chambers") or {"house": ("sldl", "SLDLST", "HD"), "senate": ("sldu", "SLDUST", "SD")}
MODES = ("all", "inperson", "mail")   # overall, early in-person, mail (incl. electronic)
MIN_MODE_BALLOTS = 30    # pace (overall, in-person, mail) shown only with >= 30 ballots now AND then


def key(name: str) -> str:
    return re.sub(r"[^A-Z]", "", name.upper())


# ---------------------------------------------------------------- data loading
def _early():
    return defaultdict(lambda: defaultdict(lambda: defaultdict(int)))


def load_early(year: int):
    """{mode: {(chamber, district): {county: {days_out: n}}}} for mode in MODES"""
    out = {m: _early() for m in MODES}
    p = DATA / f"early_{year}.csv"
    if not p.exists():
        return out
    for r in csv.DictReader(p.open(encoding="utf-8")):
        if r["chamber"] not in CHAMBERS:
            continue
        k, c, d, n = (r["chamber"], r["district"]), key(r["county"]), int(r["days_out"]), int(r["ballots"])
        out["all"][k][c][d] += n
        out[r["mode"]][k][c][d] += n
    return out


def upto(series: dict, days_out: int) -> int:
    """Cumulative ballots cast on or before `days_out` days before Election Day."""
    return sum(n for d, n in series.items() if d >= days_out)


def load_redraw():
    return {(r["chamber"], r["district"]): float(r["same_pct"])
            for r in csv.DictReader((DATA / "redraw.csv").open(encoding="utf-8"))}


def load_lean():
    """2024 presidential margin per district (two-party, D minus R, in points) plus
    the actual 2024 State House / State Senate result, from MIT Election Lab's
    official 2024 Georgia precinct file (all offices). Each precinct's district is
    read from the State House / Senate contest on its own ballot, so no matching of
    precinct names across files is needed. Precincts split between districts (~260)
    are shared out by each district's share of that precinct's legislative vote.
    Returns (lean, race): lean[(ch, d)] = margin; race[(ch, d)] = {...}."""
    pres = defaultdict(lambda: [0, 0])                      # precinct -> [D, R]
    leg = {ch: defaultdict(lambda: defaultdict(int)) for ch in CHAMBERS}   # ch -> precinct -> {dist: votes}
    cand = {ch: defaultdict(lambda: defaultdict(lambda: [0, ""])) for ch in CHAMBERS}  # ch -> dist -> name -> [votes, party]
    office = {"STATE HOUSE": "house", "STATE SENATE": "senate"}
    with MEDSL24.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            k, v = (r["county_name"], r["precinct"]), int(r["votes"] or 0)
            if r["office"] == "US PRESIDENT":
                i = {"DEMOCRAT": 0, "REPUBLICAN": 1}.get(r["party_simplified"])
                if i is not None:
                    pres[k][i] += v
            elif r["office"] in office:
                ch, d = office[r["office"]], str(int(r["district"]))
                leg[ch][k][d] += v
                c = cand[ch][d][r["candidate"]]
                c[0] += v
                c[1] = r["party_simplified"]
    lean = {}
    tot = sum(d + rep for d, rep in pres.values())
    for ch in CHAMBERS:
        acc, hit = defaultdict(lambda: [0.0, 0.0]), 0
        # Each precinct's presidential vote goes to the district(s) on its ballot;
        # precincts split between districts are shared out by each district's share
        # of that precinct's legislative vote. (Needs results reported by real
        # precinct — for NC that is the State Board's precinct-sorted file; see
        # ingestor/nc_districts.py. Tested against published district results.)
        for k, (dv, rv) in pres.items():
            dist = leg[ch].get(k)
            if not dist or not sum(dist.values()):
                continue
            hit += dv + rv
            s = sum(dist.values())
            for d, v in dist.items():
                acc[d][0] += dv * v / s
                acc[d][1] += rv * v / s
        print(f"lean ({ch}): {hit / tot:.1%} of 2024 presidential votes placed in districts")
        for d, (dv, rv) in acc.items():
            if dv + rv:
                lean[(ch, d)] = round((dv - rv) / (dv + rv) * 100, 1)
    race = {}
    for ch in CHAMBERS:
        for d, cs in cand[ch].items():
            top = sorted(cs.items(), key=lambda kv: -kv[1][0])
            dv = sum(v for v, p in cs.values() if p == "DEMOCRAT")
            rv = sum(v for v, p in cs.values() if p == "REPUBLICAN")
            if not (dv and rv):          # no D-vs-R contest (write-ins / minor parties only)
                race[(ch, d)] = {"contested": False, "winner": top[0][0].title(), "party": top[0][1][1][:1]}
                continue
            race[(ch, d)] = {"contested": True, "winner": top[0][0].title(), "party": top[0][1][1][:1],
                             "margin": round((dv - rv) / (dv + rv) * 100, 1) if dv + rv else None}
    return lean, race


# ---------------------------------------------------------------- geometry
def read_shapes(stem: str, field: str, state_only=True):
    r = shapefile.Reader(str(GEO / stem / stem))
    out = {}
    for sr in r.iterShapeRecords():
        rec = sr.record.as_dict()
        if state_only and rec.get("STATEFP") != CFG["fips"]:
            continue
        out[rec[field]] = to_shape(sr.shape.__geo_interface__).buffer(0)
    return out


def rings(geom, tol: float):
    g = geom.simplify(tol, preserve_topology=True)
    polys = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
    return [[[round(x, 5), round(y, 5)] for x, y in p.exterior.coords]
            for p in polys if p.geom_type == "Polygon" and not p.is_empty]


def label_pt(geom):
    big = geom if geom.geom_type == "Polygon" else max(geom.geoms, key=lambda p: p.area)
    p = polylabel(big, tolerance=0.0005)
    return [round(p.x, 5), round(p.y, 5)]


# ---------------------------------------------------------------- metrics
def district_stats(ch, d, cur, comp22, comp24, totals, days_out, redraw, lean, min_n=0):
    same = redraw.get((ch, d))
    unchanged = same is not None and same >= SAME_MIN
    comp_year = 2022 if unchanged else 2024
    comp = comp22 if unchanged else comp24
    now_by_cty = {c: upto(s, days_out) for c, s in cur.get((ch, d), {}).items()}
    then_by_cty = {c: upto(s, days_out) for c, s in comp.get((ch, d), {}).items()}
    now, then = sum(now_by_cty.values()), sum(then_by_cty.values())
    share_now = now / totals["now"] if totals["now"] else None
    share_then = then / totals[comp_year] if totals[comp_year] else None
    pace = (share_now / share_then - 1) if share_now is not None and share_then else None
    if min(now, then) < min_n:
        pace = None
    return {
        "chamber": ch, "district": d,
        "label": f"{CHAMBERS[ch][2]}-{d}",
        "comp_year": comp_year,
        "reason": "Same lines since 2022" if unchanged else CFG.get("reason", {}).get(ch, "Redrawn before 2024"),
        "same_pct": same,
        "lean": lean.get((ch, d)),
        "race24": RACE.get((ch, d)),
        "now": now, "then": then,
        "share_now": share_now, "share_then": share_then,
        "pace": None if pace is None else round(pace, 4),
        "by_county": sorted(({"county": c, "now": now_by_cty.get(c, 0), "then": then_by_cty.get(c, 0)}
                             for c in set(now_by_cty) | set(then_by_cty)
                             if c and (now_by_cty.get(c, 0) >= MIN_COUNTY_SHARE * max(now, 1)
                                       or then_by_cty.get(c, 0) >= MIN_COUNTY_SHARE * max(then, 1))),
                            key=lambda x: -(x["now"] or x["then"])),
    }


def make_demo(e22, e24, redraw, seed=2026):
    """Synthetic 2026 on CURRENT lines: each district's own comparison-year ballots
    up to DEMO_DAYS_OUT (2022 if lines unchanged, else 2024), tilted +/-20% per
    district. Built this way so the demo has no fake regional pattern; the only
    ups and downs are the random per-district tilts."""
    rnd = random.Random(seed)
    demo = _early()
    tot = lambda e: sum(upto(s, DEMO_DAYS_OUT) for (ch, _), b in e.items() if ch == "house" for s in b.values())
    scale24 = tot(e22) / tot(e24) if tot(e24) else 1   # put 2024-based districts on the same (midterm) scale
    for ch, d in sorted(set(e22) | set(e24), key=lambda k: (k[0], int(k[1]))):
        unchanged = redraw.get((ch, d), 0) >= SAME_MIN
        base = e22 if unchanged else e24
        t = rnd.uniform(0.8, 1.2) * (1 if unchanged else scale24)
        for c, s in base.get((ch, d), {}).items():
            demo[(ch, d)][c][DEMO_DAYS_OUT] = round(upto(s, DEMO_DAYS_OUT) * t)
    return demo


def build_mode(cur, e22, e24, days_out, redraw, lean):
    """cur/e22/e24 are {mode: early-structure}. Returns overall totals + per-district
    stats (overall), each carrying by_mode = {inperson: {...}, mail: {...}}."""
    def total(e, dd):
        return sum(upto(s, dd) for (ch, _), byc in e.items() if ch == "house" for s in byc.values())
    keys = set(e22["all"]) | set(e24["all"]) | set(cur["all"])
    out_totals, out_stats = {}, {}
    for m in MODES:
        totals = {"now": total(cur[m], days_out), 2022: total(e22[m], days_out), 2024: total(e24[m], days_out)}
        out_totals[m] = totals
        for ch, d in keys:
            if d == "0":
                continue
            s = district_stats(ch, d, cur[m], e22[m], e24[m], totals, days_out, redraw, lean,
                               min_n=MIN_MODE_BALLOTS)
            k = f"{ch}:{d}"
            if m == "all":
                out_stats[k] = s
                s["by_mode"] = {}
                if DEMO:
                    s["demo"] = demo_compare(DEMO["cur"].get((ch, d)), DEMO[s["comp_year"]].get((ch, d)),
                                             days_out, MIN_MODE_BALLOTS)
                continue
            base = out_stats[k]
            base["by_mode"][m] = {f: s[f] for f in ("now", "then", "share_now", "share_then", "pace")}
            per = {b["county"]: b for b in s["by_county"]}
            for b in base["by_county"]:
                b[f"now_{m}"] = per.get(b["county"], {}).get("now", 0)
    totals = dict(out_totals["all"])
    totals["by_mode"] = {m: out_totals[m] for m in MODES if m != "all"}
    return totals, out_stats


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "county").mkdir(exist_ok=True)
    e22, e24, e26 = load_early(2022), load_early(2024), load_early(2026)
    global RACE, DEMO
    d22, d24, d26 = load_demo(2022), load_demo(2024), load_demo(2026)
    redraw, (lean, RACE) = load_redraw(), (load_lean_tlc() if CFG.get("lean") == "tlc" else load_lean())

    # latest day in the file — but never later than today (guards against mistyped future dates)
    from datetime import date
    live_days = max(min((d for byc in e26["all"].values() for s in byc.values() for d in s), default=30),
                    (date(2026, 11, 3) - date.today()).days)
    has_demo = bool(d22 or d24)           # the state's files carry demographics (NC) or surname estimates (TX)
    DEMO = has_demo and {"cur": d26, 2022: d22, 2024: d24}
    live = build_mode(e26, e22, e24, live_days, redraw, lean)
    # demo mode: demographic make-up = each district's comparison year (no invented shifts)
    DEMO = has_demo and {"cur": {k: v for k, v in demo_from_comp(d22, d24, redraw).items()}, 2022: d22, 2024: d24}
    demo = build_mode(demo_modes(e22, e24, redraw), e22, e24, DEMO_DAYS_OUT, redraw, lean)
    modes = {"live": (live_days, *live), "demo": (DEMO_DAYS_OUT, *demo)}

    counties = {key(k): (v, k) for k, v in
                ((rec_name, g) for rec_name, g in read_county_shapes().items())}
    dshapes = {ch: (read_tlc(stem[4:]) if stem.startswith("tlc:") else read_shapes(f"cb_2024_{CFG['fips']}_{stem}_500k", fld))
               for ch, (stem, fld, _) in CHAMBERS.items()}

    state = {"counties": [], "modes": {},
             "meta": {"state": ST, "name": CFG["name"], "ev_start": CFG["ev_start"], "source": CFG["source"],
                      "has_demo": has_demo, "demo_kind": "surname" if ST == "TX" else "record",
                      "chambers": list(CHAMBERS)}}
    for m, (dd, totals, stats) in modes.items():
        state["modes"][m] = {"days_out": dd, "totals": totals,
                             "house_ahead": sum(1 for s in stats.values() if s["chamber"] == "house" and (s["pace"] or 0) > 0),
                             "house_n": sum(1 for s in stats.values() if s["chamber"] == "house" and s["pace"] is not None),
                             # compact per-district numbers for the statewide district maps
                             "dstats": {k: {"pace": s["pace"], "inperson": s["by_mode"]["inperson"]["pace"],
                                            "mail": s["by_mode"]["mail"]["pace"], "now": s["now"]}
                                        for k, s in stats.items()}}

    # statewide district outlines (House + Senate) for the Georgia map's district views;
    # each links to the county holding most of its early votes
    live_stats = modes["live"][2]
    state["districts"] = []                     # county = most comparison-year early votes
    for ch, shapes in dshapes.items():
        for st, g in sorted(shapes.items(), key=lambda kv: int(kv[0])):
            d = str(int(st))
            s = modes["demo"][2].get(f"{ch}:{d}") or live_stats.get(f"{ch}:{d}") or {}   # demo = full comparison-year counts
            bc = s.get("by_county") or []
            main = max(bc, key=lambda b: b["then"])["county"] if bc else None
            state["districts"].append({
                "chamber": ch, "district": d, "rings": rings(g, STATE_TOL), "label_at": label_pt(g),
                "lean": s.get("lean"), "comp_year": s.get("comp_year"), "county": main,
                "counties": [b["county"] for b in bc]})

    for ck, (cgeom, cname) in sorted(counties.items()):
        pieces, dists = [], set()
        for ch, shapes in dshapes.items():
            for st, g in shapes.items():
                if not g.intersects(cgeom):
                    continue
                inter = g.intersection(cgeom)
                if inter.area < MIN_PIECE * cgeom.area:
                    continue
                d = str(int(st))
                dists.add(f"{ch}:{d}")
                pieces.append({"chamber": ch, "district": d, "rings": rings(inter, COUNTY_TOL),
                               "label_at": label_pt(inter),
                               "continues": round(1 - inter.area / g.area, 3) > 0.01})
        cdata = {"county": ck, "name": cname, "outline": rings(cgeom, COUNTY_TOL),
                 "pieces": pieces, "modes": {}}
        summary = {"county": ck, "name": cname, "rings": rings(cgeom, STATE_TOL),
                   "label_at": label_pt(cgeom), "modes": {}}
        for m, (dd, totals, stats) in modes.items():
            ds = {k: stats[k] for k in dists if k in stats}
            cdata["modes"][m] = {"days_out": dd, "districts": ds}
            house = [s for s in ds.values() if s["chamber"] == "house" and s["pace"] is not None]
            now = sum(next((b["now"] for b in s["by_county"] if b["county"] == ck), 0)
                      for s in ds.values() if s["chamber"] == "house")
            now_m = {bm: sum(next((b.get(f"now_{bm}", 0) for b in s["by_county"] if b["county"] == ck), 0)
                             for s in ds.values() if s["chamber"] == "house") for bm in MODES[1:]}
            summary["modes"][m] = {"ahead": sum(1 for s in house if s["pace"] > 0), "n": len(house),
                                   "now": now, "now_by_mode": now_m}
        (OUT / "county" / f"{ck}.json").write_text(json.dumps(cdata, separators=(",", ":")), encoding="utf-8")
        state["counties"].append(summary)

    if has_demo:   # statewide make-up of early voters (House districts cover every voter once)
        for m, (dd, _, _) in modes.items():
            src = d26 if m == "live" else demo_from_comp(d22, d24, {}, all22=True)
            state["modes"][m]["demo"] = {str(y): demo_compare(statewide(src), statewide(dy), dd, 1)
                                         for y, dy in ((2022, d22), (2024, d24))}
    (OUT / "state.json").write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    page = ROOT / "web" / "ga" / "index.html"          # one page for every state
    if OUT != page.parent:
        shutil.copyfile(page, OUT / "index.html")
    print(f"wrote state.json + {len(counties)} county files; live days_out={live_days}, "
          f"live ballots={modes['live'][1]['now']:,}")


def demo_modes(e22, e24, redraw):
    """Demo snapshot per ballot mode (separate random tilts), plus their sum."""
    out = {"inperson": make_demo(e22["inperson"], e24["inperson"], redraw, seed=2026),
           "mail": make_demo(e22["mail"], e24["mail"], redraw, seed=2027)}
    out["all"] = _early()
    for m in ("inperson", "mail"):
        for k, byc in out[m].items():
            for c, s in byc.items():
                for d, n in s.items():
                    out["all"][k][c][d] += n
    return out


DEMO = {}
DIMS = ("race", "age", "gender", "party", "surname")   # surname = TX Hispanic / Asian estimate


def load_demo(year: int):
    """{(chamber, district): {dim: {group: {days_out: n}}}} or {} if the state has no demographics."""
    p = DATA / f"demo_{year}.csv"
    if not p.exists():
        return {}
    out = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))
    for r in csv.DictReader(p.open(encoding="utf-8")):
        out[(r["chamber"], r["district"])][r["dim"]][r["group"]][int(r["days_out"])] += int(r["ballots"])
    return out


def statewide(demo):
    """Sum House districts (every voter is in exactly one) into one statewide record."""
    tot = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (ch, _), dims in demo.items():
        if ch != "house":
            continue
        for dim, groups in dims.items():
            for g, series in groups.items():
                for d, n in series.items():
                    tot[dim][g][d] += n
    return tot


def demo_from_comp(d22, d24, redraw, all22=False):
    """Demo-mode make-up: each district's own comparison-year make-up."""
    if all22:
        return d22
    return {k: (d22 if redraw.get(k, 0) >= SAME_MIN else d24).get(k, {}) for k in set(d22) | set(d24)}


def demo_compare(now, then, days_out, min_n):
    """-> {dim: [{g, now, share_now, share_then}]} ; None if too few voters."""
    if not now or not then:
        return None
    out = {}
    for dim in DIMS:
        if dim not in now and dim not in then:
            continue
        gn = {g: upto(s, days_out) for g, s in now.get(dim, {}).items()}
        gt = {g: upto(s, days_out) for g, s in then.get(dim, {}).items()}
        tn, tt = sum(gn.values()), sum(gt.values())
        if tn < min_n or not tt:
            return None
        rows = []
        for g in sorted(set(gn) | set(gt), key=lambda g: -(gt.get(g, 0) + gn.get(g, 0))):
            rows.append({"g": g, "now": gn.get(g, 0), "share_now": round(gn.get(g, 0) / tn, 4),
                         "share_then": round(gt.get(g, 0) / tt, 4)})
        # privacy: don't show a separate count for tiny groups
        for r in rows:
            if 0 < r["now"] < MIN_GROUP:
                r["now"] = None
        out[dim] = rows
    return out


def read_tlc(plan: str):
    """Texas Legislative Council plan shapefile (Lambert conformal conic) -> lon/lat shapes."""
    import pyproj
    from shapely.ops import transform
    base = ROOT / "data" / "raw" / "tlc" / plan / plan / plan
    tr = pyproj.Transformer.from_crs(pyproj.CRS.from_wkt(base.with_suffix(".prj").read_text()), "EPSG:4326",
                                     always_xy=True)
    r = shapefile.Reader(str(base))
    return {str(sr.record["District"]): transform(tr.transform, to_shape(sr.shape.__geo_interface__)).buffer(0)
            for sr in r.iterShapeRecords()}


def load_lean_tlc():
    """Texas: 2024 presidential vote by district straight from the Legislative Council's
    Red-206 'Election Analysis' report for each current plan (no allocation needed)."""
    import os
    import xlrd
    plans = {ch: stem[4:] for ch, (stem, _, _) in CHAMBERS.items()}
    lean = {}
    for ch, plan in plans.items():
        b = xlrd.open_workbook(ROOT / "data" / "raw" / "tlc" / f"{plan}_r206_Election24G.xls", logfile=open(os.devnull, "w"))
        sh = b.sheet_by_index(1)
        rows = [sh.row_values(i) for i in range(sh.nrows)]
        hi = next(i for i, r in enumerate(rows) if any(str(x).startswith("Harris-D") for x in r))
        cd = next(j for j, x in enumerate(rows[hi]) if str(x).startswith("Harris-D"))
        cr = next(j for j, x in enumerate(rows[hi]) if str(x).startswith("Trump-R"))
        for r in rows[hi + 1:]:
            if isinstance(r[0], float) or str(r[0]).strip().isdigit() or isinstance(r[1], float):
                dcol = next(x for x in r[:3] if x != "")
                if str(dcol).upper() == "STATE":
                    continue
                d, dv, rv = str(int(float(dcol))), float(r[cd] or 0), float(r[cr] or 0)
                if dv + rv:
                    lean[(ch, d)] = round((dv - rv) / (dv + rv) * 100, 1)
        print(f"lean ({ch}): {sum(1 for k in lean if k[0] == ch)} districts from {plan} Red-206")
    return lean, {}


def read_county_shapes():
    r = shapefile.Reader(str(GEO / "cb_2024_us_county_500k" / "cb_2024_us_county_500k"))
    return {sr.record["NAME"]: to_shape(sr.shape.__geo_interface__).buffer(0)
            for sr in r.iterShapeRecords() if sr.record["STATEFP"] == CFG["fips"]}


if __name__ == "__main__":
    main()
