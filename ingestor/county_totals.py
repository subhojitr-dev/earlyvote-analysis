"""
county_totals.py — generic early-vote ingestor for states that publish a simple
county-level early-vote count table (GA, AZ, NV, PA). Unlike NC's per-ballot
file, these Secretary-of-State / county-recorder feeds report one row per county
with a running early/advanced/mail ballot count.

Tolerant to column naming: it auto-detects the county column and the count
column. Maps county -> FIPS via the baseline and writes data/live/{state}_current.csv.

Run:
  python ingestor/county_totals.py --state GA --file path/to/ga_advanced_voting.csv
  python ingestor/county_totals.py --state AZ --file ingestor/samples/az_county_sample.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import county_name_to_fips, get_logger, write_live   # noqa: E402

COUNTY_COLS = ("county", "county_name", "county_desc", "jurisdiction", "name")
COUNT_COLS = ("ballots", "early_votes", "advanced_voting", "advance_votes",
              "count", "total", "turnout", "votes", "early", "mail_ballots")


def _pick(fieldnames, cands):
    low = {f.lower().strip(): f for f in fieldnames}
    for c in cands:
        if c in low:
            return low[c]
    return None


def parse(state: str, path: Path):
    log = get_logger(state.lower())
    name2fips = county_name_to_fips(state)
    ballots = defaultdict(int)
    unmapped = set()
    with path.open(encoding="utf-8", newline="") as fh:
        r = csv.DictReader(fh)
        c_cty = _pick(r.fieldnames, COUNTY_COLS)
        c_cnt = _pick(r.fieldnames, COUNT_COLS)
        if not c_cty or not c_cnt:
            log.error("%s: could not detect county/count columns in %s", state, r.fieldnames)
            return None
        for row in r:
            cty = (row.get(c_cty) or "").upper().strip().replace(" COUNTY", "")
            fips = name2fips.get(cty)
            if not fips:
                if cty:
                    unmapped.add(cty)
                continue
            try:
                ballots[fips] += int(float((row.get(c_cnt) or "0").replace(",", "")))
            except ValueError:
                continue
    if unmapped:
        log.warning("%s unmapped counties: %s", state, sorted(unmapped))
    log.info("%s parsed %d counties, %d ballots", state, len(ballots), sum(ballots.values()))
    return dict(ballots)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True, choices=["GA", "AZ", "NV", "PA", "NC"])
    ap.add_argument("--file", required=True)
    a = ap.parse_args()
    res = parse(a.state, Path(a.file))
    if res is None:
        sys.exit(1)
    dst = write_live(a.state, res)
    get_logger(a.state.lower()).info("wrote %s", dst)


if __name__ == "__main__":
    main()
