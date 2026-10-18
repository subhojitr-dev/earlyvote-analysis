"""
oh_absentee.py — Ohio early vote by county vs the same point in 2022.

2026: the Secretary of State's statewide absentee/early-vote file (DATA Act, one row per
voter, updated weekdays ~11 AM) is refused to scripts, so it is reduced to counts in the
browser pane on the SoS data portal with ingestor/oh_browser_aggregate.js, which writes
OH_2026_agg_<report date>.txt (counts only). Put it in data/incoming/oh/ (or leave it in
Downloads). In-person = ballot sent and returned the same day; checked against the SoS's
Oct 13 release (194,841 in person after week 1; the file gives ~196,900 for those days).

2022: no per-voter file exists (the DATA Act began in 2024). The SoS published county
spreadsheets at three points (from the Internet Archive; data/incoming/oh/oh22_*.xlsx):
    released Oct 25 2022  → votes through Oct 24 (15 days out): early in person by county
    released Nov 1 2022   → through Oct 31 (8 days out): in person + returned
    released Nov 7 2022   → through Nov 6 (2 days out): in person + returned
So Ohio is compared on IN-PERSON early votes by county, with 2026 cut back to the same
number of days before Election Day as the latest 2022 snapshot it has reached. Before the
first snapshot point only a statewide comparison exists (Oct 18 2022 release: 50,368 in
person through Oct 17, 22 days out), and the dashboard shows that as a notice.

Outputs (counts only):
    data/oh_county/early_2026.csv     county, mode, date, ballots       (daily)
    data/oh_county/early_2022.csv     county, mode, date, ballots       (in person, as
                                      increments between snapshot dates, so summing rows up
                                      to a snapshot date gives that snapshot)
    data/live/oh_current.csv + oh_meta.json   2026 in-person by county at the aligned date

Run:  python ingestor/oh_absentee.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
INCOMING = ROOT / "data" / "incoming" / "oh"
OUT = ROOT / "data" / "oh_county"
LIVE = ROOT / "data" / "live"
EDAY = {2022: date(2022, 11, 8), 2026: date(2026, 11, 3)}
SNAPSHOTS = {date(2022, 10, 24): "oh22_2022-10-25.xlsx",        # through-date -> file
             date(2022, 10, 31): "oh22_2022-11-01.xlsx",
             date(2022, 11, 6): "oh22_2022-11-07.xlsx"}
STATEWIDE_2022 = (date(2022, 10, 17), 50368)                    # Oct 18 2022 release, in person


def latest_agg() -> Path:
    cands = glob.glob(str(INCOMING / "OH_2026_agg_*.txt")) + \
            glob.glob(os.path.expanduser("~/Downloads/OH_2026_agg_*.txt"))
    if not cands:
        raise SystemExit("no OH_2026_agg_*.txt — run ingestor/oh_browser_aggregate.js in the browser pane first")
    return Path(max(cands, key=lambda p: Path(p).name))


def read_agg(p: Path):
    parts = dict(line.split("=", 1) for line in p.read_text(encoding="utf-8").splitlines() if "=" in line)
    stamp = date.fromisoformat(parts["STAMP"][:10])
    rows = Counter()
    for item in parts["AGG"].split(";"):
        c, d, m, n = item.rsplit("|", 3)
        rows[(c.strip().upper(), "inperson" if m == "I" else "mail", d)] += int(n)
    return stamp, rows


def read_snapshots():
    """{through_date: {COUNTY: (in_person, mail_returned or None)}}"""
    out = {}
    for d, f in SNAPSHOTS.items():
        rows = list(openpyxl.load_workbook(INCOMING / f, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
        head = next(i for i, r in enumerate(rows) if any(isinstance(x, str) and "Early" in x for x in r if x))
        h = [str(x or "") for x in rows[head]]
        ip = next(i for i, x in enumerate(h) if "Early" in x and "Request" not in x)   # first block = 2022
        rt = next((i for i, x in enumerate(h) if "Returned" in x), None)
        snap = {}
        for r in rows[head + 1:]:
            if not r[0] or str(r[0]).upper() == "TOTAL" or not isinstance(r[ip], (int, float)):
                continue
            snap[str(r[0]).strip().upper()] = (int(r[ip]), int(r[rt]) - int(r[ip]) if rt is not None else None)
        out[d] = snap
    return out


def _write(p: Path, header, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main():
    agg = latest_agg()
    stamp, rows = read_agg(agg)
    complete = stamp - timedelta(days=1)            # the report is built mid-morning: yesterday is the last full day
    rows = Counter({k: v for k, v in rows.items() if date.fromisoformat(k[2]) <= complete})
    _write(OUT / "early_2026.csv", ["county", "mode", "date", "ballots"], sorted((*k, v) for k, v in rows.items()))

    snaps = read_snapshots()
    prev, inc = {}, []
    for d in sorted(snaps):
        for c, (ip, _ml) in sorted(snaps[d].items()):
            inc.append((c, "inperson", d.isoformat(), ip - prev.get(c, 0)))
            prev[c] = ip
    _write(OUT / "early_2022.csv", ["county", "mode", "date", "ballots"], inc)

    # 2026 cut at the same days-before-Election-Day as the latest 2022 snapshot it has reached
    aligned = {d: EDAY[2026] - (EDAY[2022] - d) for d in snaps}
    reached = [d for d, a in aligned.items() if a <= complete]
    ip_by_day = Counter()
    for (c, m, d), v in rows.items():
        if m == "inperson":
            ip_by_day[d] += v
    cum = lambda upto: sum(v for d, v in ip_by_day.items() if d <= upto.isoformat())
    sw_d22, sw_n22 = STATEWIDE_2022
    sw_d26 = EDAY[2026] - (EDAY[2022] - sw_d22)
    meta = {"source": "Ohio Secretary of State absentee/early-vote file (in person)", "basis": "in-person only",
            "latest": complete.isoformat(), "latest_inperson": cum(complete),
            "latest_mail": sum(v for (c, m, d), v in rows.items() if m == "mail"),
            "statewide": {"d26": sw_d26.isoformat(), "n26": cum(sw_d26), "d22": sw_d22.isoformat(), "n22": sw_n22}}
    if reached:
        snap22 = max(reached)
        cut = aligned[snap22]
        meta.update(as_of=cut.isoformat(), snapshot_2022=snap22.isoformat(), pending=False)
    else:
        cut = complete
        nxt = min(aligned.values())
        meta.update(as_of=complete.isoformat(), pending=True,
                    first_compare=(nxt + timedelta(days=1)).isoformat(), first_through=nxt.isoformat())
    fips = {r["county_name"].upper(): r["county_fips"]
            for r in csv.DictReader((ROOT / "data" / "baseline" / "county_lean.csv").open(encoding="utf-8"))
            if r["state"] == "OH"}
    per = Counter()
    for (c, m, d), v in rows.items():
        if m == "inperson" and d <= cut.isoformat():
            per[c] += v
    miss = [c for c in per if c not in fips]
    if miss:
        raise SystemExit(f"no FIPS for {miss}")
    _write(LIVE / "oh_current.csv", ["state", "county_fips", "ballots"], sorted(("OH", fips[c], v) for c, v in per.items()))
    meta["ballots"] = meta["inperson"] = sum(per.values())
    (LIVE / "oh_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"OH report {stamp} ({agg.name}): {meta['latest_inperson']:,} in person + {meta['latest_mail']:,} mail through {complete}")
    print(f"  statewide same day: 2026 {meta['statewide']['n26']:,} through {sw_d26} vs 2022 {sw_n22:,} through {sw_d22}"
          f" = {meta['statewide']['n26'] / sw_n22:.1f}x")
    print(f"  county comparison: " + (f"2026 through {cut} vs 2022 snapshot through {meta['snapshot_2022']}" if reached
                                     else f"starts with data through {meta['first_through']} (posted ~{meta['first_compare']})"))


if __name__ == "__main__":
    main()
