"""
nv_fetch.py — Nevada early voting (in person + mail returned) by county and party, vs 2022.

2026  Secretary of State VIVID dashboard (https://www.nvsos.gov/vivid/), saved daily by
      ingestor/nv_browser_return.js + nv_save.py as data/incoming/nv/vivid_<date>.json:
        in-person early votes per day, by county and party (Dem / Rep / other)
        mail ballots sent / received / accepted, by county and party — a CURRENT total only, so the
        2026 mail history is built from the daily snapshots we keep.
2022  Secretary of State weekly turnout reports (2022 Election Information page; saved as
      data/incoming/nv/nv22_ev_week1.pdf and nv22_ev_week2.pdf). Each gives that WEEK's in-person
      early votes and mail ballots returned, by county and party:
        week 1 = through Fri Oct 28 2022 (11 days before Election Day; report "Updated 10/29/2022")
        week 2 = through Fri Nov 4 2022  (4 days out); week 1 + week 2 = all of early voting
      (checked: Clark in person 78,126 + 116,685 = 194,811 and mail 223,130, as reported at the time)
      2022 "Other" + "NPP" are combined as "other" to match 2026.

2026 is compared at the latest 2022 point it has reached (same days before Election Day):
end of week 1 (2026 data through Fri Oct 23) and end of week 2 (through Fri Oct 30).

Outputs (counts only)
  data/nv_county/ref_2022.csv       point, county, mode, party, ballots   (cumulative at each point)
  data/nv_county/inperson_2026.csv  date, county, party, ballots          (daily)
  data/nv_county/mail_2026.csv      snapshot, county, party, received     (one per saved snapshot)

Run:  python ingestor/nv_fetch.py
"""
from __future__ import annotations

import csv
import glob
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parent.parent
INC = ROOT / "data" / "incoming" / "nv"
OUT = ROOT / "data" / "nv_county"
POINTS_2022 = {"2022-10-28": ["nv22_ev_week1.pdf"], "2022-11-04": ["nv22_ev_week1.pdf", "nv22_ev_week2.pdf"]}
PARTY26 = {"dem": "D", "rep": "R", "other": "O", "DEM": "D", "REP": "R", "OTH": "O"}


def parse_week(path: Path):
    """{county: {'inperson': {D,R,O}, 'mail': {D,R,O}}} from a 2022 weekly report."""
    out = {}
    for line in (pypdf.PdfReader(str(path)).pages[0].extract_text() or "").split("\n"):
        m = re.match(r"^([A-Z][A-Za-z ]+?)\s+(\d[\d,]*\s.*)$", line.strip())
        if not m or m.group(1).strip() in ("Total", "Updated", "Note", "Statewide", "STATEWIDE"):
            continue
        nums = [int(x.replace(",", "")) for x in re.findall(r"(?<![\d.])(\d[\d,]*)(?![\d.%])", m.group(2))]
        if len(nums) < 10:
            continue
        ip, ml = nums[0:5], nums[5:10]          # total, Dem, Rep, Other, NPP
        if ip[0] != sum(ip[1:]) or ml[0] != sum(ml[1:]):
            raise ValueError(f"{path.name}: totals don't add up for {m.group(1)}: {nums[:10]}")
        out[m.group(1).strip().upper()] = {
            "inperson": {"D": ip[1], "R": ip[2], "O": ip[3] + ip[4]},
            "mail": {"D": ml[1], "R": ml[2], "O": ml[3] + ml[4]}}
    return out


def _write(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main():
    weeks = {f: parse_week(INC / f) for f in {f for fs in POINTS_2022.values() for f in fs}}
    ref = defaultdict(int)
    for point, files in POINTS_2022.items():
        for f in files:
            for c, modes in weeks[f].items():
                for mode, ps in modes.items():
                    for p, n in ps.items():
                        ref[(point, c, mode, p)] += n
    _write(OUT / "ref_2022.csv", ["point", "county", "mode", "party", "ballots"],
           [(*k, v) for k, v in sorted(ref.items())])

    snaps = sorted(glob.glob(str(INC / "vivid_*.json")))
    if not snaps:
        print("NV: no 2026 VIVID snapshot saved yet")
        return
    latest = json.loads(Path(snaps[-1]).read_text(encoding="utf-8"))
    ip = [(d["date"], r["county"].upper(), PARTY26[k], r[k]) for d in latest["turnout"]["days"]
          for r in d["rows"] for k in ("dem", "rep", "other")]
    _write(OUT / "inperson_2026.csv", ["date", "county", "party", "ballots"], sorted(ip))
    mail = {}
    for f in snaps:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for r in d["ballots"]["rows"]:
            snap = r.get("lastUpdated", "")[:10]
            try:
                snap = date(*map(int, (snap[6:10], snap[0:2], snap[3:5]))).isoformat()   # MM/DD/YYYY
            except ValueError:
                snap = d["ballots"]["generatedAt"][:10]
            seen = defaultdict(int)                  # a snapshot's party codes may map to the same bucket
            for p, n in r["rawByPartyCode"]["received"].items():
                seen[PARTY26.get(p, "O")] += n
            for p, n in seen.items():
                mail[(snap, r["county"].upper(), p)] = n
    _write(OUT / "mail_2026.csv", ["snapshot", "county", "party", "received"],
           [(*k, v) for k, v in sorted(mail.items())])
    tot_ip = sum(n for *_x, n in ip)
    last_snap = max(k[0] for k in mail)
    tot_mail = sum(v for k, v in mail.items() if k[0] == last_snap)
    w1 = sum(v for k, v in ref.items() if k[0] == "2022-10-28" and k[2] == "inperson")
    print(f"NV 2026: {tot_ip:,} in person ({latest['turnout']['days'][0]['date']}..{latest['turnout']['days'][-1]['date']}), "
          f"{tot_mail:,} mail received (snapshot {last_snap}); 2022 week-1 in person {w1:,}")


if __name__ == "__main__":
    main()
