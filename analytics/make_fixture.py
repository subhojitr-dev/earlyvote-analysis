"""
make_fixture.py — fabricate a plausible "early voting in progress" snapshot per
county, so the pipeline runs end-to-end before real Oct-2026 feeds exist.

It takes each county's historical early volume, scales to a mid-early-voting
point (~45% of normal early turnout), and injects a deliberate scenario:
Dem-leaning counties slightly OVER-perform, Rep-leaning slightly under — so the
demo produces a clear, interpretable +D signal you can eyeball.

Run:  python analytics/make_fixture.py NC
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"


def make(state: str, frac=0.45, seed=7):
    random.seed(seed)
    src = csv.DictReader((BASE / "baseline" / "county_lean.csv").open(encoding="utf-8"))
    out = []
    for r in src:
        if r["state"] != state or not r["lean_dem"]:
            continue
        base_early = int(r["early_inperson"]) + int(r["early_mail"])
        lean = float(r["lean_dem"])
        # scenario: +/-12pts of pace tied to lean, plus noise
        tilt = (lean - 0.5) * 0.24
        pace = frac * (1 + tilt) * random.uniform(0.92, 1.08)
        out.append({"state": state, "county_fips": r["county_fips"],
                    "ballots": max(0, round(base_early * pace))})
    dst = BASE / "fixtures" / f"{state.lower()}_current.csv"
    with dst.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["state", "county_fips", "ballots"])
        w.writeheader(); w.writerows(out)
    print(f"  wrote {len(out)} counties -> {dst}")


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "NC")
