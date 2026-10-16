"""
add_tx_baseline.py — add Texas to data/baseline/county_results.csv from MIT Election
Lab's official 2022 Texas precinct file (2022 GOVERNOR: Abbott vs O'Rourke), so the
main dashboard can show TX. 2022 only, matching the comparison year (user's choice).

Input:  data/raw/medsl/tx22.zip  (github.com/MEDSL/2022-elections-official →
        individual_states/2022-tx-local-precinct-general.zip; gitignored)
Output: TX rows in county_results.csv (mode TOTAL — Texas reports no mode split);
        then run analytics/county_lean.py to refresh county_lean.csv.

Run:  python analytics/add_tx_baseline.py && python analytics/county_lean.py
"""
from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "medsl" / "tx22.zip"
OUT = ROOT / "data" / "baseline" / "county_results.csv"


def main():
    votes, names = Counter(), {}
    with zipfile.ZipFile(SRC) as z, z.open("TX-cleaned.csv") as fh:
        for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
            if r["office"] != "GOVERNOR" or r["stage"] != "GEN":
                continue
            fips = r["county_fips"].zfill(5)
            party = r["party_simplified"] if r["party_simplified"] in ("DEMOCRAT", "REPUBLICAN") else "OTHER"
            votes[(fips, party)] += int(r["votes"] or 0)
            names[fips] = r["county_name"].strip().upper()
    rows = [r for r in csv.DictReader(OUT.open(encoding="utf-8")) if r["state"] != "TX"]
    fields = ["year", "office", "state", "county_fips", "county_name", "party", "mode", "votes"]
    rows += [{"year": 2022, "office": "GOVERNOR", "state": "TX", "county_fips": f, "county_name": names[f],
              "party": p, "mode": "TOTAL", "votes": v} for (f, p), v in sorted(votes.items())]
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    d = sum(v for (_f, p), v in votes.items() if p == "DEMOCRAT")
    r_ = sum(v for (_f, p), v in votes.items() if p == "REPUBLICAN")
    print(f"TX 2022 governor: {len(names)} counties, D {d:,} / R {r_:,} ({d / (d + r_):.1%} D two-party)")


if __name__ == "__main__":
    main()
