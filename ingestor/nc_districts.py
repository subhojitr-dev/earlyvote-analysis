"""
nc_districts.py — North Carolina State House / State Senate / congressional early-vote
aggregates, WITH the early electorate's demographics.

Reads the NC State Board of Elections absentee files (one row per ballot, free and
public, no login): https://dl.ncsbe.gov/?prefix=ENRS/
    ENRS/2022_11_08/absentee_20221108.zip   Nov 8 2022 general
    ENRS/2024_11_05/absentee_20241105.zip   Nov 5 2024 general
    ENRS/2026_11_03/absentee_20261103.zip   Nov 3 2026 general (updated daily)
Each row carries the voter's race, ethnicity, gender, age, party and districts.
Only aggregate counts leave this script (no names, addresses or IDs).

Outputs (data/nc_districts/, small, committed) — same shape as the Georgia files so
web/build_ga_districts.py can build either state:
    early_{year}.csv  county, chamber, district, mode, days_out, ballots
    demo_{year}.csv   chamber, district, dim, group, days_out, ballots
                      dim = race | age | gender | party ; chamber includes "congress"
                      (for the Demographic Analysis app)
    redraw.csv        chamber, district, matched, same_pct  (2022 -> 2024, by NCID)
Also writes data/raw/medsl/nc24.csv (2024 results, precinct-sorted) for the district lean.

Run:  python ingestor/nc_districts.py            (downloads missing files, all years)
      python ingestor/nc_districts.py 2026       (refresh 2026 only — re-downloads it)
"""
from __future__ import annotations

import csv
import io
import re
import sys
import urllib.request
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCOMING = ROOT / "data" / "incoming" / "nc"
OUT = ROOT / "data" / "nc_districts"

ELECTION_DAY = {2022: date(2022, 11, 8), 2024: date(2024, 11, 5), 2026: date(2026, 11, 3)}
URL = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/{d:%Y_%m_%d}/absentee_{d:%Y%m%d}.zip"
CHAMBERS = {"house": "nc_house_desc", "senate": "nc_senate_desc", "congress": "cong_dist_desc"}
MODES = {"EARLY VOTING": "inperson", "ONE-STOP": "inperson", "MAIL": "mail"}


def _dist(v: str) -> str | None:
    m = re.search(r"(\d+)\s*$", v or "")
    return str(int(m.group(1))) if m else None


def race_group(r) -> str:
    if (r.get("ethnicity") or "").startswith("HISPANIC"):
        return "Hispanic"
    return {"WHITE": "White", "BLACK or AFRICAN AMERICAN": "Black", "ASIAN": "Asian",
            "UNDESIGNATED": "Not stated"}.get(r.get("race") or "", "Other / multiracial")


def age_group(a: str) -> str:
    try:
        a = int(a)
    except (TypeError, ValueError):
        return "Not stated"
    return "18–29" if a < 30 else "30–44" if a < 45 else "45–64" if a < 65 else "65+"


def party_group(p: str) -> str:
    return {"DEM": "Democrat", "REP": "Republican", "UNA": "Unaffiliated"}.get((p or "").strip(), "Other party")


def gender_group(g: str) -> str:
    return {"F": "Women", "M": "Men"}.get((g or "").strip(), "Not stated")


def path(year: int) -> Path:
    return INCOMING / f"NC_{year}_general.zip"


def download(year: int, force: bool = False):
    p = path(year)
    if p.exists() and not force:
        return
    INCOMING.mkdir(parents=True, exist_ok=True)
    url = URL.format(d=ELECTION_DAY[year])
    print(f"downloading {url}")
    tmp = p.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(p)


def aggregate(year: int):
    eday = ELECTION_DAY[year]
    early, demo, ids, seen = Counter(), Counter(), {}, set()
    with zipfile.ZipFile(path(year)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(name) as fh:
            for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace")):
                if not (r.get("ballot_rtn_status") or "").strip().startswith("ACCEPTED"):
                    continue
                mode = MODES.get((r.get("ballot_req_type") or "").strip())
                if mode is None:
                    continue
                vid = r.get("ncid") or (r.get("county_desc"), r.get("voter_reg_num"))
                if vid in seen:                 # one counted ballot per voter
                    continue
                try:
                    d = datetime.strptime(r["ballot_rtn_dt"].strip(), "%m/%d/%Y").date()
                except (KeyError, ValueError):
                    continue
                days_out = (eday - d).days
                if days_out < 0 or d > date.today():   # future-dated returns are data-entry errors
                    continue
                seen.add(vid)
                county = (r.get("county_desc") or "").strip().upper()
                groups = {"race": race_group(r), "age": age_group(r.get("age")),
                          "gender": gender_group(r.get("gender")), "party": party_group(r.get("voter_party_code"))}
                dists = {}
                for ch, col in CHAMBERS.items():
                    dist = _dist(r.get(col, ""))
                    dists[ch] = dist
                    if dist is None:
                        continue
                    if ch != "congress":
                        early[(county, ch, dist, mode, days_out)] += 1
                    for dim, g in groups.items():
                        demo[(ch, dist, dim, g, days_out)] += 1
                ids[vid] = (dists["house"], dists["senate"])
    return len(seen), early, demo, ids


RESULTS24_URL = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2024_11_05/results_precinct_sort/STATEWIDE_PRECINCT_SORT.txt"
RESULTS24_RAW = ROOT / "data" / "raw" / "ncsbe" / "STATEWIDE_PRECINCT_SORT_2024.txt"
RESULTS24 = ROOT / "data" / "raw" / "medsl" / "nc24.csv"


def build_results24():
    """2024 NC results for the district lean, from the State Board's PRECINCT-SORTED
    file: early, mail and provisional votes are assigned to the voter's home precinct.
    (MIT Election Lab's file reports many counties' early votes by voting SITE, which
    mixes districts and skews district leans by up to ~14 pts.) Written in the
    MIT-Election-Lab column layout that web/build_ga_districts.py reads."""
    if not RESULTS24_RAW.exists():
        RESULTS24_RAW.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {RESULTS24_URL}")
        urllib.request.urlretrieve(RESULTS24_URL, RESULTS24_RAW)
    office = [(re.compile(r"^US PRESIDENT$"), "US PRESIDENT"),
              (re.compile(r"^NC HOUSE OF REPRESENTATIVES DISTRICT (\d+)$"), "STATE HOUSE"),
              (re.compile(r"^NC STATE SENATE DISTRICT (\d+)$"), "STATE SENATE")]
    party = {"DEM": "DEMOCRAT", "REP": "REPUBLICAN"}
    tot = Counter()
    with RESULTS24_RAW.open(encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh, delimiter="	"):
            title = r["contest_title"].strip()
            for rx, off in office:
                m = rx.match(title)
                if m:
                    dist = m.group(1) if m.groups() else "STATEWIDE"
                    tot[(r["county"].strip(), r["precinct_code"].strip(), off, dist,
                         party.get(r["candidate_party_lbl"].strip(), "OTHER"), r["candidate_name"].strip())] += int(r["vote_ct"] or 0)
                    break
    _write(RESULTS24, ["county_name", "precinct", "office", "district", "party_simplified", "candidate", "votes"],
           sorted((*k, v) for k, v in tot.items()))
    print(f"wrote {RESULTS24.relative_to(ROOT)} ({len(tot):,} rows)")


def _write(p: Path, header, rows):
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main(years: list[int], refresh: bool):
    OUT.mkdir(parents=True, exist_ok=True)
    if not RESULTS24.exists() or RESULTS24.stat().st_mtime < (RESULTS24_RAW.stat().st_mtime if RESULTS24_RAW.exists() else 0):
        build_results24()
    ids_by_year = {}
    for y in years:
        download(y, force=refresh and y == 2026)
        n, early, demo, ids = aggregate(y)
        print(f"{y}: {n:,} accepted early/mail ballots")
        _write(OUT / f"early_{y}.csv", ["county", "chamber", "district", "mode", "days_out", "ballots"],
               sorted((*k, v) for k, v in early.items()))
        _write(OUT / f"demo_{y}.csv", ["chamber", "district", "dim", "group", "days_out", "ballots"],
               sorted((*k, v) for k, v in demo.items()))
        if y in (2022, 2024):
            ids_by_year[y] = ids
    if {2022, 2024} <= set(ids_by_year):
        old, new = ids_by_year[2022], ids_by_year[2024]
        tot, same = Counter(), Counter()
        for vid, cur in new.items():
            prev = old.get(vid)
            if not prev:
                continue
            for i, ch in enumerate(("house", "senate")):
                if cur[i] is None or prev[i] is None:
                    continue
                tot[(ch, cur[i])] += 1
                same[(ch, cur[i])] += prev[i] == cur[i]
        _write(OUT / "redraw.csv", ["chamber", "district", "matched", "same_pct"],
               sorted(((ch, d, t, round(same[(ch, d)] / t, 4)) for (ch, d), t in tot.items()),
                      key=lambda r: (r[0], int(r[1]))))
        print(f"redraw.csv: {len(tot)} districts")


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]]
    main(args or sorted(ELECTION_DAY), refresh=True)    # 2026 is always re-downloaded (it changes daily)
