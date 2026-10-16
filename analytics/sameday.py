"""
sameday.py — 2026 early vote vs the SAME POINT of early voting in 2022 (the last
midterm), by county. By the user's choice GA and TX are compared with 2022 only.

Alignment: by day of in-person early voting. If 2026 data runs through day k of
early voting (k may be negative = mail-only days before it opens), 2022 is cut at
its own opening + k. Mail ballots returned by that cutoff are included.
    GA: opened Mon Oct 17 2022 / Tue Oct 13 2026  (22 vs 21 days before Election Day)
    TX: opened Mon Oct 24 2022 / Mon Oct 19 2026  (15 days before Election Day both)

Sources (all real):
    2026  data/live/{st}_meta.json + {st}_current.csv
          GA: SoS absentee file (ga_county.py) or georgiavotes.com (ga_georgiavotes.py)
          TX: SoS early-voting turnout API (tx_fetch.py)
    2022  data/{st}_county/early_2022.csv   per county per day
          GA: SoS absentee file   TX: SoS daily rosters (data/incoming/tx/tx_ev_2022.json)

Run:  python analytics/sameday.py GA
      python analytics/sameday.py TX
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"
CFG = {
    "GA": {"ev_start": {2022: date(2022, 10, 17), 2026: date(2026, 10, 13)},
           "election_day": {2022: date(2022, 11, 8), 2026: date(2026, 11, 3)},
           "source22": "GA SoS absentee file"},
    "TX": {"ev_start": {2022: date(2022, 10, 24), 2026: date(2026, 10, 19)},
           "election_day": {2022: date(2022, 11, 8), 2026: date(2026, 11, 3)},
           "source22": "TX SoS daily early-voting rosters",
           # in-person only: the 2026 site's per-county mail counts lag far behind 2022's
           # (Oct 15: 85 of 254 counties reporting any), so mail would fake a partisan signal
           "modes": {"inperson"}},
}
YEARS = (2022,)


def as_of(state: str):
    """(as_of date, meta dict) of the live 2026 data, or (None, None)."""
    p = BASE / "live" / f"{state.lower()}_meta.json"
    if not p.exists():
        return None, None
    meta = json.loads(p.read_text())
    return date.fromisoformat(meta["as_of"]), meta


def cutoff(state: str, year: int, asof: date) -> date:
    c = CFG[state]
    return min(c["ev_start"][year] + (asof - c["ev_start"][2026]), c["election_day"][year])


def _from_daily(path: Path, cut: date, modes=None):
    out = Counter()
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if date.fromisoformat(r["date"]) <= cut and (modes is None or r["mode"] in modes):
            out[r["county"]] += int(r["ballots"])
    return out


def sameday(state: str = "GA"):
    """-> {'as_of', 'day', 'source', 'years': {year: {'cutoff', 'used', 'source',
    'counts': {COUNTY: ballots}}}} or None when there is no live 2026 data."""
    if state not in CFG:
        return None
    asof, meta = as_of(state)
    if asof is None:
        return None
    c = CFG[state]
    out = {"as_of": asof.isoformat(), "day": (asof - c["ev_start"][2026]).days + 1,
           "source": meta.get("source"), "basis": meta.get("basis", "in-person + mail"),
           "mail": meta.get("mail"), "mail_counties": meta.get("mail_counties"),
           "counties": meta.get("counties"), "years": {}}
    for y in YEARS:
        cut = cutoff(state, y, asof)
        counts = _from_daily(BASE / f"{state.lower()}_county" / f"early_{y}.csv", cut, c.get("modes"))
        out["years"][y] = {"cutoff": cut.isoformat(), "used": cut.isoformat(), "source": c["source22"],
                           "counts": {k.replace(" ", ""): v for k, v in counts.items()}}
    return out


if __name__ == "__main__":
    st = (sys.argv[1] if len(sys.argv) > 1 else "GA").upper()
    s = sameday(st)
    if not s:
        raise SystemExit(f"no live 2026 {st} data")
    cur = Counter()
    for r in csv.DictReader((BASE / "live" / f"{st.lower()}_current.csv").open(encoding="utf-8")):
        cur[r["county_fips"]] += int(r["ballots"])
    tot = sum(cur.values())
    print(f"{st} 2026 through {s['as_of']} (early-voting day {s['day']}): {tot:,}  [{s['source']}]")
    for y, rec in s["years"].items():
        n = sum(rec["counts"].values())
        print(f"{y} through {rec['used']} (same day): {n:,}   2026 = {tot / n:.0%} of {y}  [{rec['source']}]")
