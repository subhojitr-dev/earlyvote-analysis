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
    early_2022_cur.csv    same columns as early_{year}.csv: the 2022 early votes
                          RE-COUNTED ON TODAY'S LINES (python ingestor/ga_districts.py
                          recount). Lets every district be compared with 2022, the
                          last midterm, even where lines were redrawn in Dec 2023.
    redraw.csv            chamber, district, matched, same_pct
                          of voters who voted early in BOTH 2022 and 2024, the
                          share whose 2022 district had the same number as their
                          2024 district (proxy for "lines unchanged")

Run:  python ingestor/ga_districts.py            (all years present)
      python ingestor/ga_districts.py 2026       (just refresh 2026)
      python ingestor/ga_districts.py recount    (one-time: 2022 on current lines)
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


def recount_2022(min_share: float = 0.03):
    """2022 early votes placed on the CURRENT (Dec 2023) House / Senate lines.

    Each 2022 ballot is placed by its 2022 precinct, not by the individual voter:
    for every (county, 2022 precinct, 2022 district) we look up where voters from it
    are registered now, using everyone who appears in both the 2022 and 2024 files
    and still lives in the same county (so movers don't drag votes elsewhere). A
    precinct split between new districts is shared out in proportion; shares under
    `min_share` are treated as mover noise. Precincts with no matched voters fall
    back to their (county, 2022 district) pattern, then their county's."""
    now = {}                                           # reg# -> (county, house, senate) on 2024 lines
    for r in _rows(2024):
        reg = (r.get("Voter Registration #") or "").strip()
        if reg:
            now[reg] = (r["County"].replace(" ", "").upper(), _dist(r.get("HOUSE", "")), _dist(r.get("SEN", "")))
    print(f"recount: {len(now):,} voters on current lines (2024 file)")

    eday = ELECTION_DAY[2022]
    xw = {ch: defaultdict(Counter) for ch in CHAMBERS}          # (county, precinct, d22) -> Counter(d_now)
    ballots = Counter()                                         # (county, precinct, h22, s22, mode, days_out) -> n
    seen = set()
    for r in _rows(2022):
        reg = (r.get("Voter Registration #") or "").strip()
        county, prec = r["County"].strip().upper(), (r.get("County Precinct") or "").strip()
        d22 = {ch: _dist(r.get(col, "")) for ch, col in CHAMBERS.items()}
        cur = now.get(reg)
        if cur and cur[0] == county.replace(" ", "") and reg not in seen:
            seen.add(reg)
            for i, ch in enumerate(CHAMBERS):
                if cur[1 + i] is not None:
                    xw[ch][(county, prec, d22[ch])][cur[1 + i]] += 1
        if r.get("Ballot Status") != "A":
            continue
        try:
            d = datetime.strptime(r["Ballot Return Date"], "%m/%d/%Y").date()
        except (KeyError, ValueError):
            continue
        days_out = (eday - d).days
        mode = MODES.get((r.get("Ballot Style") or "").strip().upper())
        if days_out < 0 or mode is None:
            continue
        ballots[(county, prec, d22["house"], d22["senate"], mode, days_out)] += 1
    del now

    def norm(c: Counter):
        tot = sum(c.values())
        keep = {k: v for k, v in c.items() if v / tot >= min_share} or dict(c)
        t = sum(keep.values())
        return {k: v / t for k, v in keep.items()}

    out = Counter()
    how = Counter()
    for i, ch in enumerate(CHAMBERS):
        by_cd, by_c = defaultdict(Counter), defaultdict(Counter)    # fallbacks
        for (county, _p, d22), c in xw[ch].items():
            by_cd[(county, d22)].update(c)
            by_c[county].update(c)
        cache = {}
        for (county, prec, h22, s22, mode, days_out), n in ballots.items():
            d22 = (h22, s22)[i]
            k = (county, prec, d22)
            if k not in cache:
                if xw[ch].get(k):
                    cache[k] = ("precinct", norm(xw[ch][k]))
                elif by_cd.get((county, d22)):
                    cache[k] = ("county+district", norm(by_cd[(county, d22)]))
                elif by_c.get(county):
                    cache[k] = ("county", norm(by_c[county]))
                else:
                    cache[k] = ("unplaced", {})
            kind, dist = cache[k]
            how[(ch, kind)] += n
            for dnow, f in dist.items():
                out[(county, ch, dnow, mode, days_out)] += n * f
    for ch in CHAMBERS:
        tot = sum(v for (c, k), v in how.items() if c == ch)
        print(f"recount {ch}: " + ", ".join(f"{k} {v / tot:.1%}" for (c, k), v in sorted(how.items()) if c == ch))
    _write(OUT / "early_2022_cur.csv", ["county", "chamber", "district", "mode", "days_out", "ballots"],
           sorted((*k, round(v)) for k, v in out.items() if round(v) > 0))
    print(f"wrote early_2022_cur.csv: {sum(out.values()) / len(CHAMBERS):,.0f} ballots per chamber")


if __name__ == "__main__":
    if sys.argv[1:] == ["recount"]:
        recount_2022()
        raise SystemExit
    ys = [int(a) for a in sys.argv[1:]] or [y for y in ELECTION_DAY
                                            if (INCOMING / f"GA_{y}_general.zip").exists()
                                            or list(INCOMING.glob(f"*_{y}_general.csv"))]
    main(ys)
