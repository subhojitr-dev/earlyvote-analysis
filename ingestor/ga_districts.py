"""
ga_districts.py — Georgia State House / State Senate early-vote aggregates.

Reads the GA Secretary of State absentee voter files (one row per voter, with the
voter's CNG / SEN / HOUSE district) and writes ONLY aggregate counts — no names,
addresses or registration numbers leave this script.

Inputs (data/incoming/ga/, gitignored — downloaded from
https://mvp.sos.ga.gov/s/voter-absentee-files):
    GA_2022_general.zip   Nov 8 2022 general (statewide, one CSV per county)
    GA_2024_general.zip   Nov 5 2024 general
    GA_2026_general.zip   Nov 3 2026 general (refresh daily during early voting)
    (a single-county CSV such as FULTON_2026_general.csv also works)

Outputs (data/ga_districts/, small, committed):
    early_{year}.csv      county, chamber, district, mode, days_out, ballots
                          accepted ballots by the number of days before Election
                          Day they were cast/returned; mode = inperson (EARLY
                          IN-PERSON) or mail (ABSENTEE BY MAIL + ELECTRONIC BALLOT
                          DELIVERY, i.e. mostly military/overseas)
    xwalk_2024.csv        county, precinct, chamber, district, voters
                          precinct -> district weights (2024 early voters), used
                          to put 2024 presidential precinct results into districts
    redraw.csv            chamber, district, matched, same_pct
                          of voters who voted early in BOTH 2022 and 2024, the
                          share whose 2022 district had the same number as their
                          2024 district (proxy for "lines unchanged")

Run:  python ingestor/ga_districts.py            (all years present)
      python ingestor/ga_districts.py 2026       (just refresh 2026)
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCOMING = ROOT / "data" / "incoming" / "ga"
OUT = ROOT / "data" / "ga_districts"

ELECTION_DAY = {2022: date(2022, 11, 8), 2024: date(2024, 11, 5), 2026: date(2026, 11, 3)}
CHAMBERS = {"house": "HOUSE", "senate": "SEN"}
MODES = {"EARLY IN-PERSON": "inperson", "ABSENTEE BY MAIL": "mail", "ELECTRONIC BALLOT DELIVERY": "mail"}


def _dist(v: str) -> str | None:
    """'049' / '49' -> '49'; blanks and placeholder codes -> None."""
    v = (v or "").strip()
    if not v.isdigit() or v.startswith("999"):
        return None
    return str(int(v))


def _rows(year: int):
    """Yield dict rows for a year from its zip and/or single-county CSVs."""
    zp = INCOMING / f"GA_{year}_general.zip"
    if zp.exists():
        with zipfile.ZipFile(zp) as z:
            # The zip holds one CSV per county PLUS a STATEWIDE.csv that repeats
            # every row — read the statewide file alone, or the counties alone.
            names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            statewide = [n for n in names if n.upper() == "STATEWIDE.CSV"]
            for name in statewide or names:
                with z.open(name) as fh:
                    yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace"))
        return
    for p in sorted(INCOMING.glob(f"*_{year}_general.csv")):
        with p.open(encoding="utf-8-sig", errors="replace") as fh:
            yield from csv.DictReader(fh)


def aggregate(year: int, keep_ids: bool = False):
    eday = ELECTION_DAY[year]
    early = Counter()                      # (county, chamber, district, mode, days_out) -> n
    other = Counter()                      # unrecognised ballot styles (reported, not counted)
    xwalk = Counter()                      # (county, precinct, chamber, district) -> n
    ids = {}                               # reg# -> (house, senate)   [in memory only]
    n = 0
    for r in _rows(year):
        if r.get("Ballot Status") != "A":  # accepted ballots only
            continue
        try:
            d = datetime.strptime(r["Ballot Return Date"], "%m/%d/%Y").date()
        except (KeyError, ValueError):
            continue
        days_out = (eday - d).days
        if days_out < 0:
            continue
        mode = MODES.get((r.get("Ballot Style") or "").strip().upper())
        if mode is None:
            other[r.get("Ballot Style")] += 1
            continue
        county = r["County"].strip().upper()
        n += 1
        dists = {}
        for ch, col in CHAMBERS.items():
            dist = _dist(r.get(col, ""))
            dists[ch] = dist
            if dist is None:
                continue
            early[(county, ch, dist, mode, days_out)] += 1
            if year == 2024:
                xwalk[(county, r.get("County Precinct", "").strip(), ch, dist)] += 1
        if keep_ids:
            ids[r["Voter Registration #"]] = (dists["house"], dists["senate"])
    if other:
        print(f"{year}: skipped unrecognised ballot styles: {dict(other)}")
    return n, early, xwalk, ids


def _write(path: Path, header: list[str], rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main(years: list[int]):
    OUT.mkdir(parents=True, exist_ok=True)
    ids_by_year = {}
    need_redraw = {2022, 2024} <= set(years)
    for y in years:
        n, early, xwalk, ids = aggregate(y, keep_ids=need_redraw and y in (2022, 2024))
        print(f"{y}: {n:,} accepted early/mail ballots")
        _write(OUT / f"early_{y}.csv", ["county", "chamber", "district", "mode", "days_out", "ballots"],
               sorted((*k, v) for k, v in early.items()))
        if y == 2024:
            _write(OUT / "xwalk_2024.csv", ["county", "precinct", "chamber", "district", "voters"],
                   sorted((*k, v) for k, v in xwalk.items()))
        if ids:
            ids_by_year[y] = ids

    if need_redraw:
        old, new = ids_by_year[2022], ids_by_year[2024]
        tot, same = Counter(), Counter()
        for reg, (h24, s24) in new.items():
            prev = old.get(reg)
            if not prev:
                continue
            for i, (ch, d24) in enumerate((("house", h24), ("senate", s24))):
                if d24 is None or prev[i] is None:
                    continue
                tot[(ch, d24)] += 1
                same[(ch, d24)] += prev[i] == d24
        _write(OUT / "redraw.csv", ["chamber", "district", "matched", "same_pct"],
               sorted(((ch, d, t, round(same[(ch, d)] / t, 4)) for (ch, d), t in tot.items()),
                      key=lambda r: (r[0], int(r[1]))))
        print(f"redraw.csv: {len(tot)} districts")


if __name__ == "__main__":
    ys = [int(a) for a in sys.argv[1:]] or [y for y in ELECTION_DAY
                                            if (INCOMING / f"GA_{y}_general.zip").exists()
                                            or list(INCOMING.glob(f"*_{y}_general.csv"))]
    main(ys)
