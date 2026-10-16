"""
ga_sameday.py — Georgia early vote at the SAME POINT of early voting in 2020 and
2022 as 2026 is right now (real data, not end-of-cycle totals).

Alignment: by day of in-person early voting, which opened
    2020: Mon Oct 12   2022: Mon Oct 17   2026: Tue Oct 13
If 2026 data runs through day k (k = as_of - Oct 13), each prior year is cut at
its own opening + k. Mail ballots returned by that cutoff are included in all
years (2020's huge pandemic mail vote is why 2020 counts run high — compare
county SHARES, which the dashboard does, not raw volume).

Sources (all real):
    2026  data/live/ga_meta.json + ga_current.csv  (SoS file / georgiavotes.com)
    2022  data/ga_county/early_2022.csv            (SoS absentee file, per day)
    2020  data/ga_county/early_2020.csv if present (SoS file), else
          data/ga_county/snapshots_2020.csv        (Elections Project daily pages)

Run:  python analytics/ga_sameday.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"
GC = BASE / "ga_county"
EV_START = {2020: date(2020, 10, 12), 2022: date(2022, 10, 17), 2026: date(2026, 10, 13)}
ELECTION_DAY = {2020: date(2020, 11, 3), 2022: date(2022, 11, 8), 2026: date(2026, 11, 3)}
YEARS = (2020, 2022)


def as_of():
    """(as_of date, meta dict) of the live 2026 data, or (None, None)."""
    p = BASE / "live" / "ga_meta.json"
    if not p.exists():
        return None, None
    meta = json.loads(p.read_text())
    return date.fromisoformat(meta["as_of"]), meta


def cutoff(year: int, asof: date) -> date:
    return min(EV_START[year] + (asof - EV_START[2026]), ELECTION_DAY[year])


def _from_daily(path: Path, cut: date):
    out = Counter()
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if date.fromisoformat(r["date"]) <= cut:
            out[r["county"]] += int(r["ballots"])
    return out


def _from_snapshots(path: Path, cut: date):
    snaps = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        snaps.setdefault(date.fromisoformat(r["through_date"]), {})[r["county"]] = int(r["ballots"])
    usable = [d for d in snaps if d <= cut]
    if not usable:
        return None, None
    d = max(usable)
    return Counter(snaps[d]), d


def sameday():
    """-> {'as_of', 'day', 'source', 'years': {year: {'cutoff', 'used', 'source',
    'counts': {COUNTY: ballots}}}} or None when there is no live 2026 data."""
    asof, meta = as_of()
    if asof is None:
        return None
    out = {"as_of": asof.isoformat(), "day": (asof - EV_START[2026]).days + 1,
           "source": meta.get("source"), "years": {}}
    for y in YEARS:
        cut = cutoff(y, asof)
        daily = GC / f"early_{y}.csv"
        if daily.exists():
            counts, used, src = _from_daily(daily, cut), cut, "GA SoS absentee file"
        else:
            counts, used = _from_snapshots(GC / f"snapshots_{y}.csv", cut)
            src = "U.S. Elections Project daily snapshot (from SoS file)"
            if counts is None:
                continue
        out["years"][y] = {"cutoff": cut.isoformat(), "used": used.isoformat(), "source": src,
                           "counts": {k.replace(" ", ""): v for k, v in counts.items()}}
    return out


if __name__ == "__main__":
    s = sameday()
    if not s:
        raise SystemExit("no live 2026 GA data — run ingestor/ga_georgiavotes.py or ga_county.py 2026")
    cur = Counter()
    for r in csv.DictReader((BASE / "live" / "ga_current.csv").open(encoding="utf-8")):
        cur[r["county_fips"]] += int(r["ballots"])
    tot = sum(cur.values())
    print(f"2026 through {s['as_of']} (early-voting day {s['day']}): {tot:,}  [{s['source']}]")
    for y, rec in s["years"].items():
        n = sum(rec["counts"].values())
        print(f"{y} through {rec['used']} (same day): {n:,}   2026 = {tot / n:.0%} of {y}  [{rec['source']}]")
