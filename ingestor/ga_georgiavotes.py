"""
ga_georgiavotes.py — interim live GA county counts from georgiavotes.com.

Georgia Votes rebuilds its county table every morning from the same Secretary of
State absentee voter file we use (data through the previous day). Unlike the SoS
download page it has no reCAPTCHA, so this runs unattended. It is the FALLBACK:
when the official file (ingestor/ga_county.py 2026) is as new or newer, that wins.

Writes data/live/ga_current.csv + data/live/ga_meta.json (same shape as
ga_county.py). Per county: ballots = Mail (V) + Early (V)  (accepted mail +
in-person early votes).

Run:  python ingestor/ga_georgiavotes.py
"""
from __future__ import annotations

import csv
import html
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "data" / "live"
URL = "https://georgiavotes.com/county"


def _int(s: str) -> int:
    return int(s.replace(",", "").strip() or 0)


def fetch(url: str = URL) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (earlyvote-analysis)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def parse(page: str):
    """-> (updated datetime, {COUNTY: (mail_voted, early_voted)})"""
    m = re.search(r"Last updated\s*(?:<[^>]*>\s*)*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", page)
    if not m:
        raise SystemExit("could not find 'Last updated' stamp — page layout changed?")
    updated = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    table = re.search(r"<table.*?</table>", page, re.S).group(0)
    head = [html.unescape(re.sub("<[^>]+>", "", h)).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)]
    need = ["County", "Mail (V)", "Early (V)"]
    if not all(h in head for h in need):
        raise SystemExit(f"unexpected columns {head}")
    ix = {h: head.index(h) for h in need}
    out = {}
    for row in re.findall(r"<tr>(.*?)</tr>", table, re.S):
        cells = [html.unescape(re.sub("<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < len(head) or not cells[ix["County"]]:
            continue
        out[cells[ix["County"]].upper()] = (_int(cells[ix["Mail (V)"]]), _int(cells[ix["Early (V)"]]))
    return updated, out


def main():
    updated, rows = parse(fetch())
    # The site refreshes each morning from that morning's SoS file -> votes through yesterday.
    as_of = (updated.date() - timedelta(days=1)).isoformat()
    meta_p = LIVE / "ga_meta.json"
    if meta_p.exists():
        old = json.loads(meta_p.read_text())
        if old.get("source", "").startswith("GA Secretary") and old.get("as_of", "") >= as_of:
            print(f"official SoS file is current (as of {old['as_of']}); leaving it in place")
            return
    fips = {r["county_name"].upper().replace(" ", ""): r["county_fips"]
            for r in csv.DictReader((ROOT / "data" / "baseline" / "county_lean.csv").open(encoding="utf-8"))
            if r["state"] == "GA"}
    missing = [c for c in rows if c.replace(" ", "") not in fips]
    if missing or len(rows) != 159:
        raise SystemExit(f"county mismatch: {len(rows)} rows, unmatched {missing}")
    mail = sum(v[0] for v in rows.values())
    inperson = sum(v[1] for v in rows.values())
    LIVE.mkdir(parents=True, exist_ok=True)
    with (LIVE / "ga_current.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["state", "county_fips", "ballots"])
        w.writerows(sorted(("GA", fips[c.replace(" ", "")], m + e) for c, (m, e) in rows.items()))
    meta_p.write_text(json.dumps({"as_of": as_of, "ballots": mail + inperson, "inperson": inperson,
                                  "mail": mail, "source": f"georgiavotes.com (SoS file, updated {updated})"},
                                 indent=1))
    print(f"georgiavotes.com updated {updated}: {mail + inperson:,} ballots "
          f"({inperson:,} in person, {mail:,} mail) through {as_of}")


if __name__ == "__main__":
    main()
