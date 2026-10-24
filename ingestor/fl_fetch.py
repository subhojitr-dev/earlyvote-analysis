"""
fl_fetch.py — Florida early vote (in person) + vote-by-mail ballots returned, by county and party,
vs the same point in 2022.

2026  Florida Division of Elections daily statistics files (public, by 9 AM, cumulative through
      the previous day), one row per county with Republican / Democrat / Other / NPA counts:
        electionfiles.floridados.gov/countyballotreportfiles/Stats_49894_EarlyVoted.txt
        electionfiles.floridados.gov/countyballotreportfiles/Stats_49894_VbmVoted.txt
      (a cache-busting query is added; without it a cached copy can be a day or two old).
      Each run stores that day's snapshot, so the 2026 series builds up day by day; earlier 2026
      days are back-filled from Internet Archive copies of the statistics page when they exist.
2022  The same statistics page, as saved by the Internet Archive almost daily from Oct 21 to
      Election Day 2022 (web.archive.org); the county tables "Voted Vote-by-Mail" and "Voted
      Early" are read from each saved copy. (The Division's own 2022 archive is final totals only.)

A snapshot compiled on day D covers votes through D-1. Daily counts are the differences between
consecutive snapshots, so summing a county's rows up to a date gives that date's snapshot.

Outputs (counts only):
  data/fl_county/snapshots_{2022,2026}.csv  through, county, mode, party, cumulative
  data/fl_county/early_{2022,2026}.csv      county, mode, date, ballots   (daily increments)
  data/live/fl_current.csv + fl_meta.json   2026 in-person + mail by county, latest day

Run:  python ingestor/fl_fetch.py            (today's 2026 files; builds 2022 once if missing)
"""
from __future__ import annotations

import csv
import html
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fl_county"
LIVE = ROOT / "data" / "live"
CACHE = ROOT / "data" / "incoming" / "fl" / "wayback"
UA = "Mozilla/5.0 (earlyvote-analysis; campaign-hub-hazel.vercel.app)"
ELECTION = {2022: "26906", 2026: "49894"}
STATS_URL = "https://electionfiles.floridados.gov/countyballotreportfiles/Stats_{eid}_{kind}.txt?ts={ts}"
PAGE = "countyballotfiles.floridados.gov/VoteByMailEarlyVotingReports/PublicStats"
MODES = {"EarlyVoted": "inperson", "VbmVoted": "mail"}
PARTIES = ("R", "D", "O", "N")


def get(url: str, tries: int = 3) -> str:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5)


def num(s: str) -> int:
    s = re.sub(r"[^\d]", "", s or "")
    return int(s) if s else 0


# ------------------------------------------------------------------ 2026 official files
def fetch_official(year: int = 2026):
    """-> (through date, {(COUNTY, mode, party): cumulative})"""
    snap, compiled = {}, None
    for kind, mode in MODES.items():
        txt = get(STATS_URL.format(eid=ELECTION[year], kind=kind, ts=int(time.time())))
        for r in csv.DictReader(txt.splitlines(), delimiter="\t"):
            county = (r.get("CountyName") or "").strip().upper()
            if county == "STATE TOTALS":
                m = re.search(r"(\d{2}/\d{2}/\d{4})", r.get("CompileDate") or "")
                if m:
                    d = datetime.strptime(m.group(1), "%m/%d/%Y").date()
                    compiled = max(compiled, d) if compiled else d
                continue
            if not county:
                continue
            for p, col in zip(PARTIES, ("TotalRep", "TotalDem", "TotalOth", "TotalNpa")):
                snap[(county, mode, p)] = num(r.get(col))
    if not compiled:
        raise SystemExit("could not read the compile date from the Florida statistics files")
    return compiled - timedelta(days=1), snap


# ------------------------------------------------------------------ Internet Archive snapshots
def wayback_list(year: int):
    """One capture per compile day: [(timestamp)] for the statistics page during that election."""
    lo, hi = (f"{year}0901", f"{year}1110")
    url = (f"https://web.archive.org/cdx/search/cdx?url={PAGE}*&output=json&fl=timestamp,statuscode"
           f"&from={lo}&to={hi}&filter=statuscode:200")
    rows = json.loads(get(url) or "[]")[1:]
    return [r[0] for r in rows]


def parse_page(page: str, election: str):
    """Statistics page -> (through date, {(COUNTY, mode, party): cumulative}) or None."""
    if election not in page:
        return None
    snap, compiled = {}, None
    for tid, mode in (("county_abl", "mail"), ("county_evs", "inperson")):
        m = re.search(rf'id="{tid}".*?(<table.*?</table>)', page, flags=re.S)
        if not m:
            return None
        for tr in re.findall(r"<tr.*?</tr>", m.group(1), flags=re.S):
            cells = [html.unescape(re.sub(r"<[^>]+>", " ", c)).strip()
                     for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
            if len(cells) < 7 or election not in cells[1]:   # early-Oct pages still list the primary
                continue
            county = re.sub(r"\s+", " ", cells[0]).upper()
            for p, v in zip(PARTIES, cells[2:6]):
                snap[(county, mode, p)] = num(v)
            dm = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", cells[7] if len(cells) > 7 else "")
            if dm:
                d = datetime.strptime(dm.group(1), "%m/%d/%Y").date()
                compiled = max(compiled, d) if compiled else d
    if not compiled or not snap:
        return None
    return compiled - timedelta(days=1), snap


def backfill(year: int, have: set):
    """Add Internet Archive snapshots for days not already stored. Returns {through: snap}."""
    CACHE.mkdir(parents=True, exist_ok=True)
    got = {}
    try:
        stamps = wayback_list(year)
    except Exception as e:
        print(f"  Internet Archive list failed ({e}); skipping back-fill")
        return got
    by_day = {}
    for ts in stamps:                         # keep the latest capture of each day
        by_day[ts[:8]] = ts
    for day, ts in sorted(by_day.items()):
        f = CACHE / f"{ts}.html"
        if not f.exists():
            try:
                f.write_text(get(f"https://web.archive.org/web/{ts}id_/https://{PAGE}"), encoding="utf-8")
                time.sleep(1.5)
            except Exception as e:
                print(f"  {ts}: fetch failed ({e})")
                continue
        res = parse_page(f.read_text(encoding="utf-8", errors="replace"), ELECTION[year])
        if res and res[0] not in have and res[0] not in got:
            got[res[0]] = res[1]
    return got


# ------------------------------------------------------------------ storage
def load_snaps(year: int):
    p = OUT / f"snapshots_{year}.csv"
    snaps = defaultdict(dict)
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            snaps[date.fromisoformat(r["through"])][(r["county"], r["mode"], r["party"])] = int(r["cumulative"])
    return snaps


def save_snaps(year: int, snaps):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"snapshots_{year}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["through", "county", "mode", "party", "cumulative"])
        for d in sorted(snaps):
            for (c, m, p), v in sorted(snaps[d].items()):
                w.writerow([d.isoformat(), c, m, p, v])


def write_daily(year: int, snaps):
    """Increments between consecutive snapshots (never negative). When snapshots are more than
    a day apart (the Internet Archive skipped days, e.g. no 2022 copy through Oct 28 or 29), the
    increment is spread evenly over the days it covers. Dating it all on the later day made a
    same-day comparison on a skipped day use the previous day's total (found 2026-10-24: FL read
    105% of 2022 instead of ~97%)."""
    rows, prev, last = [], defaultdict(int), None
    for d in sorted(snaps):
        tot = defaultdict(int)
        for (c, m, _p), v in snaps[d].items():
            tot[(c, m)] += v
        span = [d] if last is None else [last + timedelta(days=i) for i in range(1, (d - last).days + 1)]
        for (c, m), v in sorted(tot.items()):
            inc = v - prev[(c, m)]
            if inc > 0:
                parts = [inc * (i + 1) // len(span) - inc * i // len(span) for i in range(len(span))]
                rows.extend([c, m, day.isoformat(), n] for day, n in zip(span, parts) if n > 0)
            prev[(c, m)] = max(prev[(c, m)], v)
        last = d
    with (OUT / f"early_{year}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["county", "mode", "date", "ballots"])
        w.writerows(rows)
    return len(rows)


def write_live(through: date, snap):
    fips = {}
    for r in csv.DictReader((ROOT / "data" / "baseline" / "county_lean.csv").open(encoding="utf-8")):
        if r["state"] == "FL":
            fips[r["county_name"].upper()] = r["county_fips"]
    by_c, modes, party = defaultdict(int), defaultdict(int), defaultdict(int)
    missing = set()
    for (c, m, p), v in snap.items():
        by_c[c] += v
        modes[m] += v
        party[p] += v
        if c not in fips:
            missing.add(c)
    if missing:
        print(f"  warning: counties without a FIPS match: {sorted(missing)}")
    LIVE.mkdir(exist_ok=True)
    with (LIVE / "fl_current.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["state", "county_fips", "ballots"])
        for c, v in sorted(by_c.items()):
            if c in fips:
                w.writerow(["FL", fips[c], v])
    tot = sum(by_c.values())
    meta = {"as_of": through.isoformat(), "ballots": tot, "inperson": modes["inperson"], "mail": modes["mail"],
            "party": {"Republican": party["R"], "Democrat": party["D"], "Other": party["O"], "No party": party["N"]},
            "source": "Florida Division of Elections daily vote-by-mail and early voting statistics"}
    (LIVE / "fl_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # 2022 baseline (once): Internet Archive copies of the statistics page
    s22 = load_snaps(2022)
    if not s22:
        print("building 2022 from Internet Archive snapshots (one-time)…")
        s22.update(backfill(2022, set()))
        save_snaps(2022, s22)
    n22 = write_daily(2022, s22)
    print(f"2022: {len(s22)} snapshot days ({min(s22)} … {max(s22)}), {n22} county-day rows" if s22 else "2022: none")

    # 2026: today's official files + any archived earlier days
    s26 = load_snaps(2026)
    through, snap = fetch_official(2026)
    s26[through] = snap
    if len(s26) < 3:                                   # first runs: try to back-fill earlier days
        s26.update(backfill(2026, set(s26)))
    save_snaps(2026, s26)
    write_daily(2026, s26)
    meta = write_live(through, snap)
    print(f"FL through {through}: {meta['ballots']:,} ballots ({meta['inperson']:,} early in person, "
          f"{meta['mail']:,} mail); {len(s26)} snapshot days stored")
    p = meta["party"]
    print(f"  party: R {p['Republican']:,} / D {p['Democrat']:,} / NPA {p['No party']:,} / other {p['Other']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
