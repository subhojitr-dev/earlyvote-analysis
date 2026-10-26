"""
pa_fetch.py — Pennsylvania mail ballots returned, by county, day and party (2022 and 2026).

Pennsylvania has no in-person early voting: "early" voting is mail ballots (mail-in and absentee,
including on-demand ballots voted at county offices). The Department of State publishes every
mail ballot application on data.pa.gov, updated daily, with county, party and Ballot Returned Date:
    2026 general  https://data.pa.gov/d/nbwd-pfn4
    2022 general  https://data.pa.gov/d/uhfm-zhus   (final file, Nov 2022)
Only aggregate counts are requested (Socrata SoQL GROUP BY), never voter rows.

Outputs (counts only):
    data/pa_county/early_{2022,2026}.csv  county, mode, date, ballots     (mode = mail; daily returns)
    data/pa_county/party_{2022,2026}.csv  county, party, date, ballots    (party = D / R / O)
    data/live/pa_current.csv + pa_meta.json   2026 cumulative returned by county (latest full day)

Run:  python ingestor/pa_fetch.py          (2022 is fetched once, then reused)
"""
from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "pa_county"
LIVE = ROOT / "data" / "live"
DATASET = {2022: "uhfm-zhus", 2026: "nbwd-pfn4"}
EDAY = {2022: date(2022, 11, 8), 2026: date(2026, 11, 3)}
PARTY = {"DEM": "D", "D": "D", "REP": "R", "R": "R"}


def query(year: int):
    """{(county, party, date): ballots} for ballots with a returned date up to Election Day."""
    soql = {"$select": "countyname, party, ballotreturneddate as d, count(*) as n",
            "$where": f"ballotreturneddate IS NOT NULL AND ballotreturneddate <= '{EDAY[year]}T23:59:59'",
            "$group": "countyname, party, ballotreturneddate", "$limit": "50000", "$offset": "0"}
    out = defaultdict(int)
    while True:
        url = f"https://data.pa.gov/resource/{DATASET[year]}.json?" + urllib.parse.urlencode(soql)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "earlyvote-analysis"}), timeout=180) as r:
            rows = json.loads(r.read())
        if isinstance(rows, dict):
            raise RuntimeError(rows)
        for x in rows:
            if not x.get("d") or not x.get("countyname"):
                continue
            out[(x["countyname"].strip().upper(), PARTY.get((x.get("party") or "").strip().upper(), "O"),
                 x["d"][:10])] += int(x["n"])
        if len(rows) < 50000:
            return out
        soql["$offset"] = str(int(soql["$offset"]) + 50000)


def write(year: int, data):
    OUT.mkdir(parents=True, exist_ok=True)
    by_day = defaultdict(int)
    for (c, _p, d), n in data.items():
        by_day[(c, d)] += n
    with (OUT / f"early_{year}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["county", "mode", "date", "ballots"])
        w.writerows([c, "mail", d, n] for (c, d), n in sorted(by_day.items()))
    with (OUT / f"party_{year}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["county", "party", "date", "ballots"])
        w.writerows([c, p, d, n] for (c, p, d), n in sorted(data.items()))


def write_live(data):
    """Cumulative through the latest COMPLETE day (the file is refreshed during the day)."""
    today = datetime.now(timezone(timedelta(hours=-4))).date()
    days = sorted({d for (_c, _p, d) in data if date.fromisoformat(d) < today})
    through = days[-1]
    fips = {r["county_name"].upper(): r["county_fips"]
            for r in csv.DictReader((ROOT / "data" / "baseline" / "county_lean.csv").open(encoding="utf-8"))
            if r["state"] == "PA"}
    by_c, party = defaultdict(int), defaultdict(int)
    for (c, p, d), n in data.items():
        if d <= through:
            by_c[c] += n
            party[p] += n
    missing = sorted(c for c in by_c if c not in fips)
    if missing:
        print(f"  warning: counties without a FIPS match: {missing}")
    LIVE.mkdir(exist_ok=True)
    with (LIVE / "pa_current.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["state", "county_fips", "ballots"])
        w.writerows(["PA", fips[c], n] for c, n in sorted(by_c.items()) if c in fips)
    tot = sum(by_c.values())
    meta = {"as_of": through, "ballots": tot, "inperson": 0, "mail": tot,
            "party": {"Democrat": party["D"], "Republican": party["R"], "Other": party["O"]},
            "basis": "mail ballots returned",
            "source": "Pennsylvania Department of State mail ballot file (data.pa.gov)"}
    (LIVE / "pa_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def main():
    if not (OUT / "early_2022.csv").exists():
        d22 = query(2022)
        write(2022, d22)
        print(f"2022: {sum(d22.values()):,} mail ballots returned by Election Day")
    d26 = query(2026)
    write(2026, d26)
    meta = write_live(d26)
    p = meta["party"]
    print(f"PA through {meta['as_of']}: {meta['ballots']:,} mail ballots returned "
          f"(D {p['Democrat']:,} / R {p['Republican']:,} / other {p['Other']:,})")


if __name__ == "__main__":
    main()
