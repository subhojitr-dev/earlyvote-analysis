"""
build_baseline.py — extract a compact NC/GA county baseline from the big
nationwide MEDSL precinct-general files (which live in the election-forecast
project, gitignored at ~1.2 GB). We only need NC + GA, aggregated to county +
party + vote-mode, so the output is tiny and lives inside this repo.

Output: data/baseline/county_results.csv with one row per
        (year, office, state, county_fips, county_name, party, mode) -> votes

From this single file we derive BOTH things the signal needs:
  • county partisan lean   = two-party Dem share per county (all modes)
  • early-vote mix baseline = share of each county's vote cast EARLY
                              (mode in ONE STOP / ABSENTEE / EARLY) historically

Run:  python analytics/build_baseline.py
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

# Where the big source files live (election-forecast/data/raw). Override with env.
SRC_DIR = Path(os.environ.get(
    "MEDSL_SRC",
    r"C:\Users\subho\election-forecast\data\raw",
))

# Source file -> (year, office) we care about. Add more as needed.
SOURCES = {
    "2018-SENATE-precinct-general.csv": (2018, "SENATE"),
    "2020-SENATE-precinct-general.csv": (2020, "SENATE"),
    "2022-SENATE-precinct-general.csv": (2022, "SENATE"),  # doi:10.7910/DVN/IAD3XR — ideal midterm comparator
    "2024-PRESIDENT-precinct-general.csv": (2024, "PRESIDENT"),
    "2024-SENATE-precinct-general.csv": (2024, "SENATE"),
}

STATES = {"NC", "GA"}
OUT = Path(__file__).resolve().parent.parent / "data" / "baseline" / "county_results.csv"

# csv module chokes on huge fields in some MEDSL rows; bump the limit.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def main() -> None:
    # key: (year, office, state, fips, county, party, mode) -> votes
    agg: dict[tuple, int] = defaultdict(int)
    for fname, (year, office) in SOURCES.items():
        path = SRC_DIR / fname
        if not path.exists():
            print(f"  SKIP (missing): {path}")
            continue
        print(f"  reading {fname} ...", flush=True)
        n = 0
        with path.open("r", encoding="utf-8", newline="") as fh:
            r = csv.DictReader(fh)
            for row in r:
                if row.get("state_po") not in STATES:
                    continue
                try:
                    votes = int(float(row.get("votes") or 0))
                except ValueError:
                    continue
                key = (
                    year, office, row["state_po"],
                    row.get("county_fips", ""), row.get("county_name", ""),
                    (row.get("party_simplified") or "OTHER").upper(),
                    (row.get("mode") or "UNKNOWN").upper(),
                )
                agg[key] += votes
                n += 1
        print(f"    kept {n:,} NC/GA rows")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "office", "state", "county_fips",
                    "county_name", "party", "mode", "votes"])
        for k in sorted(agg):
            w.writerow([*k, agg[k]])
    print(f"\n  wrote {len(agg):,} rows -> {OUT.relative_to(OUT.parents[2])}")


if __name__ == "__main__":
    main()
