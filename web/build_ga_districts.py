"""
build_ga_districts.py — data for the Georgia State House / State Senate drill-down
page (web/ga/).

Combines
  data/ga_districts/early_{2022,2024,2026}.csv   (from ingestor/ga_districts.py)
  data/ga_districts/redraw.csv                   (lines-unchanged proxy)
  data/ga_districts/xwalk_2024.csv               (precinct -> district weights)
  election-forecast/data/raw/2024-PRESIDENT-precinct-general.csv   (lean)
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

Run:  python web/build_ga_districts.py
"""
from __future__ import annotations

import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path

import shapefile  # pyshp
from shapely.geometry import shape as to_shape, mapping
from shapely.ops import polylabel

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ga_districts"
GEO = ROOT / "data" / "raw" / "geo"
PRES = ROOT.parent / "election-forecast" / "data" / "raw" / "2024-PRESIDENT-precinct-general.csv"
OUT = ROOT / "web" / "ga"

SAME_MIN = 0.90          # >= 90% same voters => "lines unchanged" (movers add ~2-4% noise)
DEMO_DAYS_OUT = 15       # demo snapshot = one week into early voting
STATE_TOL = 0.004        # geometry simplification (degrees) for the state map
COUNTY_TOL = 0.0006      # finer for the single-county map
LEAN_MIN_COVERAGE = 0.90  # show lean only if >= 90% of the district's voters are matched
MIN_COUNTY_SHARE = 0.005  # hide counties with < 0.5% of a district's ballots (address noise)
MIN_PIECE = 0.003        # drop district pieces < 0.3% of the county's area (slivers)
CHAMBERS = {"house": ("sldl", "SLDLST", "HD"), "senate": ("sldu", "SLDUST", "SD")}
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
    """2024 presidential D/R votes per district, allocating each precinct by its
    share of 2024 early voters in each district (handles split precincts)."""
    w = defaultdict(lambda: defaultdict(float))            # (county, precinct, ch) -> {dist: voters}
    for r in csv.DictReader((DATA / "xwalk_2024.csv").open(encoding="utf-8")):
        w[(key(r["county"]), r["precinct"].upper(), r["chamber"])][r["district"]] += int(r["voters"])
    votes = defaultdict(lambda: [0, 0])                    # (county, precinct) -> [D, R]
    with PRES.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["state"] != "GEORGIA" or r["office"] != "US PRESIDENT":
                continue
            i = {"DEMOCRAT": 0, "REPUBLICAN": 1}.get(r["party_simplified"])
            if i is not None:
                votes[(key(r["county_name"]), r["precinct"].upper())][i] += int(r["votes"] or 0)
    lean = defaultdict(lambda: [0.0, 0.0])
    # coverage: share of each district's 2024 early voters whose precinct we could
    # match to a presidential result (precinct names vs codes differ by county)
    have = {k for k in votes}
    cov_all, cov_hit = defaultdict(float), defaultdict(float)
    for (cty, pct, ch), dist in w.items():
        for k, v in dist.items():
            cov_all[(ch, k)] += v
            if (cty, pct) in have:
                cov_hit[(ch, k)] += v
    matched = total = 0
    for (cty, pct), (d, rep) in votes.items():
        total += d + rep
        hit = False
        for ch in CHAMBERS:
            dist = w.get((cty, pct, ch))
            if not dist:
                continue
            hit = True
            s = sum(dist.values())
            for k, v in dist.items():
                lean[(ch, k)][0] += d * v / s
                lean[(ch, k)][1] += rep * v / s
        matched += (d + rep) if hit else 0
    print(f"lean: {matched / total:.1%} of 2024 presidential votes matched to districts")
    return {k: round((d - r) / (d + r) * 100, 1) for k, (d, r) in lean.items()
            if d + r and cov_hit[k] / cov_all[k] >= LEAN_MIN_COVERAGE}


# ---------------------------------------------------------------- geometry
def read_shapes(stem: str, field: str, state_only=True):
    r = shapefile.Reader(str(GEO / stem / stem))
    out = {}
    for sr in r.iterShapeRecords():
        rec = sr.record.as_dict()
        if state_only and rec.get("STATEFP") != "13":
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
        "reason": "Same lines since 2022" if unchanged else "Redrawn before 2024",
        "same_pct": same,
        "lean": lean.get((ch, d)),
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
    redraw, lean = load_redraw(), load_lean()

    live_days = min((d for byc in e26["all"].values() for s in byc.values() for d in s), default=30)
    modes = {
        "live": (live_days, *build_mode(e26, e22, e24, live_days, redraw, lean)),
        "demo": (DEMO_DAYS_OUT, *build_mode(demo_modes(e22, e24, redraw), e22, e24, DEMO_DAYS_OUT, redraw, lean)),
    }

    counties = {key(k): (v, k) for k, v in
                ((rec_name, g) for rec_name, g in read_county_shapes().items())}
    dshapes = {ch: read_shapes(f"cb_2024_13_{stem}_500k", fld) for ch, (stem, fld, _) in CHAMBERS.items()}

    state = {"counties": [], "modes": {}}
    for m, (dd, totals, stats) in modes.items():
        state["modes"][m] = {"days_out": dd, "totals": totals,
                             "house_ahead": sum(1 for s in stats.values() if s["chamber"] == "house" and (s["pace"] or 0) > 0),
                             "house_n": sum(1 for s in stats.values() if s["chamber"] == "house" and s["pace"] is not None)}

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
        summary = {"county": ck, "name": cname, "rings": rings(cgeom, STATE_TOL), "modes": {}}
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

    (OUT / "state.json").write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
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


def read_county_shapes():
    r = shapefile.Reader(str(GEO / "cb_2024_us_county_500k" / "cb_2024_us_county_500k"))
    return {sr.record["NAME"]: to_shape(sr.shape.__geo_interface__).buffer(0)
            for sr in r.iterShapeRecords() if sr.record["STATEFP"] == "13"}


if __name__ == "__main__":
    main()
