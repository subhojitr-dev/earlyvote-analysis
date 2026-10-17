"""
add_baseline_2022.py — add a state to data/baseline/county_results.csv from MIT Election
Lab's official 2022 precinct file (2022 GOVERNOR), so the main dashboard can show it.
2022 only, matching the comparison year (user's choice). Used for TX (Abbott vs
O'Rourke) and ME (Mills vs LePage).

Input:  data/raw/medsl/{st}22.zip  (github.com/MEDSL/2022-elections-official →
        individual_states/2022-{st}-local-precinct-general.zip; gitignored)
Output: that state's rows in county_results.csv (mode TOTAL); then run
        analytics/county_lean.py to refresh county_lean.csv.

Run:  python analytics/add_baseline_2022.py TX && python analytics/county_lean.py
      python analytics/add_baseline_2022.py ME && python analytics/county_lean.py
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "baseline" / "county_results.csv"
MEMBER = {"TX": "TX-cleaned.csv", "ME": "me_final.csv"}


def main(st: str = "TX"):
    votes, names = Counter(), {}
    with zipfile.ZipFile(ROOT / "data" / "raw" / "medsl" / f"{st.lower()}22.zip") as z, z.open(MEMBER[st]) as fh:
        for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
            if r["office"] != "GOVERNOR" or r["stage"] != "GEN":
                continue
            fips = r["county_fips"].zfill(5)
            party = r["party_simplified"] if r["party_simplified"] in ("DEMOCRAT", "REPUBLICAN") else "OTHER"
            votes[(fips, party)] += int(r["votes"] or 0)
            names[fips] = r["county_name"].strip().upper()
    rows = [r for r in csv.DictReader(OUT.open(encoding="utf-8")) if r["state"] != st]
    fields = ["year", "office", "state", "county_fips", "county_name", "party", "mode", "votes"]
    rows += [{"year": 2022, "office": "GOVERNOR", "state": st, "county_fips": f, "county_name": names[f],
              "party": p, "mode": "TOTAL", "votes": v} for (f, p), v in sorted(votes.items())]
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    d = sum(v for (_f, p), v in votes.items() if p == "DEMOCRAT")
    r_ = sum(v for (_f, p), v in votes.items() if p == "REPUBLICAN")
    print(f"{st} 2022 governor: {len(names)} counties, D {d:,} / R {r_:,} ({d / (d + r_):.1%} D two-party)")


if __name__ == "__main__":
    main((sys.argv[1] if len(sys.argv) > 1 else "TX").upper())
