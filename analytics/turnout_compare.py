"""
turnout_compare.py -- the core question, answered directly:

  For each county, how is THIS cycle's early-vote participation running vs. past
  reference cycles (2020, 2022, 2024) -- over-performing or under-performing, and
  by how much? Then: are the Democratic strongholds (Fulton, DeKalb, Gwinnett,
  Cobb, Clayton, Chatham/Savannah ...) turning out heavy? If yes -> good D signal.

WHY WE COMPARE *SHARE*, NOT RAW COUNTS (read this):
  Raw early-vote counts can't be compared across these years:
    - 2020 & 2024 are PRESIDENTIAL (high turnout); 2022 & 2026 are MIDTERMS (lower).
      Raw counts would show 2026 "down 35%" everywhere -- that's the midterm gap,
      not a party signal.
    - Mid-election you only have part of the ballots in, so totals aren't comparable.
  So we use each county's SHARE of the statewide vote. Share cancels both problems:
  if Fulton was 12.8% of GA's vote in 2024 and is 14.1% of the early vote now, the
  Atlanta metro is OVER-indexing -> Democratic strongholds punching above weight.

DATA BASIS PER YEAR (printed in the header):
  - "early" = compared against that year's EARLY-vote share (best; needs the mode
    breakdown). NC has it for 2020 & 2024.
  - "total" = that year only had total votes in our source (e.g. GA 2024 in MEDSL),
    so we compare against total-vote share. Early-share and total-share track each
    other closely, so this is still a sound reference -- just slightly less precise.
  For GA's authoritative early-vote-by-county history, the real source is the GA
  Secretary of State daily files / UF Election Lab, not MEDSL (a data TODO).

Run:  python analytics/turnout_compare.py GA
      python analytics/turnout_compare.py NC
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"

EARLY = {"ONE STOP", "EARLY VOTING", "ADVANCED VOTING", "ADVANCE VOTING", "ADVANCED",
         "IN PERSON", "EARLY", "LATE EARLY", "LATE VOTES",
         "ABSENTEE BY MAIL", "ABSENTEE", "MAIL", "ABSENTEE/MAIL"}
TOTAL_LABEL = "TOTAL"

# Democratic strongholds the user named (Atlanta metro + Savannah=Chatham).
GA_STRONGHOLDS = {"FULTON", "DEKALB", "GWINNETT", "COBB", "CLAYTON", "CHATHAM"}


def series_by_year_county(state: str):
    """{year: {county: {'early': e, 'total': t}}} from the historical baseline.

    Two-pass + order-independent: a county's total is the TOTAL-row value if one
    exists (some years report only a TOTAL, e.g. GA 2024), otherwise the sum of
    its per-mode rows. Never both -- mixing them double-counts the county."""
    early = defaultdict(lambda: defaultdict(int))
    modes_sum = defaultdict(lambda: defaultdict(int))   # sum of all non-TOTAL modes
    total_row = defaultdict(lambda: defaultdict(int))   # explicit TOTAL rows
    for r in csv.DictReader((BASE / "baseline" / "county_results.csv").open(encoding="utf-8")):
        if r["state"] != state:
            continue
        y, cty, m, v = int(r["year"]), r["county_name"].upper(), r["mode"].upper().strip(), int(r["votes"])
        if m == TOTAL_LABEL:
            total_row[y][cty] += v
            continue
        if m in EARLY:
            early[y][cty] += v
        modes_sum[y][cty] += v
    out = {}
    for y in set(early) | set(modes_sum) | set(total_row):
        counties = set(early[y]) | set(modes_sum[y]) | set(total_row[y])
        out[y] = {c: {"early": early[y].get(c, 0),
                      "total": total_row[y][c] if total_row[y].get(c) else modes_sum[y].get(c, 0)}
                  for c in counties}
    return out


def lean_by_county(state: str):
    return {r["county_name"].upper(): float(r["lean_dem"])
            for r in csv.DictReader((BASE / "baseline" / "county_lean.csv").open(encoding="utf-8"))
            if r["state"] == state and r["lean_dem"]}


def load_current(state: str):
    """This-cycle early votes per county. Prefers a REAL feed at
    data/live/{state}_current.csv (written by the ingestors); falls back to the
    synthetic data/fixtures/{state}_current.csv until live voting opens."""
    fips2name = {r["county_fips"]: r["county_name"].upper()
                 for r in csv.DictReader((BASE / "baseline" / "county_lean.csv").open(encoding="utf-8"))
                 if r["state"] == state}
    live = BASE / "live" / f"{state.lower()}_current.csv"
    src = live if live.exists() else BASE / "fixtures" / f"{state.lower()}_current.csv"
    out = {}
    for r in csv.DictReader(src.open(encoding="utf-8")):
        name = fips2name.get(r["county_fips"])
        if name:
            out[name] = int(r["ballots"])
    return out


def _shares(counts):
    tot = sum(counts.values()) or 1
    return {k: v / tot for k, v in counts.items()}


def compare(state: str):
    hist = series_by_year_county(state)
    lean = lean_by_county(state)
    cur = load_current(state)
    ref_years = sorted(hist)

    # pick a basis per year: early if that year has any early-mode data, else total
    basis = {}
    ref_sh = {}
    for y in ref_years:
        early_tot = sum(c["early"] for c in hist[y].values())
        b = "early" if early_tot > 0 else "total"
        basis[y] = b
        ref_sh[y] = _shares({c: hist[y][c][b] for c in hist[y]})

    cur_sh = _shares(cur)
    rows = []
    for cty in sorted(cur):
        row = {"county": cty, "lean_dem": lean.get(cty), "cur_share": cur_sh.get(cty, 0)}
        for y in ref_years:
            base = ref_sh[y].get(cty)
            row[f"vs_{y}"] = (cur_sh.get(cty, 0) / base - 1) if base else None
        rows.append(row)
    return ref_years, basis, rows, hist, cur, lean


def group_deviation(state, lean_split=0.50):
    """Blue-leaning vs Red-leaning DISTRICTS, each as a % over/under its own
    share in 2020 and 2022. This is the partisan turnout battle in one table:
    if blue districts are over-performing their baseline share while red ones
    under-perform, that's a net Democratic turnout edge (and vice-versa).
    Uses SHARE (normalized %), so it's immune to the midterm/presidential gap."""
    ref_years, basis, _rows, hist, cur, lean = compare(state)
    total_cur = sum(cur.values()) or 1
    groups = {"Blue-leaning": [], "Red-leaning": [], "Tossup/Unknown": []}
    for c in cur:
        ld = lean.get(c)
        g = ("Tossup/Unknown" if ld is None
             else "Blue-leaning" if ld >= lean_split else "Red-leaning")
        groups[g].append(c)

    out = {"ref_years": ref_years, "basis": basis, "groups": {}}
    for gname, cties in groups.items():
        cur_share = sum(cur.get(c, 0) for c in cties) / total_cur
        rec = {"n": len(cties), "cur_share": cur_share, "dev": {}}
        for y in ref_years:
            b = basis[y]
            tot_y = sum(hist[y][c][b] for c in hist[y]) or 1
            ref_share = sum(hist[y].get(c, {}).get(b, 0) for c in cties) / tot_y
            rec["dev"][y] = (cur_share / ref_share - 1) if ref_share else None
        out["groups"][gname] = rec
    return out


def composite_lean(state):
    """Aggregate 'Dem tilt' of the early electorate, per year. For each year we
    weight every county's DEM two-party lean (fixed, from past results) by that
    county's SHARE of the early vote that year. Since the lean is fixed, changes
    across years come purely from WHERE the early votes are concentrated -- i.e.
    a higher number = the early electorate is coming from more-Democratic places.
    Returns (years, {year->composite, 'cur'->2026 composite})."""
    hist = series_by_year_county(state)
    lean = lean_by_county(state)
    cur = load_current(state)
    years = sorted(hist)

    def comp(shares):
        num = den = 0.0
        for c, v in shares.items():
            L = lean.get(c)
            if L is None:
                continue
            num += v * L
            den += v
        return (num / den) if den else None

    def yr_shares(y):
        early = {c: hist[y][c]["early"] for c in hist[y]}
        src = early if sum(early.values()) > 0 else {c: hist[y][c]["total"] for c in hist[y]}
        tot = sum(src.values()) or 1
        return {c: src[c] / tot for c in src}

    out = {y: comp(yr_shares(y)) for y in years}
    ctot = sum(cur.values()) or 1
    out["cur"] = comp({c: cur[c] / ctot for c in cur})
    return years, out


def turnout_progress(state):
    """Progress gauge: 2026 early votes so far as a % of each county's TOTAL
    turnout (all modes) in a prior year. As early voting runs, this climbs; >100%
    means early votes alone have already exceeded that entire past election.
    Returns (years, per_county{county->{year->pct}}, aggregate{year->pct})."""
    hist = series_by_year_county(state)
    cur = load_current(state)
    years = sorted(hist)
    per = {}
    for c in cur:
        per[c] = {}
        for y in years:
            tot = hist[y].get(c, {}).get("total", 0)
            per[c][y] = (cur[c] / tot) if tot else None
    agg = {}
    for y in years:
        num = sum(cur.values())
        den = sum(hist[y][c]["total"] for c in hist[y])
        agg[y] = (num / den) if den else None
    return years, per, agg


def turnout_rate(state):
    """TRUE early-vote turnout rate = 2026 early ballots / registered voters,
    per county and aggregate. Needs data/reference/registration.csv (run
    build_registration.py). Returns (per_county{name->rate}, aggregate_rate) or
    (None, None) if registration data isn't available."""
    reg_file = BASE / "reference" / "registration.csv"
    if not reg_file.exists():
        return None, None
    reg = {}
    for r in csv.DictReader(reg_file.open(encoding="utf-8")):
        if r["state"] == state and r.get("registered"):
            reg[r["county_name"].upper()] = int(r["registered"])
    cur = load_current(state)
    per = {c: (cur[c] / reg[c]) for c in cur if reg.get(c)}
    tot_reg = sum(reg.get(c, 0) for c in cur)
    agg = (sum(cur.values()) / tot_reg) if tot_reg else None
    return per, agg


def report(state="GA"):
    ref_years, basis, rows, _hist, _cur, _lean = compare(state)
    miss = [y for y in (2020, 2022, 2024) if y not in ref_years]

    print(f"\n========  {state}: 2026 early-vote participation vs reference cycles  ========")
    basis_str = ", ".join(f"{y}={basis[y]}" for y in ref_years)
    print(f"  reference years: {ref_years}  [basis: {basis_str}]"
          + (f"   (!) MISSING: {miss}" if miss else ""))
    print("  metric = county's SHARE of the statewide vote (over/under-index vs that year)")
    print("  positive = bigger slice of the electorate than that year (turning out heavy)\n")

    named = ([r for r in rows if r["county"] in GA_STRONGHOLDS] if state == "GA"
             else sorted(rows, key=lambda x: -(x["lean_dem"] or 0))[:8])
    label = ("Democratic strongholds (Atlanta metro + Savannah/Chatham)" if state == "GA"
             else "most-Democratic counties")
    print(f"  --- {label} ---")
    print(f"  {'county':<12} {'lean':>5} {'cur%':>6}" + "".join(f" {('vs'+str(y)):>9}" for y in ref_years))
    for r in sorted(named, key=lambda x: -x["cur_share"]):
        line = f"  {r['county']:<12} {(r['lean_dem'] or 0):>5.0%} {r['cur_share']:>6.2%}"
        for y in ref_years:
            v = r[f"vs_{y}"]
            line += f" {('%+.1f%%' % (v*100)) if v is not None else 'n/a':>9}"
        print(line)

    # ---- BLUE vs RED district deviation (the partisan turnout battle) ----
    gd = group_deviation(state)
    print("\n  --- blue- vs red-leaning DISTRICTS: % over/under their own baseline share ---")
    print(f"  {'group':<16}{'#cty':>5}{'2026share':>11}" + "".join(f" {('vs'+str(y)):>9}" for y in ref_years))
    for gname in ("Blue-leaning", "Red-leaning", "Tossup/Unknown"):
        rec = gd["groups"][gname]
        if rec["n"] == 0:
            continue
        line = f"  {gname:<16}{rec['n']:>5}{rec['cur_share']:>10.1%}"
        for y in ref_years:
            v = rec["dev"].get(y)
            line += f" {('%+.1f%%' % (v*100)) if v is not None else 'n/a':>9}"
        print(line)
    # net read: blue deviation minus red deviation per year
    for y in ref_years:
        b = gd["groups"]["Blue-leaning"]["dev"].get(y)
        r = gd["groups"]["Red-leaning"]["dev"].get(y)
        if b is None or r is None:
            continue
        net = b - r
        who = "Democratic" if net > 0 else "Republican"
        print(f"  vs {y}: blue {b*100:+.1f}% vs red {r*100:+.1f}%  ->  net {net*100:+.1f} pts "
              f"toward {who} turnout")

    def avg_vs(year, subset):
        num = den = 0.0
        for r in subset:
            v = r.get(f"vs_{year}")
            if v is None:
                continue
            num += v * r["cur_share"]; den += r["cur_share"]
        return (num / den) if den else None

    print("\n  --- read (size-weighted across those counties) ---")
    for y in ref_years:
        a = avg_vs(y, named)
        if a is None:
            continue
        verdict = ("OVER-performing -- good Democratic turnout signal" if a > 0.01
                   else "UNDER-performing -- soft Democratic turnout" if a < -0.01
                   else "roughly on par")
        print(f"  share of vote vs {y} ({basis[y]}): {a*100:+.1f}%  -> {verdict}")
    if 2022 in miss:
        print("\n  NOTE: 2026 is a MIDTERM; the cleanest yardstick is 2022 (also midterm).")
        print("  2020/2024 are presidential -- read these as directional share-shifts.")
        print("  Adding 2022 (and GA SOS early-vote files) is the top data TODO.")


if __name__ == "__main__":
    report(sys.argv[1].upper() if len(sys.argv) > 1 else "GA")
