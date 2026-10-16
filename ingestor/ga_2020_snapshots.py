"""
ga_2020_snapshots.py — Georgia 2020 general: cumulative ballots cast by COUNTY at
each day of early voting, recovered from the U.S. Elections Project (Michael
McDonald, UF) daily pages.

Why: the SoS 2020 absentee file has the per-day detail too, but its download page
has a reCAPTCHA. The Elections Project rebuilt docs/GA.html from that SoS file
every day of early voting and committed it to GitHub, so the repo history is a
public day-by-day archive of the county "Total Voted" table (mail + in person).
Each commit message carries the data-through date ("CA GA 10-14" = votes
through Oct 14 2020; checked: that page's in-person total, 378,675, is exactly
3 days of voting from the Oct 12 opening).

Source: github.com/ElectProject/Early-Vote-2020G (CC BY-SA). Output (committed):
    data/ga_county/snapshots_2020.csv   through_date, county, ballots

If you later download the official GA_2020_general.zip, ingestor/ga_county.py 2020
builds exact per-day counts (data/ga_county/early_2020.csv), which take priority.

Run:  python ingestor/ga_2020_snapshots.py
"""
from __future__ import annotations

import csv
import json
import re
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ga_county" / "snapshots_2020.csv"
REPO = "ElectProject/Early-Vote-2020G"
API = f"https://api.github.com/repos/{REPO}/commits?path=docs/GA.html&per_page=100"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "earlyvote-analysis"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def commits():
    """[(through_date, sha)] — latest commit per data date, Oct 1 – Nov 3 2020."""
    out = {}
    for page in (1, 2, 3):
        batch = json.loads(_get(f"{API}&page={page}&since=2020-09-25T00:00:00Z&until=2020-11-06T00:00:00Z"))
        for c in batch:
            m = re.search(r"\b(1[01])-(\d{1,2})\b", c["commit"]["message"])
            if not m:
                continue
            d = date(2020, int(m.group(1)), int(m.group(2)))
            when = c["commit"]["committer"]["date"]
            if d not in out or when > out[d][0]:
                out[d] = (when, c["sha"])
        if len(batch) < 100:
            break
    return sorted((d, sha) for d, (_w, sha) in out.items())


def county_voted(page: str):
    """{COUNTY: total voted} from the 'Total Voted' datatable widget."""
    for blob in re.findall(r'<script type="application/json" data-for="[^"]+">(.*?)</script>', page, re.S):
        try:
            x = json.loads(blob)["x"]
        except (ValueError, KeyError, TypeError):
            continue
        cont = x.get("container", "")
        if "Registered Voters" in cont and "Total Voted" in cont and isinstance(x.get("data"), list):
            names, _reg, voted = x["data"][0], x["data"][1], x["data"][2]
            return {n.strip().upper(): int(v) for n, v in zip(names, voted) if n and v is not None}
    return {}


def main():
    rows = []
    for d, sha in commits():
        page = _get(f"https://raw.githubusercontent.com/{REPO}/{sha}/docs/GA.html").decode("utf-8", "replace")
        cv = county_voted(page)
        if len(cv) < 150:
            print(f"  {d}: county table not found ({len(cv)} rows), skipped")
            continue
        print(f"  {d}: {sum(cv.values()):>9,} voted in {len(cv)} counties  ({sha[:7]})")
        rows += [(d.isoformat(), c, v) for c, v in sorted(cv.items())]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["through_date", "county", "ballots"])
        w.writerows(rows)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
