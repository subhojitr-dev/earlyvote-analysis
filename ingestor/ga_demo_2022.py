"""
ga_demo_2022.py — who voted early in Georgia in the 2022 general, by race, gender and age, statewide,
for every day of early voting. Run once; the output is committed.

Georgia Votes (georgiavotes.com) has no 2022 archive of its own, but the Internet Archive kept a copy
of its home page almost every day in Oct–Nov 2022 (the LAST copy of each day is used, since the site
updates each morning and an early copy still shows the day before), and those pages carry the statewide 'Breakdown by
Race / Gender / Age' tables. One copy per day is read from web.archive.org (not from georgiavotes.com).

Output (data/ga_districts/, aggregate counts only):
  gv_demo_2022_state.csv   asof, dim, group, ballots
    asof = the page's own 'Last updated' date (counts run through the day before),
    dim = race | gender | age; group names match gv_demo_2026.csv.

Run:  python ingestor/ga_demo_2022.py
"""
from __future__ import annotations

import csv
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ga_districts" / "gv_demo_2022_state.csv"
UA = "Mozilla/5.0 (earlyvote-analysis; campaign-hub-hazel.vercel.app)"
CDX = ("https://web.archive.org/cdx/search/cdx?url=georgiavotes.com&from=20221017&to=20221109"
       "&output=json&filter=statuscode:200")
RENAME = {"gender": {"Female": "Women", "Male": "Men", "Unknown": "Not stated"},
          "age": {"Unknown": "Not stated"}, "race": {}}


def get(url: str) -> str:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(20)


def parse(page: str):
    """-> (last-updated date, {dim: {group: votes}}) from the 2022 page's
    'Breakdown by Race  A breakdown of the N people who have voted early  Race Votes Vote %  White 1,125,250 57.8% ...'"""
    page = re.sub(r"<script.*?</script>", "", page, flags=re.S)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    m = re.search(r"Last updated (\d{4}-\d{2}-\d{2})", text)
    out = {}
    for dim, label in (("race", "Race"), ("gender", "Gender"), ("age", "Age")):
        b = re.search(rf"Breakdown by {label} A breakdown of the [\d,]+ people who have voted early "
                      rf"{label} Votes Vote % (.*?)(?= By [A-Z]| 2018 general| 2020 general|$)", text)
        if b:
            out[dim] = {RENAME[dim].get(g, g): int(v.replace(",", ""))
                        for g, v in re.findall(r"([A-Za-z0-9+\-]+) ([\d,]+) [\d.]+%", b.group(1))}
    return (m.group(1) if m else None), out


def main():
    last = {}                                     # day -> last capture that day
    for _key, ts, orig, *_ in json.loads(get(CDX))[1:]:
        last[ts[:8]] = (ts, orig)
    rows, seen = [], set()
    for ts, orig in sorted(last.values()):
        time.sleep(4)                             # web.archive.org refuses rapid requests
        try:
            when, got = parse(get(f"https://web.archive.org/web/{ts}id_/{orig}"))
        except Exception as e:
            print(f"  {ts}: skipped ({e})")
            continue
        if not when or when in seen or len(got) < 3:
            continue
        seen.add(when)
        tot = sum(got["race"].values())
        print(f"  {ts}: updated {when}, {tot:,} early voters")
        rows += [(when, dim, g, v) for dim, groups in got.items() for g, v in groups.items()]
    if not rows:
        print("nothing parsed; nothing written")
        return 1
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["asof", "dim", "group", "ballots"])
        w.writerows(sorted(rows))
    print(f"wrote {OUT.name}: {len(seen)} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
