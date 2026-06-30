"""
county_lean.py — the partisan baseline that powers the early-vote signal.

Two products, both per county, from data/baseline/county_results.csv:

  1. LEAN   — two-party Dem share of each county's TOTAL vote, blended across
              the baseline cycles. This is "what this county normally does".
              Heavy-Dem county => high lean; heavy-Rep => low lean.

  2. EARLY MIX — what share of each county's vote was historically cast EARLY
              (in-person early + mail), vs on election day. Tells us the
              normal early-vote propensity so a live surge/shortfall is
              measured against the right yardstick, county by county.

The live signal (evote_signal.py) combines these: as early ballots come in by
county, weight each county by its LEAN to read whether the early electorate is
tilting more D or more R than the baseline mix would predict.

Run:  python analytics/county_lean.py   -> writes data/baseline/county_lean.csv
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data" / "baseline"
SRC = BASE / "county_results.csv"
OUT = BASE / "county_lean.csv"

# Normalize the drifting mode labels into 3 buckets. "TOTAL" is a GA summary
# row we MUST drop (it double-counts the others).
EARLY_IN_PERSON = {"ONE STOP", "EARLY VOTING", "ADVANCED VOTING", "ADVANCE VOTING",
                   "IN PERSON", "EARLY"}
EARLY_MAIL = {"ABSENTEE BY MAIL", "ABSENTEE", "MAIL", "ABSENTEE/MAIL"}
ELECTION_DAY = {"ELECTION DAY", "POLLING PLACE"}
DROP = {"TOTAL"}  # summary rows; ignore


def bucket(mode: str) -> str | None:
    m = mode.upper().strip()
    if m in DROP:
        return None
    if m in EARLY_IN_PERSON:
        return "early_inperson"
    if m in EARLY_MAIL:
        return "early_mail"
    if m in ELECTION_DAY:
        return "election_day"
    return "other"  # provisional, unknown — counted in totals, not in early/eday


def load_rows():
    with SRC.open(encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def build():
    # per (state, fips, county): party totals and bucket totals
    party = defaultdict(lambda: defaultdict(int))   # key -> {DEMOCRAT: n, ...}
    buckets = defaultdict(lambda: defaultdict(int))  # key -> {early_inperson: n,...}
    names = {}
    for r in load_rows():
        b = bucket(r["mode"])
        if b is None:
            continue
        key = (r["state"], r["county_fips"])
        names[key] = r["county_name"]
        v = int(r["votes"])
        party[key][r["party"]] += v
        buckets[key][b] += v

    out = []
    for key in sorted(party):
        st, fips = key
        d = party[key].get("DEMOCRAT", 0)
        rep = party[key].get("REPUBLICAN", 0)
        two_party = d + rep
        lean = round(d / two_party, 4) if two_party else None  # Dem two-party share
        b = buckets[key]
        total = sum(b.values())
        early = b["early_inperson"] + b["early_mail"]
        out.append({
            "state": st, "county_fips": fips, "county_name": names[key],
            "dem_votes": d, "rep_votes": rep, "two_party": two_party,
            "lean_dem": lean,
            "early_inperson": b["early_inperson"], "early_mail": b["early_mail"],
            "election_day": b["election_day"],
            "early_share": round(early / total, 4) if total else None,
        })
    return out


def main():
    rows = build()
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    # quick summary
    nc = [r for r in rows if r["state"] == "NC" and r["lean_dem"]]
    ga = [r for r in rows if r["state"] == "GA" and r["lean_dem"]]
    def statewide(rs):
        d = sum(r["dem_votes"] for r in rs); t = sum(r["two_party"] for r in rs)
        es = sum(r["early_inperson"] + r["early_mail"] for r in rs)
        tot = sum(r["early_inperson"] + r["early_mail"] + r["election_day"] for r in rs)
        return d / t, es / tot
    for label, rs in (("NC", nc), ("GA", ga)):
        lean, em = statewide(rs)
        print(f"  {label}: {len(rs)} counties | statewide Dem two-party {lean:.1%} "
              f"| early-vote share {em:.1%}")
    print(f"\n  wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
