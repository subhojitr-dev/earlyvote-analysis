"""
ks_fetch.py — Kansas advance voting, STATEWIDE only.

The Kansas Secretary of State publishes 2026 general-election advance voting as a public Power BI
dashboard (https://www.sos.ks.gov/elections/advance-voting-data.html): one row per report date with
cumulative advance-by-mail ballots sent and returned and advance in-person votes. There is NO county
or party breakdown, so Kansas gets a statewide tab only (no county table or county-lean signal).

2022 comparison: no day-by-day 2022 series survives. Two Secretary of State reference points exist:
    12 days out  49,830 in person, 23,563 mail returned, 139,261 sent — given by the SoS to WIBW as
                 the 2022 comparison for its Oct 22 2026 figures (the 2022 date isn't stated; it is
                 treated as the same point, 12 days before Election Day = Oct 27 2022)
    4 days out   191,140 in person, 91,544 returned, 154,925 sent — SoS release of Fri Nov 4 2022
Like Ohio and Michigan, 2026 is compared at the latest 2022 point it has reached (same days out).

Outputs:
    data/ks_state/daily_2026.csv   date, sent, returned, inperson   (cumulative, per report date)
    data/ks_state/ref_2022.csv     days_out, date, sent, returned, inperson, source

Run:  python ingestor/ks_fetch.py
"""
from __future__ import annotations

import csv
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mi_fetch as pbi  # noqa: E402  (shared Power BI public-query helpers)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ks_state"
EDAY = {2022: date(2022, 11, 8), 2026: date(2026, 11, 3)}
KEY = "575810d1-1d5f-480c-8407-8a3ab8d38073"          # public resource key in the dashboard's embed URL
MODEL = 2123594
QURL = "https://wabi-us-gov-virginia-api.analysis.usgovcloudapi.net/public/reports/querydata?synchronous=true"
ENTITY = "ADVANCE VOTE COUNTS GENERAL 2026"
REF_2022 = [   # days_out, sent, returned, in person, source
    (12, 139261, 23563, 49830, "Kansas SoS figures reported by WIBW, Oct 23 2026 (2022 same-point comparison)"),
    (4, 154925, 91544, 191140, "Kansas SoS press release, Nov 4 2022"),
]


def fetch():
    pbi.KEY, pbi.MODEL, pbi.QURL = KEY, MODEL, QURL
    rows = pbi._q(ENTITY, ["DATE"], ["ADVANCE VOTING BALLOTS SENT", "ADVANCE VOTING BALLOTS RETURNED", "IN PERSON ADVANCE"])
    out = []
    for d, sent, ret, inp in rows:
        d = pbi._d(d) if isinstance(d, (int, float)) else date.fromisoformat(str(d)[:10])
        out.append((d, int(sent or 0), int(ret or 0), int(inp or 0)))
    return sorted(out)


def compare(daily):
    """Latest 2022 reference point 2026 has reached, and 2026's figures at the same days out."""
    if not daily:
        return None
    last_out = (EDAY[2026] - daily[-1][0]).days
    reached = [r for r in REF_2022 if r[0] >= last_out]
    if not reached:
        return None
    ref = min(reached, key=lambda r: r[0])
    target = EDAY[2026] - timedelta(days=ref[0])
    upto = [r for r in daily if r[0] <= target]
    if not upto:
        return None
    d26 = upto[-1]
    return {"days_out": ref[0], "d22": (EDAY[2022] - timedelta(days=ref[0])).isoformat(), "d26": d26[0].isoformat(),
            "inperson26": d26[3], "returned26": d26[2], "inperson22": ref[3], "returned22": ref[2], "source22": ref[4]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    daily = fetch()
    if not daily:
        print("KS: no 2026 rows returned (dashboard changed?) — nothing written")
        return 1
    with (OUT / "daily_2026.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "sent", "returned", "inperson"])
        w.writerows([d.isoformat(), s, r, i] for d, s, r, i in daily)
    with (OUT / "ref_2022.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["days_out", "date", "sent", "returned", "inperson", "source"])
        w.writerows([o, (EDAY[2022] - timedelta(days=o)).isoformat(), s, r, i, src] for o, s, r, i, src in REF_2022)
    d, s, r, i = daily[-1]
    print(f"KS through {d}: {i + r:,} advance ballots voted ({i:,} in person, {r:,} mail returned; {s:,} mail sent)")
    c = compare(daily)
    if c:
        print(f"  vs 2022 at {c['days_out']} days out: in person {c['inperson26']:,} ({c['d26']}) vs {c['inperson22']:,} "
              f"= {c['inperson26'] / c['inperson22']:.0%}; in person + mail {c['inperson26'] + c['returned26']:,} vs "
              f"{c['inperson22'] + c['returned22']:,} = {(c['inperson26'] + c['returned26']) / (c['inperson22'] + c['returned22']):.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
