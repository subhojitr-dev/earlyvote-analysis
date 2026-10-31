"""
tx_gender.py — estimated share of women and men among Texas early voters, statewide by day, 2026 and 2022.

Texas's early-vote rosters have no sex field, so it is ESTIMATED from first names: each voter's first
name is looked up in the Social Security Administration's baby-name counts (births 1920–2008, via the
CRAN 'babynames' package; data/reference/firstnames_gender.csv = name, share female, people), and the
shares are added up (a 'MARY' adds 0.996 women, a 'JORDAN' 0.28). Names not in the table (~3–5%) are
left out of the shares. Names are used only for the lookup and never written out.

  2026  data/incoming/tx/2026/*.csv           the daily statewide rosters (tx_fetch.py; one file per voting day)
  2022  data/incoming/tx/tx_gender_2022.json  per-day totals reduced in the browser from the old SoS site's
                                              county rosters (earlyvoting.texas-election.com → downloadVoterInfoReport.do,
                                              idTown 1–254 per day) with the same name table:
                                              {"days": {"2022-10-24": {"n": .., "f": .., "m": .., "u": ..}}}

Output (committed, counts only):
  data/tx_districts/gender_{2022,2026}.csv   days_out, group, ballots    group = Women (est.) | Men (est.) | Not matched

Run:  python ingestor/tx_gender.py
"""
from __future__ import annotations

import csv
import glob
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "data" / "reference" / "firstnames_gender.csv"
OUT = ROOT / "data" / "tx_districts"
ELECTION_DAY = {2022: date(2022, 11, 8), 2026: date(2026, 11, 3)}


def first_name(voter_name: str) -> str:
    """'GUTIERREZ, MARISA ISABEL' -> 'MARISA'."""
    rest = voter_name.split(",", 1)[1] if "," in voter_name else voter_name
    parts = rest.replace(".", " ").split()
    return parts[0].upper() if parts else ""


def tally_file(path: str, pf: dict) -> dict:
    """One roster -> {"n", "f", "m", "u"}; cached next to it (.gender_*.json, counts only)."""
    p = Path(path)
    cache = p.with_name(".gender_" + p.stem + ".json")
    if cache.exists() and cache.stat().st_mtime >= p.stat().st_mtime:
        return json.loads(cache.read_text())
    t = {"n": 0, "f": 0.0, "m": 0.0, "u": 0}
    with p.open(encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            t["n"] += 1
            q = pf.get(first_name(r.get("VOTER_NAME", "")))
            if q is None:
                t["u"] += 1
            else:
                t["f"] += q
                t["m"] += 1 - q
    cache.write_text(json.dumps(t))
    return t


def write(year: int, days: dict):
    with (OUT / f"gender_{year}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["days_out", "group", "ballots"])
        for d, t in sorted(days.items()):
            out = (ELECTION_DAY[year] - date.fromisoformat(d)).days
            w.writerow([out, "Women (est.)", round(t["f"], 1)])
            w.writerow([out, "Men (est.)", round(t["m"], 1)])
            w.writerow([out, "Not matched", t["u"]])
    n, u = sum(t["n"] for t in days.values()), sum(t["u"] for t in days.values())
    f = sum(t["f"] for t in days.values())
    print(f"{year}: {n:,} voters over {len(days)} days; women {f / (n - u):.1%} of matched; {u / n:.1%} not matched")


def main():
    pf = {r["name"]: float(r["p_female"]) for r in csv.DictReader(TABLE.open(encoding="utf-8"))}
    days26 = {}
    for f in sorted(glob.glob(str(ROOT / "data" / "incoming" / "tx" / "2026" / "*.csv"))):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(f).name)
        if m:
            days26[m.group(1)] = tally_file(f, pf)
    if days26:
        write(2026, days26)
    j22 = ROOT / "data" / "incoming" / "tx" / "tx_gender_2022.json"
    if j22.exists():
        write(2022, json.loads(j22.read_text())["days"])
    elif not (OUT / "gender_2022.csv").exists():
        print("no 2022 totals yet (data/incoming/tx/tx_gender_2022.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
