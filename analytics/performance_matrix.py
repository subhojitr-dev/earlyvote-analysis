"""
performance_matrix.py -- the one-screen read for a state:

  [1] OVERALL early-vote turnout, 2026 vs 2020 & 2022 (volume; caveated)
  [2] PARTISAN PERFORMANCE -- Dem-leaning vs Rep-leaning counties aggregated,
      each as % over/under its OWN share of the vote vs 2020 & 2022, + net read
  [3] COUNTY MATRIX -- every county's % over/under vs 2020 & 2022, with lean+group

Metric note: sections [2] and [3] use SHARE of the statewide vote (a normalized
percentage), so they are immune to the midterm-vs-presidential turnout gap and to
early voting being only partway done. Section [1] is raw VOLUME and therefore only
a rough gauge until we have same-point-in-cycle daily data + registered-voter
denominators (a data TODO) -- read it as context, not the partisan signal.

Run:  python analytics/performance_matrix.py GA
      python analytics/performance_matrix.py NC
"""
from __future__ import annotations

import sys

from turnout_compare import (compare, group_deviation, series_by_year_county,
                             load_current)

SPLIT = 0.50  # lean_dem >= SPLIT => Dem-leaning


def overall_turnout(state):
    hist = series_by_year_county(state)
    cur = load_current(state)
    cur_total = sum(cur.values())
    out = {}
    for y in sorted(hist):
        early = sum(c["early"] for c in hist[y].values())
        total = sum(c["total"] for c in hist[y].values())
        ref = early if early > 0 else total
        out[y] = {"ref_early": ref, "pct_of": cur_total / ref if ref else None,
                  "basis": "early" if early > 0 else "total"}
    return cur_total, out


def matrix(state="GA"):
    ref_years, basis, rows, hist, cur, lean = compare(state)
    cur_total, ov = overall_turnout(state)

    print(f"\n############  {state} EARLY-VOTE PERFORMANCE MATRIX  ############")
    print(f"#  2026 (in-progress) vs 2020 (presidential) & 2022 (midterm)")
    print(f"#  reference basis per year: " + ", ".join(f"{y}={basis[y]}" for y in ref_years))

    # ---- [1] OVERALL TURNOUT (volume) ----
    print("\n[1] OVERALL EARLY-VOTE TURNOUT  (raw volume -- context only, see note)")
    print(f"    2026 early ballots so far: {cur_total:,}")
    for y in ref_years:
        p = ov[y]["pct_of"]
        print(f"      = {p:5.0%} of {y}'s full early-vote total ({ov[y]['ref_early']:,}, {ov[y]['basis']})")
    print("    (2026 is incomplete + a midterm; treat as 'how far along', not turnout vs.)")

    # ---- [2] PARTISAN PERFORMANCE (share, normalized) ----
    gd = group_deviation(state, SPLIT)
    rename = {"Blue-leaning": "Dem-leaning", "Red-leaning": "Rep-leaning",
              "Tossup/Unknown": "Tossup/Unk"}
    print("\n[2] PARTISAN PERFORMANCE  (share of statewide vote -- normalized %, the signal)")
    print(f"    {'group':<13}{'#cty':>5}{'2026share':>11}" + "".join(f" {('vs'+str(y)):>9}" for y in ref_years))
    for g in ("Blue-leaning", "Red-leaning", "Tossup/Unknown"):
        rec = gd["groups"][g]
        if rec["n"] == 0:
            continue
        line = f"    {rename[g]:<13}{rec['n']:>5}{rec['cur_share']:>10.1%}"
        for y in ref_years:
            v = rec["dev"].get(y)
            line += f" {('%+.1f%%' % (v*100)) if v is not None else 'n/a':>9}"
        print(line)
    for y in ref_years:
        b = gd["groups"]["Blue-leaning"]["dev"].get(y)
        r = gd["groups"]["Red-leaning"]["dev"].get(y)
        if b is None or r is None:
            continue
        net = b - r
        print(f"    -> vs {y}: Dem-leaning {b*100:+.1f}% vs Rep-leaning {r*100:+.1f}%  "
              f"=> net {net*100:+.1f} pts toward {'DEMOCRATIC' if net > 0 else 'REPUBLICAN'} turnout")

    # ---- [3] COUNTY MATRIX ----
    print("\n[3] COUNTY MATRIX  (each county's % over/under its own share)")
    print(f"    {'county':<16}{'lean':>5} {'grp':>3}{'2026%':>8}" + "".join(f" {('vs'+str(y)):>9}" for y in ref_years))
    for r in sorted(rows, key=lambda x: -(x["lean_dem"] or 0)):
        ld = r["lean_dem"]
        grp = "?" if ld is None else ("D" if ld >= SPLIT else "R")
        line = f"    {r['county'][:16]:<16}{(ld or 0):>5.0%} {grp:>3}{r['cur_share']:>7.2%}"
        for y in ref_years:
            v = r[f"vs_{y}"]
            line += f" {('%+.1f%%' % (v*100)) if v is not None else 'n/a':>9}"
        print(line)
    if 2022 not in ref_years:
        print("\n    (!) 2022 missing -- add it for the midterm-to-midterm comparison.")


if __name__ == "__main__":
    matrix(sys.argv[1].upper() if len(sys.argv) > 1 else "GA")
