"""
county_lean.py — the partisan baseline that powers the early-vote signal.

Per county, from data/baseline/county_results.csv:
  1. LEAN        — two-party Dem share of the county's total vote, blended across
                   the baseline cycles ("what this county normally does").
  2. EARLY MIX   — in-person early + mail volume, and the early share of the vote.
  3. TOTAL VOTES — blended total turnout (used as the fixture volume base for
                   totals-only states like NV/PA that have no mode breakdown).

Order-independent + totals-only safe: for each (year, county) we take the TOTAL
row if the source reported one, otherwise sum the per-mode rows — never both
(mixing them double-counts). This makes NC/GA (mode-level) and NV/PA (TOTAL-only)
both correct.

Run:  python analytics/county_lean.py   -> writes data/baseline/county_lean.csv
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data" / "baseline"
SRC = BASE / "county_results.csv"
OUT = BASE / "county_lean.csv"

EARLY_IN_PERSON = {"ONE STOP", "EARLY VOTING", "ADVANCED VOTING", "ADVANCE VOTING",
                   "ADVANCED", "EARLY", "LATE EARLY", "LATE VOTES", "IN PERSON"}
EARLY_MAIL = {"ABSENTEE BY MAIL", "ABSENTEE", "MAIL", "ABSENTEE/MAIL"}
ELECTION_DAY = {"ELECTION DAY", "POLLING PLACE"}
TOTAL_LABEL = "TOTAL"


def bucket(mode: str):
    m = mode.upper().strip()
    if m in EARLY_IN_PERSON:
        return "ei"
    if m in EARLY_MAIL:
        return "em"
    if m in ELECTION_DAY:
        return "ed"
    return "other"


def build():
    # stage per (state, fips, year): dedup TOTAL vs modes for party + turnout
    stage = defaultdict(lambda: {
        "name": "", "hasT": False, "tot_row": 0, "modes_sum": 0,
        "pT": defaultdict(int), "pM": defaultdict(int),
        "ei": 0, "em": 0, "ed": 0})
    for r in csv.DictReader(SRC.open(encoding="utf-8")):
        k = (r["state"], r["county_fips"], r["year"])
        s = stage[k]
        s["name"] = r["county_name"]
        m = r["mode"].upper().strip()
        p = r["party"].upper()
        v = int(r["votes"])
        if m == TOTAL_LABEL:
            s["hasT"] = True
            s["tot_row"] += v
            if p in ("DEMOCRAT", "REPUBLICAN"):
                s["pT"][p] += v
            continue
        s["modes_sum"] += v
        if p in ("DEMOCRAT", "REPUBLICAN"):
            s["pM"][p] += v
        b = bucket(m)
        if b in ("ei", "em", "ed"):
            s[b] += v

    # collapse years into per-county blended totals
    out = defaultdict(lambda: {"name": "", "dem": 0, "rep": 0,
                               "ei": 0, "em": 0, "ed": 0, "tot": 0})
    for (st, fips, _y), s in stage.items():
        o = out[(st, fips)]
        o["name"] = s["name"]
        if s["hasT"]:
            o["dem"] += s["pT"]["DEMOCRAT"]; o["rep"] += s["pT"]["REPUBLICAN"]
            o["tot"] += s["tot_row"]
        else:
            o["dem"] += s["pM"]["DEMOCRAT"]; o["rep"] += s["pM"]["REPUBLICAN"]
            o["tot"] += s["modes_sum"]
        o["ei"] += s["ei"]; o["em"] += s["em"]; o["ed"] += s["ed"]

    rows = []
    for (st, fips), o in sorted(out.items()):
        two = o["dem"] + o["rep"]
        early = o["ei"] + o["em"]
        rows.append({
            "state": st, "county_fips": fips, "county_name": o["name"],
            "dem_votes": o["dem"], "rep_votes": o["rep"], "two_party": two,
            "lean_dem": round(o["dem"] / two, 4) if two else None,
            "early_inperson": o["ei"], "early_mail": o["em"],
            "election_day": o["ed"], "total_votes": o["tot"],
            "early_share": round(early / o["tot"], 4) if o["tot"] else None,
        })
    return rows


def main():
    rows = build()
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    for st in sorted({r["state"] for r in rows}):
        rs = [r for r in rows if r["state"] == st and r["lean_dem"] is not None]
        d = sum(r["dem_votes"] for r in rs); t = sum(r["two_party"] for r in rs)
        early = sum(r["early_inperson"] + r["early_mail"] for r in rs)
        tot = sum(r["total_votes"] for r in rs)
        em = f"{early/tot:.1%}" if tot else "n/a"
        print(f"  {st}: {len(rs)} counties | Dem two-party {d/t:.1%} | early share {em}")
    print(f"\n  wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
