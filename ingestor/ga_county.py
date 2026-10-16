"""
ga_county.py — Georgia early vote by COUNTY and DAY, from the real SoS absentee files.

Feeds the main dashboard (web/index.html). Same input files as ga_districts.py
(data/incoming/ga/GA_{year}_general.zip, gitignored, one row per voter); writes
ONLY aggregate counts — no names, addresses or registration numbers leave here.

Outputs:
    data/ga_county/early_{year}.csv   county, mode, date, ballots
                                      accepted ballots per county per day;
                                      mode = inperson | mail (mail includes
                                      electronic/UOCAVA ballots)
    data/live/ga_current.csv          state, county_fips, ballots
                                      2026 cumulative accepted early + mail
                                      ballots — the analytics prefer this over
                                      the synthetic fixture automatically
    data/live/ga_meta.json            as-of date of the 2026 file

Years: 2022 (last midterm) is the comparison year; 2026 is the live year.

Run:  python ingestor/ga_county.py          (every year whose zip is present)
      python ingestor/ga_county.py 2026     (daily refresh)
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ga_districts import INCOMING, _rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ga_county"
LIVE = ROOT / "data" / "live"
YEARS = (2022, 2026)
ELECTION_DAY = {2022: date(2022, 11, 8), 2026: date(2026, 11, 3)}


def _mode(style: str) -> str | None:
    """Ballot Style -> inperson / mail ('EARLY IN-PERSON' / 'ABSENTEE BY MAIL',
    'ELECTRONIC BALLOT DELIVERY')."""
    s = (style or "").strip().upper()
    if "PERSON" in s:
        return "inperson"
    if "MAIL" in s or "ELECTRONIC" in s:
        return "mail"
    return None


def aggregate(year: int):
    counts = Counter()           # (county, mode, iso date) -> n
    other = Counter()
    for r in _rows(year):
        if (r.get("Ballot Status") or "").strip() != "A":   # accepted only
            continue
        try:
            d = datetime.strptime(r["Ballot Return Date"].strip(), "%m/%d/%Y").date()
        except (KeyError, ValueError):
            continue
        if d.year != year or d > ELECTION_DAY[year]:   # 01/01/1900 placeholders, typos,
            continue                                    # post-election (runoff-era) stamps
        mode = _mode(r.get("Ballot Style"))
        if mode is None:
            other[r.get("Ballot Style")] += 1
            continue
        counts[(r["County"].strip().upper(), mode, d.isoformat())] += 1
    if other:
        print(f"{year}: skipped unrecognised ballot styles: {dict(other)}")
    return counts


def _file_date(year: int):
    """Date the SoS built the zip (its members' timestamps), or None."""
    zp = INCOMING / f"GA_{year}_general.zip"
    if not zp.exists():
        return None
    import zipfile
    with zipfile.ZipFile(zp) as z:
        return max(date(*i.date_time[:3]) for i in z.infolist())


def _fips_by_name():
    return {r["county_name"].upper().replace(" ", ""): r["county_fips"]
            for r in csv.DictReader((ROOT / "data" / "baseline" / "county_lean.csv").open(encoding="utf-8"))
            if r["state"] == "GA"}


def main(years):
    OUT.mkdir(parents=True, exist_ok=True)
    for y in years:
        counts = aggregate(y)
        n = sum(counts.values())
        by_mode = Counter()
        for (_c, m, _d), v in counts.items():
            by_mode[m] += v
        last = max((d for (_c, _m, d) in counts), default="-")
        stamp = _file_date(y)
        if stamp:   # votes run through the day BEFORE the file was built; later dates are typos
            last = max((d for (_c, _m, d) in counts if d < stamp.isoformat()), default=last)
        print(f"{y}: {n:,} accepted ballots ({by_mode['inperson']:,} in person, "
              f"{by_mode['mail']:,} mail) through {last}")
        with (OUT / f"early_{y}.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["county", "mode", "date", "ballots"])
            w.writerows(sorted((*k, v) for k, v in counts.items()))

        meta_p = LIVE / "ga_meta.json"
        if y == 2026 and meta_p.exists() and json.loads(meta_p.read_text()).get("as_of", "") > last:
            print(f"  live data is newer ({json.loads(meta_p.read_text())['as_of']}); "
                  f"download today's SoS file to replace it")
        elif y == 2026:
            fips = _fips_by_name()
            per = Counter()
            for (c, _m, _d), v in counts.items():
                per[c] += v
            missing = sorted(c for c in per if c.replace(" ", "") not in fips)
            if missing:
                print(f"  (!) no FIPS for: {missing}")
            LIVE.mkdir(parents=True, exist_ok=True)
            with (LIVE / "ga_current.csv").open("w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["state", "county_fips", "ballots"])
                w.writerows(sorted(("GA", fips[c.replace(" ", "")], v) for c, v in per.items()
                                   if c.replace(" ", "") in fips))
            (LIVE / "ga_meta.json").write_text(json.dumps(
                {"as_of": last, "ballots": n, "inperson": by_mode["inperson"], "mail": by_mode["mail"],
                 "source": "GA Secretary of State absentee voter file"}, indent=1))
            print(f"  wrote {LIVE / 'ga_current.csv'} ({len(per)} counties)")


if __name__ == "__main__":
    ys = [int(a) for a in sys.argv[1:]] or [y for y in YEARS if (INCOMING / f"GA_{y}_general.zip").exists()]
    main(ys)
