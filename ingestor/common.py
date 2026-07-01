"""
common.py — shared helpers for the state early-vote ingestors.

Every ingestor's job is the same: read a state's live early-vote file, aggregate
accepted early/mail ballots to the county, and write the canonical feed file
  data/live/{state}_current.csv   with columns:  state, county_fips, ballots
which the analytics layer (turnout_compare.load_current) picks up automatically
in preference to the synthetic fixture.

County names are mapped to FIPS using the baseline (data/baseline/county_lean.csv)
so the live feed joins cleanly to the historical baseline.
"""
from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data"
LIVE = BASE / "live"
LOGS = ROOT / "logs"


def get_logger(name: str) -> logging.Logger:
    LOGS.mkdir(exist_ok=True)
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(name)s: %(message)s")
    fh = logging.FileHandler(LOGS / "ingestor.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    lg.addHandler(fh); lg.addHandler(sh)
    return lg


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.upper().strip()).replace(" COUNTY", "")


def county_name_to_fips(state: str) -> dict[str, str]:
    """{normalized county name -> FIPS} for a state, from the baseline."""
    out = {}
    src = BASE / "baseline" / "county_lean.csv"
    for r in csv.DictReader(src.open(encoding="utf-8")):
        if r["state"] == state:
            out[_norm(r["county_name"])] = r["county_fips"]
    return out


def write_live(state: str, county_ballots: dict[str, int], party=None) -> Path:
    """county_ballots: {FIPS -> ballots}. Writes data/live/{state}_current.csv.
    Optional party: {FIPS -> {'DEM': n, 'REP': n, 'OTH': n}} -> *_party.csv."""
    LIVE.mkdir(parents=True, exist_ok=True)
    dst = LIVE / f"{state.lower()}_current.csv"
    with dst.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["state", "county_fips", "ballots"])
        for fips, n in sorted(county_ballots.items()):
            w.writerow([state, fips, n])
    if party:
        pdst = LIVE / f"{state.lower()}_current_party.csv"
        with pdst.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["state", "county_fips", "dem", "rep", "oth"])
            for fips, d in sorted(party.items()):
                w.writerow([state, fips, d.get("DEM", 0), d.get("REP", 0), d.get("OTH", 0)])
    return dst
