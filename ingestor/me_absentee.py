"""
me_absentee.py — Maine early (absentee) vote by county, district and party, from the
Secretary of State's statewide absentee voter file.

Maine has no separate "early voting": voting early = absentee, either in person at the
town clerk's office (Rec Type VP) or returned by mail / drop box / delivered. The SoS
posts one statewide file per election, one row per absentee voter, refreshed during the
voting period (https://www.maine.gov/sos/elections-voting/voter-data):
    town, party (D/R/G/L/U), ward/precinct, congressional (CG), State Senate (SS) and
    State House (SR) district, received type + date, status (accepted = ACT / ACC).
District lines are unchanged since 2022 (town/ward → district agrees for 608 of 611
pairs), so 2022 compares directly. The site returns 403 to bare scripts, so requests
send a normal browser User-Agent; the files are public, no login or CAPTCHA.

Inputs (data/incoming/me/, gitignored — voter IDs):
    ME_2022_general.txt   Nov 8 2022 final file (one-time)
    ME_2026_general.txt   Nov 3 2026, re-downloaded on every run
Town → county: MIT Election Lab 2022 Maine precinct file (data/raw/medsl/me22.zip),
plus a few unorganized townships that aren't listed there.

Outputs (counts only):
    data/me_county/early_{year}.csv      county, mode, date, ballots
    data/me_districts/early_{year}.csv   county, chamber, district, mode, days_out, ballots
    data/me_districts/demo_{year}.csv    chamber, district, dim(party), group, days_out, ballots
    data/me_districts/redraw.csv         every district "same lines since 2022"
    data/live/me_current.csv + me_meta.json   2026 cumulative ballots per county

Run:  python ingestor/me_absentee.py          (re-downloads 2026, processes 2022 + 2026)
      python ingestor/me_absentee.py 2026     (2026 only)
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCOMING = ROOT / "data" / "incoming" / "me"
OUT_C = ROOT / "data" / "me_county"
OUT_D = ROOT / "data" / "me_districts"
LIVE = ROOT / "data" / "live"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36", "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
PAGE = "https://www.maine.gov/sos/elections-voting/voter-data"
URL_2022 = "https://www.maine.gov/sos/sites/maine.gov.sos/files/inline-files/Absentee%20Voter%20File11822_0.txt"
ELECTION_DAY = {2022: date(2022, 11, 8), 2026: date(2026, 11, 3)}
COLS = {2022: dict(town="MUNICIPALITY", rt="RECTYPE", rd="RECDATE", st="ACC OR REJ", ok="ACC"),
        2026: dict(town="RES MUNICIPALITY", rt="Rec Type", rd="Rec Date", st="Status", ok="ACT")}
CHAMBERS = {"house": "SR", "senate": "SS", "congress": "CG"}
PARTY = {"D": "Democrat", "R": "Republican", "U": "Unenrolled", "G": "Green", "L": "Libertarian"}
# unorganized townships not named in the MIT file
EXTRA_TOWNS = {"SINCLAIR": "AROOSTOOK", "CROSS LAKE TWP (T17 R5)": "AROOSTOOK", "BENEDICTA TWP": "AROOSTOOK",
               "SILVER RIDGE TWP": "AROOSTOOK", "T3 INDIAN PURCHASE TWP": "PENOBSCOT",
               "T4 INDIAN PURCHASE TWP": "PENOBSCOT", "TRESCOTT TWP": "WASHINGTON", "LONG A TWP": "PENOBSCOT",
               "FRENCHTOWN TWP (KOKADJO)": "PISCATAQUIS", "HARFORDS POINT TWP": "PISCATAQUIS",
               "MOOSEHEAD JUNCTION TWP": "PISCATAQUIS", "BLANCHARD TWP": "PISCATAQUIS",
               "TOMHEGAN TWP": "SOMERSET"}


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        return r.read()


def download(year: int):
    p = INCOMING / f"ME_{year}_general.txt"
    INCOMING.mkdir(parents=True, exist_ok=True)
    if year == 2022:
        if not p.exists():
            p.write_bytes(get(URL_2022))
        return
    html = get(PAGE).decode("utf-8", "replace")
    m = re.search(r'href="([^"]*11-3-26[^"]*\.txt)"', html)
    if not m:
        raise SystemExit("could not find the Nov 3 2026 absentee file link on the SoS voter-data page")
    url = m.group(1) if m.group(1).startswith("http") else "https://www.maine.gov" + m.group(1)
    p.write_bytes(get(url))
    a = re.search(r"as%20of%20(\d{1,2})-(\d{1,2})-(\d{2})", url)     # "...as of 10-16-26.txt"
    if a:
        (INCOMING / "ME_2026_asof.txt").write_text(f"20{a.group(3)}-{int(a.group(1)):02d}-{int(a.group(2)):02d}")
    print(f"downloaded {url.rsplit('/', 1)[-1]}")


def town_county():
    out = dict(EXTRA_TOWNS)
    with zipfile.ZipFile(ROOT / "data" / "raw" / "medsl" / "me22.zip") as z, z.open("me_final.csv") as fh:
        for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8")):
            for nm in (r["jurisdiction_name"], r["precinct"]):
                for part in nm.upper().split("/"):
                    out.setdefault(part.strip(), r["county_name"].strip().upper())
    return out


def aggregate(year: int, t2c: dict):
    c = COLS[year]
    g = lambda r, k: (r.get(k) or "").strip()
    eday = ELECTION_DAY[year]
    by_day, early, demo, unplaced = Counter(), Counter(), Counter(), Counter()
    with (INCOMING / f"ME_{year}_general.txt").open(encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            if g(r, c["st"]) != c["ok"]:
                continue
            try:
                d = datetime.strptime(g(r, c["rd"])[:10], "%m/%d/%Y").date()
            except ValueError:
                continue
            if d > eday or d.year != year:
                continue
            town = g(r, c["town"]).upper()
            county = t2c.get(town)
            if not county:
                unplaced[town] += 1
                continue
            mode = "inperson" if g(r, c["rt"]) == "VP" else "mail"
            days_out = (eday - d).days
            by_day[(county, mode, d.isoformat())] += 1
            party = PARTY.get(g(r, "P"), "Other")
            for ch, col in CHAMBERS.items():
                dist = g(r, col)
                if not dist.isdigit():
                    continue
                dist = str(int(dist))
                early[(county, ch, dist, mode, days_out)] += 1
                demo[(ch, dist, "party", party, days_out)] += 1
    if unplaced:
        print(f"{year}: {sum(unplaced.values())} ballots with no county ({len(unplaced)} towns): "
              f"{unplaced.most_common(5)}")
    return by_day, early, demo


def _write(p: Path, header, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def write_live(by_day: Counter):
    per_day = Counter()
    for (_c, _m, d), v in by_day.items():
        per_day[d] += v
    floor = 0.001 * sum(per_day.values())
    # The file is posted during the day, so the day in its name ("as of 10-16-26") is only
    # partly counted: use the days BEFORE it (and never today).
    asof_p = INCOMING / "ME_2026_asof.txt"
    limit = min(date.today().isoformat(), asof_p.read_text().strip() if asof_p.exists() else "9999")
    as_of = max((d for d, v in per_day.items() if v >= floor and d < limit), default="-")
    fips = {r["county_name"].upper(): r["county_fips"]
            for r in csv.DictReader((ROOT / "data" / "baseline" / "county_lean.csv").open(encoding="utf-8"))
            if r["state"] == "ME"}
    per = Counter()
    for (c, _m, d), v in by_day.items():
        if d <= as_of:
            per[c] += v
    _write(LIVE / "me_current.csv", ["state", "county_fips", "ballots"],
           sorted(("ME", fips[c], v) for c, v in per.items() if c in fips))
    ip = sum(v for (_c, m, d), v in by_day.items() if m == "inperson" and d <= as_of)
    ml = sum(v for (_c, m, d), v in by_day.items() if m == "mail" and d <= as_of)
    (LIVE / "me_meta.json").write_text(json.dumps({"as_of": as_of, "ballots": ip + ml, "inperson": ip, "mail": ml,
                                                   "source": "Maine Secretary of State absentee voter file"}, indent=1))
    miss = [c for c in per if c not in fips]
    print(f"  live: {ip + ml:,} ballots ({ip:,} in person, {ml:,} mail/returned) through {as_of} in {len(per)} counties"
          + (f"; no FIPS for {miss}" if miss else ""))


def main(years):
    t2c = town_county()
    for y in years:
        download(y)
        by_day, early, demo = aggregate(y, t2c)
        print(f"{y}: {sum(by_day.values()):,} accepted absentee ballots")
        _write(OUT_C / f"early_{y}.csv", ["county", "mode", "date", "ballots"], sorted((*k, v) for k, v in by_day.items()))
        _write(OUT_D / f"early_{y}.csv", ["county", "chamber", "district", "mode", "days_out", "ballots"],
               sorted((*k, v) for k, v in early.items()))
        _write(OUT_D / f"demo_{y}.csv", ["chamber", "district", "dim", "group", "days_out", "ballots"],
               sorted((*k, v) for k, v in demo.items()))
        if y == 2026:
            write_live(by_day)
            dists = sorted({(ch, d) for (_c, ch, d, _m, _o) in early}, key=lambda k: (k[0], int(k[1])))
            _write(OUT_D / "redraw.csv", ["chamber", "district", "matched", "same_pct"],
                   [(ch, d, 0, 1.0) for ch, d in dists])


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or sorted(ELECTION_DAY))
