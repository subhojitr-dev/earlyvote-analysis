"""
sc_fetch.py — South Carolina early (in-person) vote by county vs the same day of early voting in 2022.

2026  SC Election Commission early-voting report: a CSV posted (and replaced as early voting goes on)
      on https://scvotes.gov/elections-statistics/voter-participation/ — one row per county with a
      column per early-voting day, then a row per voting site. This script finds the newest
      2026 general-election early-voting CSV on that page (skipping primary / runoff / special files).
2022  The Commission's archived "EV Stats (2022 GE)" workbook from 2022-Historical-Absentee-EV-Reports.zip
      (same layout: county totals by day, Oct 24 – Nov 5 2022).
Mail  2022 mail ballots exist only as a final total, so the comparison is IN-PERSON early votes only
      (like Texas and Ohio). South Carolina has no party registration.

Outputs (counts only):
  data/sc_county/early_{2022,2026}.csv   county, mode, date, ballots   (mode = inperson)
  data/live/sc_current.csv + sc_meta.json

Run:  python ingestor/sc_fetch.py
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
import zipfile
from datetime import date, datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sc_county"
LIVE = ROOT / "data" / "live"
INCOMING = ROOT / "data" / "incoming" / "sc"
UA = "Mozilla/5.0 (earlyvote-analysis; campaign-hub-hazel.vercel.app)"
STATS_PAGE = "https://scvotes.gov/elections-statistics/voter-participation/"
ZIP22 = "https://scvotes.gov/wp-content/uploads/2022/12/2022-Historical-Absentee-EV-Reports.zip"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def county_name(s: str) -> str:
    return re.sub(r"\s+Total\s*$", "", str(s)).strip().upper()


def write_daily(year: int, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"early_{year}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["county", "mode", "date", "ballots"])
        w.writerows(sorted(rows))


# ------------------------------------------------------------------ 2022
def build_2022():
    z = INCOMING / "sc2022.zip"
    if not z.exists():
        INCOMING.mkdir(parents=True, exist_ok=True)
        z.write_bytes(get(ZIP22))
    with zipfile.ZipFile(z) as zf:
        name = next(n for n in zf.namelist() if "EV Stats" in n and "GE" in n)
        ws = openpyxl.load_workbook(io.BytesIO(zf.read(name)), read_only=True, data_only=True).worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
    hdr = next(r for r in rows if r and str(r[0]).strip() == "County")
    days = [(i, d.date()) for i, d in enumerate(hdr) if isinstance(d, datetime)]
    out = []
    for r in rows:
        if not r or not isinstance(r[0], str) or not r[0].strip().endswith("Total") or "Statewide" in r[0]:
            continue
        for i, d in days:
            if isinstance(r[i], (int, float)) and r[i]:
                out.append((county_name(r[0]), "inperson", d.isoformat(), int(r[i])))
    write_daily(2022, out)
    return out


# ------------------------------------------------------------------ 2026
def find_2026_csv():
    """URL of the newest 2026 general-election early-voting CSV on the statistics page, or None."""
    page = get(STATS_PAGE).decode("utf-8", "replace")
    best = None
    for href, text in re.findall(r'<a[^>]+href="([^"]+\.csv)"[^>]*>(.*?)</a>', page, flags=re.S):
        label = (re.sub(r"<[^>]+>", " ", text) + " " + href).lower()
        if "/2026/" not in href or "early" not in label:
            continue
        if any(w in label for w in ("primary", "runoff", "special", "june", "-may", "march")):
            continue
        m = re.search(r"/2026/(\d{2})/", href)
        key = (m.group(1) if m else "00", href)
        if best is None or key > best[0]:
            best = (key, href)
    return best[1] if best else None


def parse_2026(text: str):
    rows = list(csv.reader(io.StringIO(text)))
    hi = next(i for i, r in enumerate(rows) if r and r[0].strip().lower() == "jurisdiction")
    days = []
    for i, h in enumerate(rows[hi]):
        h = h.strip()
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                days.append((i, datetime.strptime(h, fmt).date()))
                break
            except ValueError:
                pass
    out = []
    for r in rows[hi + 1:]:
        if not r or not r[0].strip() or r[0].strip().lower() == "south carolina":
            continue
        for i, d in days:
            v = re.sub(r"[^\d]", "", r[i] if i < len(r) else "")
            if v and int(v):
                out.append((county_name(r[0]), "inperson", d.isoformat(), int(v)))
    return out


def write_live(rows, src):
    fips = {r["county_name"].upper(): r["county_fips"]
            for r in csv.DictReader((ROOT / "data" / "baseline" / "county_lean.csv").open(encoding="utf-8"))
            if r["state"] == "SC"}
    by_c, last = {}, None
    for c, _m, d, n in rows:
        by_c[c] = by_c.get(c, 0) + n
        last = max(last, d) if last else d
    miss = sorted(set(by_c) - set(fips))
    if miss:
        print(f"  warning: counties without a FIPS match: {miss}")
    LIVE.mkdir(exist_ok=True)
    with (LIVE / "sc_current.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["state", "county_fips", "ballots"])
        for c, v in sorted(by_c.items()):
            if c in fips:
                w.writerow(["SC", fips[c], v])
    tot = sum(by_c.values())
    meta = {"as_of": last, "ballots": tot, "inperson": tot, "basis": "in-person only",
            "source": "SC Election Commission early-voting report", "url": src}
    (LIVE / "sc_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def main():
    r22 = build_2022()
    print(f"2022: {sum(n for *_, n in r22):,} early in-person votes, {len({r[0] for r in r22})} counties")
    url = find_2026_csv()
    if not url:
        print("2026: the general-election early-voting report isn't posted on scvotes.gov yet — nothing to update")
        return 0
    r26 = parse_2026(get(url).decode("utf-8-sig", "replace"))
    write_daily(2026, r26)
    meta = write_live(r26, url)
    print(f"SC through {meta['as_of']}: {meta['ballots']:,} early in-person votes  [{url.rsplit('/', 1)[-1]}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
