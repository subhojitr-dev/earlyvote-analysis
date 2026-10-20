"""
ga_demographics.py — who is voting early in Georgia, by race, gender and age, for every
State House, State Senate and congressional district (and statewide), from Georgia Votes.

Georgia's own early-vote file has no race or age. Georgia Votes (georgiavotes.com, a free
independent site) joins it to the state voter list, which records race, gender and age, and
publishes the totals per district each morning. We read those public pages (robots.txt allows
them; /api/ is not used), slowly, and credit the site on our pages.

  2026 general   georgiavotes.com/{statehouse?hd=N, statesen?sd=N, ushouse?cd=N}, and /  (statewide)
  2024 general   the same under /2024-general/  (FINAL 2024 early electorate — fetched once, cached)

Georgia Votes has no 2022 archive, so the comparison is with the whole 2024 early electorate
(a presidential year, not the same day) — labelled that way on the page.

Outputs (data/ga_districts/, committed; aggregate counts only):
  gv_demo_2026.csv     chamber, district, dim, group, ballots, asof      (latest snapshot)
  gv_demo_2024.csv     chamber, district, dim, group, ballots            (2024 final)
  gv_demo_history.csv  asof, chamber, district, dim, group, ballots      (one snapshot per day)
  chamber = house | senate | congress | state ; dim = race | gender | age

Run:  python ingestor/ga_demographics.py          (2026 snapshot; fetches 2024 once if missing)
"""
from __future__ import annotations

import csv
import html
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ga_districts"
BASE = "https://georgiavotes.com"
UA = "Mozilla/5.0 (earlyvote-analysis; campaign-hub-hazel.vercel.app)"
PAUSE = 0.6                                       # seconds between requests (be polite)
PAGES = {"house": ("statehouse", "hd", 180), "senate": ("statesen", "sd", 56), "congress": ("ushouse", "cd", 14)}
RENAME = {"gender": {"Female": "Women", "Male": "Men", "Unknown": "Not stated"},
          "age": {"Unknown": "Not stated"}, "race": {}}


def get(url: str) -> str:
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)


def parse(page: str):
    """-> {dim: {group: votes}} from the server-rendered 'By Race / Gender / Age' blocks.
    Reads by content, not exact markup (the site restyled its pages on 2026-10-20): within the
    block that starts at id="race" (etc.), the <p> texts are the column headers, then the group
    names, then the vote counts, then the percentages."""
    out = {}
    heads = {"Race", "Gender", "Age", "Votes", "Vote %", "Vote%"}
    for dim in ("race", "gender", "age"):
        m = re.search(rf'id="{dim}"(.*?)(?=id="[a-z0-9]+"|</main>|$)', page, flags=re.S)
        if not m:
            continue
        texts = [html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
                 for t in re.findall(r"<p[^>]*>(.*?)</p>", m.group(1), flags=re.S)]
        texts = [t for t in texts if t and t not in heads]
        names = [t for t in texts if not re.fullmatch(r"[\d,.]+%?", t)]
        votes = [int(t.replace(",", "")) for t in texts if re.fullmatch(r"[\d,]+", t)]
        if names and len(names) == len(votes):
            out[dim] = {RENAME[dim].get(g, g): v for g, v in zip(names, votes)}
    return out


def asof(page: str) -> str | None:
    m = re.search(r"Last updated\s*(?:<!-- -->)?\s*(\d{4}-\d{2}-\d{2})", page)
    return m.group(1) if m else None


def snapshot(prefix: str = ""):
    rows, when = [], None
    home = get(f"{BASE}{prefix}/")
    when = asof(home)
    for dim, groups in parse(home).items():
        rows += [("state", "0", dim, g, v) for g, v in groups.items()]
    for ch, (path, q, n) in PAGES.items():
        for d in range(1, n + 1):
            time.sleep(PAUSE)
            page = get(f"{BASE}{prefix}/{path}?{q}={d}")
            got = parse(page)
            if not got:
                print(f"  warning: no breakdown on {prefix}/{path}?{q}={d}")
            for dim, groups in got.items():
                rows += [(ch, str(d), dim, g, v) for g, v in groups.items()]
        print(f"  {prefix or '2026'} {ch}: {n} districts")
    return rows, when


def _write(p: Path, header, rows):
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f24 = OUT / "gv_demo_2024.csv"
    if not f24.exists():
        rows24, _ = snapshot("/2024-general")
        _write(f24, ["chamber", "district", "dim", "group", "ballots"], rows24)
        print(f"wrote {f24.name} ({len(rows24):,} rows)")
    rows, when = snapshot()
    if not rows:
        print("no data parsed — Georgia Votes page layout may have changed; nothing written")
        return 1
    when = when or time.strftime("%Y-%m-%d")
    _write(OUT / "gv_demo_2026.csv", ["chamber", "district", "dim", "group", "ballots", "asof"],
           [(*r, when) for r in rows])
    hist = OUT / "gv_demo_history.csv"
    old = []
    if hist.exists():
        old = [r for r in csv.reader(hist.open(encoding="utf-8"))][1:]
        old = [r for r in old if r[0] != when]                      # one snapshot per day
    _write(hist, ["asof", "chamber", "district", "dim", "group", "ballots"], old + [(when, *r) for r in rows])
    tot = sum(v for c, _, dim, _, v in rows if c == "state" and dim == "race")
    print(f"Georgia Votes data as of {when}: {tot:,} early voters statewide; {len(rows):,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
