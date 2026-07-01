"""
nc_absentee.py — NC early-vote ingestor (the best public feed in the country).

SOURCE: NC State Board of Elections absentee/one-stop data.
  Portal : https://www.ncsbe.gov/results-data/absentee-data
  Files  : https://dl.ncsbe.gov/?prefix=ENRS/   (absentee_YYYYMMDD.zip -> CSV;
           one row per absentee/one-stop ballot, statewide)
Key columns (tolerant to naming variants across cycles):
  county_desc | ballot_req_type ("ONE STOP" = in-person early, "MAIL")
             | ballot_rtn_status ("ACCEPTED" = counted) | voter_party_code
We count ACCEPTED early + mail ballots, by county and by registered party, and
write the canonical feed data/live/nc_current.csv (+ _party.csv).

Because it records each voter's REGISTERED PARTY, NC gives a sharper signal than
the county-lean method alone (a future analytics enhancement can use *_party.csv).

Run (once real files exist, ~Oct 2026):
  python ingestor/nc_absentee.py --file path/to/absentee_YYYYMMDD.csv
  python ingestor/nc_absentee.py --file ingestor/samples/nc_absentee_sample.csv  # demo
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import county_name_to_fips, get_logger, write_live   # noqa: E402

log = get_logger("nc")

ACCEPTED = {"ACCEPTED"}
EARLY_REQ = {"ONE STOP", "ONE-STOP", "MAIL", "ABSENTEE ONESTOP", "IN PERSON"}
PARTY_MAP = {"DEM": "DEM", "REP": "REP"}


def _col(fieldnames, *cands):
    low = {f.lower(): f for f in fieldnames}
    for c in cands:
        if c in low:
            return low[c]
    return None


def parse(path: Path):
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    name2fips = county_name_to_fips("NC")
    ballots: dict[str, int] = defaultdict(int)
    party: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    total, kept, unmapped = 0, 0, set()

    with path.open(encoding="utf-8", newline="") as fh:
        r = csv.DictReader(fh)
        c_county = _col(r.fieldnames, "county_desc", "county", "county_name")
        c_type = _col(r.fieldnames, "ballot_req_type", "ballot_request_type", "ballot_rtn_type")
        c_status = _col(r.fieldnames, "ballot_rtn_status", "ballot_return_status", "status")
        c_party = _col(r.fieldnames, "voter_party_code", "party", "voter_party")
        if not c_county or not c_status:
            log.error("NC file missing required columns; found %s", r.fieldnames)
            return None
        for row in r:
            total += 1
            if (row.get(c_status) or "").upper().strip() not in ACCEPTED:
                continue
            if c_type and (row.get(c_type) or "").upper().strip() not in EARLY_REQ:
                continue
            cty = (row.get(c_county) or "").upper().strip()
            fips = name2fips.get(cty.replace(" COUNTY", ""))
            if not fips:
                unmapped.add(cty); continue
            ballots[fips] += 1
            p = PARTY_MAP.get((row.get(c_party) or "").upper().strip()[:3], "OTH") if c_party else "OTH"
            party[fips][p] += 1
            kept += 1

    if unmapped:
        log.warning("NC unmapped counties: %s", sorted(unmapped))
    log.info("NC parsed %d rows -> %d accepted early ballots across %d counties",
             total, kept, len(ballots))
    return dict(ballots), {k: dict(v) for k, v in party.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="path to NC absentee CSV")
    a = ap.parse_args()
    res = parse(Path(a.file))
    if not res:
        sys.exit(1)
    ballots, party = res
    dst = write_live("NC", ballots, party)
    log.info("wrote %s (%d ballots total)", dst, sum(ballots.values()))


if __name__ == "__main__":
    main()
