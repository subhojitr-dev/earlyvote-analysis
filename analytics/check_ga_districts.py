"""
check_ga_districts.py — sanity checks for the Georgia district drill-down data (web/ga/).

Run after `python web/build_ga_districts.py [GA|NC]`:
    python analytics/check_ga_districts.py        (Georgia)
    python analytics/check_ga_districts.py NC     (North Carolina)

Checks
  1. Every district (GA 180 House + 56 Senate; NC 120 + 50) appears, with a 2024 lean.
  2. 2024 presidential lean matches independently published values
     (akashic.app, retrieved 2026-10-04) within 2 pts. The published figures are
     margins over ALL votes; ours are two-party (D vs R), so small gaps are expected.
  3. Each district's in-person + mail counts add up to its overall count.
  4. The counties listed for a district cover >= 98% of its votes (counties with
     < 0.5% are hidden as address noise, so it is not exactly 100%).
Exits non-zero if anything fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ST = (sys.argv[1] if len(sys.argv) > 1 else "GA").upper()
WEB = Path(__file__).resolve().parent.parent / "web" / ST.lower()
SIZE = {"GA": (180, 56), "NC": (120, 50)}[ST]

# 2024 presidential margin (D minus R, % of all votes) — akashic.app, retrieved 2026-10-04/05
PUBLISHED = {
    "GA": {"house:25": -11.9, "house:33": -64.6, "house:48": 1.2, "house:50": 13.0, "house:56": 77.4, "house:80": 21.4, "house:97": 23.2, "house:101": 46.4, "house:151": -7.9, "senate:6": -40.4, "senate:8": -34.7, "senate:14": 18.1, "senate:17": 52.7, "senate:21": -34.0, "senate:40": 27.9, "senate:42": -11.7, "senate:55": 54.4},
    "NC": {"house:1": -28.7, "house:11": 32.5, "house:34": 30.8, "house:35": -1.9, "house:36": 11.7, "house:40": 27.6, "house:49": 40.2, "house:63": -7.7, "house:98": 2.6, "house:103": 14.5, "house:105": 0.6, "house:112": 52.1, "senate:7": -5.5, "senate:13": 4.6, "senate:15": 36.9, "senate:17": 29.3, "senate:18": -0.5, "senate:37": -26.6, "senate:41": 51.3, "senate:42": 6.5},
}[ST]

# 2024 presidential margin (D minus R, % of all votes) — akashic.app, retrieved 2026-10-04/05
PUBLISHED = {
    "GA": {"house:25": -11.9, "house:33": -64.6, "house:48": 1.2, "house:56": 77.4, "house:151": -7.9,
           "senate:6": -40.4, "senate:8": -34.7, "senate:14": 18.1, "senate:55": 54.4},
    "NC": {"house:1": -28.7, "house:34": 30.8, "house:98": 2.6,
           "senate:7": -5.5, "senate:18": -0.5, "senate:42": 6.5},
}[ST]
TOL = 2.0   # third-party votes: published margins use all votes, ours D-vs-R only


def main() -> int:
    fails = []
    districts = {}
    for f in sorted((WEB / "county").glob("*.json")):
        cd = json.loads(f.read_text(encoding="utf-8"))
        for mode, md in cd["modes"].items():
            for k, s in md["districts"].items():
                districts.setdefault(mode, {})[k] = s

    for mode, ds in districts.items():
        house = [k for k in ds if k.startswith("house:")]
        senate = [k for k in ds if k.startswith("senate:")]
        if (len(house), len(senate)) != SIZE:
            fails.append(f"[{mode}] expected {SIZE[0]} House + {SIZE[1]} Senate districts, got {len(house)} + {len(senate)}")
        no_lean = [k for k, s in ds.items() if s["lean"] is None]
        if no_lean:
            fails.append(f"[{mode}] {len(no_lean)} districts without a lean, e.g. {no_lean[:5]}")
        for k, s in ds.items():
            bm = s["by_mode"]
            if bm["inperson"]["now"] + bm["mail"]["now"] != s["now"]:
                fails.append(f"[{mode}] {k}: in-person + mail != overall (now)")
            if bm["inperson"]["then"] + bm["mail"]["then"] != s["then"]:
                fails.append(f"[{mode}] {k}: in-person + mail != overall (then)")

    live = districts.get("live", {})
    for k, pub in PUBLISHED.items():
        ours = live.get(k, {}).get("lean")
        ok = ours is not None and abs(ours - pub) <= TOL
        print(f"  {k:<11} published {pub:+6.1f}  ours {ours if ours is None else f'{ours:+6.1f}'}  {'ok' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"{k}: lean {ours} vs published {pub}")

    for f in sorted((WEB / "county").glob("*.json")):
        cd = json.loads(f.read_text(encoding="utf-8"))
        for k, s in cd["modes"]["demo"]["districts"].items():
            shown = sum(b["now"] for b in s["by_county"])
            if s["now"] and not 0.98 * s["now"] <= shown <= s["now"]:
                fails.append(f"{k}: counties shown cover {shown / s['now']:.1%} of the district")

    print(f"\n{sum(len(d) for d in districts.values())} district records checked")
    if fails:
        print("FAILED:\n  " + "\n  ".join(fails[:30]))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
