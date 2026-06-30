"""
evote_signal.py — turn live early-vote-by-county counts into a partisan signal.

INPUT  (live, this cycle): early ballots cast SO FAR, per county.
        Schema: state, county_fips, ballots[, dem_reg, rep_reg]  (reg optional;
        only NC/NV/AZ/PA publish party-of-record, GA/WI/MI do not).
BASELINE (data/baseline/county_lean.csv): each county's Dem two-party lean and
        its normal early-vote volume.

The county-lean method (works in ALL states, registration or not):
  • Composite early-electorate lean =
        sum( ballots_c * lean_dem_c ) / sum( ballots_c )
    i.e. the Dem two-party lean of the *places* voting early so far.
  • Baseline composite lean = same formula but weighted by each county's
    historical early volume — "what the early electorate normally looks like".
  • SIGNAL = composite_now - composite_baseline, in two-party share points.
        > 0  => early electorate tilting MORE Dem than usual  (good for D)
        < 0  => tilting MORE Rep than usual                   (good for R)
  • Per-county PACE = ballots_now / baseline_early_volume (scaled), flags which
    counties are over/under-performing — the "where to act" layer for campaigns.

This is deliberately a composition signal, not a vote-count prediction: nobody
reports who you voted for during early voting. It answers "is the early
electorate shaped more favorably for D or R than the baseline?"
"""
from __future__ import annotations

import csv
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data" / "baseline"


def load_baseline():
    out = {}
    with (BASE / "county_lean.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not r["lean_dem"]:
                continue
            out[(r["state"], r["county_fips"])] = {
                "county_name": r["county_name"],
                "lean_dem": float(r["lean_dem"]),
                "baseline_early": int(r["early_inperson"]) + int(r["early_mail"]),
            }
    return out


def compute(live_rows, state: str):
    """live_rows: iterable of dicts {county_fips, ballots}. Returns a report."""
    base = load_baseline()
    counties = []
    now_num = now_den = base_num = base_den = 0.0
    for r in live_rows:
        key = (state, r["county_fips"])
        b = base.get(key)
        if not b:
            continue
        ballots = float(r["ballots"])
        lean = b["lean_dem"]
        now_num += ballots * lean
        now_den += ballots
        base_num += b["baseline_early"] * lean
        base_den += b["baseline_early"]
        pace = ballots / b["baseline_early"] if b["baseline_early"] else None
        counties.append({
            "county_fips": r["county_fips"], "county_name": b["county_name"],
            "lean_dem": lean, "ballots": int(ballots),
            "baseline_early": b["baseline_early"],
            "pace": round(pace, 3) if pace else None,
        })
    composite_now = now_num / now_den if now_den else None
    composite_base = base_num / base_den if base_den else None
    signal = (composite_now - composite_base) if (composite_now and composite_base) else None
    # Per-county contribution to the signal (additive decomposition that sums to
    # `signal`): a county pushes the signal by how OVER/UNDER-represented it is in
    # the early electorate now vs its baseline share, times its lean gap. Positive
    # => pushing D; negative => pushing R. Using shares (not raw pace) removes the
    # "everyone is at 45% so far" artifact.
    for c in counties:
        share_now = c["ballots"] / now_den if now_den else 0
        share_base = c["baseline_early"] / base_den if base_den else 0
        c["pull"] = round((share_now - share_base) * (c["lean_dem"] - (composite_base or 0.5)), 5)
    counties.sort(key=lambda c: -c["pull"])
    return {
        "state": state,
        "composite_now": composite_now,
        "composite_baseline": composite_base,
        "signal_pts": signal,                 # two-party share points
        "direction": ("D" if signal and signal > 0 else "R" if signal else "—"),
        "n_counties": len(counties),
        "total_ballots": int(now_den),
        "counties": counties,
    }


def _fmt(rep):
    print(f"\n=== {rep['state']} early-vote signal ===")
    print(f"  ballots in: {rep['total_ballots']:,} across {rep['n_counties']} counties")
    print(f"  early-electorate lean now : {rep['composite_now']:.2%} Dem")
    print(f"  baseline early lean       : {rep['composite_baseline']:.2%} Dem")
    s = rep["signal_pts"] * 100
    print(f"  SIGNAL: {s:+.2f} pts  ->  tilting toward {rep['direction']}")
    print("\n  counties pulling hardest:")
    for c in rep["counties"][:3] + rep["counties"][-3:]:
        print(f"    {c['county_name']:<14} lean {c['lean_dem']:.0%}  "
              f"pace {c['pace']:>5}x  pull {c['pull']:+.4f}")


if __name__ == "__main__":
    # demo on the synthetic fixture (data/fixtures/nc_current.csv)
    import sys
    state = sys.argv[1] if len(sys.argv) > 1 else "NC"
    fx = BASE.parent / "fixtures" / f"{state.lower()}_current.csv"
    rows = list(csv.DictReader(fx.open(encoding="utf-8")))
    _fmt(compute(rows, state))
