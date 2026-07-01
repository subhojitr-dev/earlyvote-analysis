"""
run.py — ingestor orchestrator. For each state, looks for a dropped-in raw feed
file at data/incoming/{state}.csv, runs the correct parser, and writes the
canonical live feed at data/live/{state}_current.csv. Anything with no incoming
file is skipped (the synthetic fixture keeps serving until real voting opens).

Typical live-season loop (cron/Task Scheduler): a fetch step downloads each
state's file into data/incoming/, then `python ingestor/run.py` refreshes the
feeds, then `python web/build_dashboard.py` rebuilds and a git push redeploys.

Run:  python ingestor/run.py            # process whatever is in data/incoming/
      python ingestor/run.py --demo     # process the bundled sample files
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import county_totals                                  # noqa: E402
import nc_absentee                                    # noqa: E402
from common import get_logger, write_live, BASE       # noqa: E402

log = get_logger("run")
INCOMING = BASE / "incoming"
SAMPLES = Path(__file__).resolve().parent / "samples"

# state -> (parser, sample-file). NC uses the per-ballot parser; others generic.
STATES = {
    "NC": ("nc", SAMPLES / "nc_absentee_sample.csv"),
    "GA": ("totals", None),
    "AZ": ("totals", SAMPLES / "az_county_sample.csv"),
    "NV": ("totals", None),
    "PA": ("totals", None),
}


def process(state, kind, path):
    if kind == "nc":
        res = nc_absentee.parse(path)
        if not res:
            return None
        ballots, party = res
        return write_live("NC", ballots, party)
    res = county_totals.parse(state, path)
    if res is None:
        return None
    return write_live(state, res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="use bundled sample files")
    a = ap.parse_args()
    done, skipped = [], []
    for state, (kind, sample) in STATES.items():
        incoming = INCOMING / f"{state}.csv"
        src = incoming if incoming.exists() else (sample if a.demo else None)
        if not src or not src.exists():
            skipped.append(state); continue
        dst = process(state, kind, src)
        (done if dst else skipped).append(state)
    log.info("ingest complete — updated: %s | skipped (fixture stays): %s",
             done or "none", skipped or "none")


if __name__ == "__main__":
    main()
