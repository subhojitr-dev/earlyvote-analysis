"""
build_registration.py — registered-voter denominators per county, so turnout can
be expressed as a TRUE RATE (early votes / registered voters) rather than only a
ratio against a past election's turnout.

Output: data/reference/registration.csv  (state, county_fips, county_name, registered)

Two modes:
  • REAL (preferred): if data/reference/registration_real.csv exists (same columns,
    populated from each state's Secretary-of-State current registration-by-county
    files), it is used verbatim. Drop real files there when available.
  • ESTIMATE (default): registered ≈ 2024 total turnout / TURNOUT_ASSUMPTION. This
    is a stand-in so the rate metric works today; replace with real files for
    accuracy. Presidential turnout of registered voters runs ~70–75%.

Run:  python analytics/build_registration.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
RESULTS = Path(__file__).resolve().parent.parent / "data" / "baseline" / "county_results.csv"
OUT = REF / "registration.csv"
REAL = REF / "registration_real.csv"
TURNOUT_ASSUMPTION = 0.72  # est. share of registered voters who turned out in 2024


def from_results():
    # per (state, fips, county) 2024 total (TOTAL row if present else sum modes)
    tot_row = defaultdict(int); modes = defaultdict(int); has = defaultdict(bool)
    name = {}
    for r in csv.DictReader(RESULTS.open(encoding="utf-8")):
        if r["year"] != "2024":
            continue
        k = (r["state"], r["county_fips"]); name[k] = r["county_name"]
        if r["mode"].upper().strip() == "TOTAL":
            tot_row[k] += int(r["votes"]); has[k] = True
        else:
            modes[k] += int(r["votes"])
    rows = []
    for k in sorted(name):
        total = tot_row[k] if has[k] else modes[k]
        rows.append({"state": k[0], "county_fips": k[1], "county_name": name[k],
                     "registered": round(total / TURNOUT_ASSUMPTION)})
    return rows


def main():
    REF.mkdir(parents=True, exist_ok=True)
    if REAL.exists():
        rows = list(csv.DictReader(REAL.open(encoding="utf-8")))
        note = f"REAL (from {REAL.name})"
    else:
        rows = from_results()
        note = f"ESTIMATE (2024 turnout / {TURNOUT_ASSUMPTION})"
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["state", "county_fips", "county_name", "registered"])
        w.writeheader(); w.writerows(rows)
    tot = sum(int(r["registered"]) for r in rows)
    print(f"  wrote {len(rows)} counties -> {OUT}  [{note}]  total registered ~{tot:,}")


if __name__ == "__main__":
    main()
