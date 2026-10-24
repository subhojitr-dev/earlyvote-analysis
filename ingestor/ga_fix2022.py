"""
ga_fix2022.py — fill the holes in Georgia's 2022 absentee file.

The GA Secretary of State's 2022 general-election absentee file (our 2022 comparison
year) is missing most EARLY IN-PERSON records for two counties:
    Fulton    Oct 24 - Nov 4 2022   (file has 44% of the certified early vote)
    Gwinnett  Oct 24 - Oct 31 2022  (file has 62%)
On those days the file shows ~25 votes a day where the real figure was 10,000-19,000;
every other county matches its certified total within about +/-2%. Left alone, this
makes Fulton/Gwinnett look far ahead of 2022 and every other county look behind
(found 2026-10-24; Georgia Votes, which fills the same gap, confirmed it).

The fix, per county whose 2022 in-person total is under GAP_MIN of its certified
2022 "advance voting" total (MEDSL, U.S. Senate race):
  1. The daily shape of the rest of the state's in-person early vote is the template.
  2. The county's normal ratio to that template comes from its complete days; a day
     under SHORT_DAY of what that ratio predicts is short (empty or partial).
  3. The missing votes (certified total minus the file's total) are spread over the
     short days in proportion to each day's shortfall.
  4. District files: each bad day's estimate is split among the county's districts by
     their share of the county's in-person votes on its good days.
Once filled, the county total matches its certified total, so a second run finds no
gap and changes nothing (idempotent).

Files patched in place:
    data/ga_county/early_2022.csv        county, mode, date, ballots
    data/ga_districts/early_2022.csv     county, chamber, district, mode, days_out, ballots
    data/ga_districts/early_2022_cur.csv same, on today's district lines
and data/ga_county/fix2022.json records what was estimated (shown as a note on the site).

Run:  python ingestor/ga_fix2022.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COUNTY = ROOT / "data" / "ga_county" / "early_2022.csv"
DIST_FILES = [ROOT / "data" / "ga_districts" / "early_2022.csv",
              ROOT / "data" / "ga_districts" / "early_2022_cur.csv"]
CERT = ROOT / "data" / "baseline" / "county_results.csv"
NOTE = ROOT / "data" / "ga_county" / "fix2022.json"
EDAY = date(2022, 11, 8)

GAP_MIN = 0.90      # county in-person total under 90% of certified => has a gap
GOOD_DAY = 0.80     # days at >= 80% of the expected volume set the county's normal ratio
SHORT_DAY = 0.80    # days under 80% of expected (empty or partial) get filled by their shortfall


def certified_advance() -> dict[str, int]:
    out = Counter()
    for r in csv.DictReader(CERT.open(encoding="utf-8")):
        if r["state"] == "GA" and r["year"] == "2022" and r["mode"] == "ADVANCED":
            out[r["county_name"]] += int(r["votes"])
    return out


def plan():
    """{county: {date: estimated extra in-person ballots}} for every county with a gap."""
    rows = list(csv.DictReader(COUNTY.open(encoding="utf-8")))
    daily = defaultdict(Counter)                      # county -> date -> in-person ballots
    for r in rows:
        if r["mode"] == "inperson":
            daily[r["county"]][r["date"]] += int(r["ballots"])
    cert = certified_advance()
    gaps = {c for c, n in cert.items() if sum(daily[c].values()) < GAP_MIN * n}
    template = Counter()
    for c, by_day in daily.items():
        if c not in gaps:
            template.update(by_day)
    est, info = {}, {}
    top = max(template.values())
    for c in sorted(gaps):
        obs = daily[c]
        days = [d for d in template if template[d] >= 0.01 * top]          # real early-voting days
        ratio0 = sum(obs.values()) / sum(template[d] for d in days)
        good = [d for d in days if obs.get(d, 0) >= GOOD_DAY * template[d] * ratio0]
        ratio = sum(obs[d] for d in good) / sum(template[d] for d in good)
        # every day short of its expected volume (template x county's normal ratio)
        # gets a share of the missing votes in proportion to its shortfall
        short = {d: ratio * template[d] - obs.get(d, 0) for d in days
                 if obs.get(d, 0) < SHORT_DAY * ratio * template[d]}
        missing = cert[c] - sum(obs.values())
        w = sum(short.values())
        est[c] = {d: missing * v / w for d, v in short.items()}
        bad = sorted(short)
        info[c] = {"file_total": sum(obs.values()), "certified": cert[c], "estimated": missing,
                   "days": [bad[0], bad[-1]], "n_days": len(bad), "good_day_ratio": round(ratio, 5)}
    return rows, est, info


def patch_county(rows, est):
    tot = Counter()
    for r in rows:
        tot[(r["county"], r["mode"], r["date"])] += int(r["ballots"])
    for c, by_day in est.items():
        for d, n in by_day.items():
            tot[(c, "inperson", d)] += round(n)
    with COUNTY.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["county", "mode", "date", "ballots"])
        w.writerows(sorted((*k, v) for k, v in tot.items() if v > 0))


def patch_districts(path: Path, est):
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    bad_out = {c: {(EDAY - date.fromisoformat(d)).days: n for d, n in by_day.items()} for c, by_day in est.items()}
    share = defaultdict(Counter)                      # (county, chamber) -> district -> in-person on good days
    tot = Counter()
    for r in rows:
        k = (r["county"], r["chamber"], r["district"], r["mode"], int(r["days_out"]))
        tot[k] += int(r["ballots"])
        if r["county"] in bad_out and r["mode"] == "inperson" and int(r["days_out"]) not in bad_out[r["county"]]:
            share[(r["county"], r["chamber"])][r["district"]] += int(r["ballots"])
    for (c, ch), by_d in share.items():
        s = sum(by_d.values())
        for days_out, n in bad_out[c].items():
            for dist, v in by_d.items():
                tot[(c, ch, dist, "inperson", days_out)] += round(n * v / s)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["county", "chamber", "district", "mode", "days_out", "ballots"])
        w.writerows(sorted((*k, v) for k, v in tot.items() if v > 0))


def district_gaps(path: Path, est) -> dict:
    """The part of `est` for counties whose in-person total in this district file is
    still short of certified (each file is checked on its own, so regenerating only
    one of them is caught too)."""
    cert, tot = certified_advance(), Counter()
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if r["chamber"] == "house" and r["mode"] == "inperson":
            tot[r["county"]] += int(r["ballots"])
    return {c: v for c, v in est.items() if tot[c] < GAP_MIN * cert[c]}


def main():
    rows, est, info = plan()
    if est:
        for c, i in info.items():
            print(f"{c}: file {i['file_total']:,} vs certified {i['certified']:,} -> estimating "
                  f"{i['estimated']:,} in-person votes over {i['n_days']} days ({i['days'][0]} to {i['days'][1]})")
        patch_county(rows, est)
        print(f"patched {COUNTY.relative_to(ROOT)}")
        old = json.loads(NOTE.read_text(encoding="utf-8")) if NOTE.exists() else {}
        for c, i in info.items():
            old[c] = {**i, "by_day": {d: round(n) for d, n in sorted(est[c].items())}}
        NOTE.write_text(json.dumps(old, indent=1), encoding="utf-8")
        print(f"wrote {NOTE.relative_to(ROOT)}")
    elif NOTE.exists():                               # county file already filled: reuse its estimate
        est = {c: i["by_day"] for c, i in json.loads(NOTE.read_text(encoding="utf-8")).items()}
    for p in DIST_FILES:
        todo = district_gaps(p, est) if p.exists() else {}
        if todo:
            patch_districts(p, todo)
            print(f"patched {p.relative_to(ROOT)} ({', '.join(sorted(todo))})")
    if not est:
        print("2022 GA file: no county gaps found — nothing to do")


if __name__ == "__main__":
    main()
