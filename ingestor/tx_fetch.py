"""
tx_fetch.py — Texas 2026 early vote, fetched automatically from the Secretary of State.

The SoS early-voting site (goelect.txelections.civixapps.com/ivis-evr-ui/evr) is an
Angular app over a public JSON API; this script calls the same endpoints the page
does, so no manual download is needed:
    getFile?type=EVR_ELECTION                         elections + their early-voting dates
    getFile?type=EVR_EARLYVOTING&electionId&electionDate
                                                      per county: registered voters,
                                                      cumulative in-person and mail voters
    getFile?type=EVR_STATEWIDE&electionId&electionDate
                                                      the statewide roster ("Generate
                                                      Statewide Report"): one row per
                                                      voter, CUMULATIVE through that date
Payloads are base64 in an {"upload": ...} wrapper.

Writes
    data/tx_county/turnout_{date}.csv    county, registered, inperson, mail  (cumulative; committed)
    data/live/tx_current.csv + tx_meta.json  latest county IN-PERSON totals for the main dashboard
                                         (mail is left out: the new site's mail counts lag badly by
                                         county — on Oct 15 only 85 of 254 counties had any)
    data/incoming/tx/2026/STATEWIDE...EarlyVoting.{date}.csv   rosters (names — gitignored,
                                         read only by tx_districts.py, which writes counts)

Run:  python ingestor/tx_fetch.py          (fetches every posted day not already on disk)
"""
from __future__ import annotations

import base64
import csv
import json
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

import shapefile  # pyshp

ROOT = Path(__file__).resolve().parent.parent
API = "https://goelect.txelections.civixapps.com/api-ivis-system/api/v1/getFile"
ELECTION = "2026 NOVEMBER GENERAL ELECTION"
COUNTY_OUT = ROOT / "data" / "tx_county"
LIVE = ROOT / "data" / "live"
ROSTERS = ROOT / "data" / "incoming" / "tx" / "2026"


def get(params: str):
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": "Mozilla/5.0 (earlyvote-analysis)"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read())
    return base64.b64decode(d["upload"]) if d.get("upload") else None


def election():
    els = json.loads(get("type=EVR_ELECTION"))["elections"]
    e = next(e for e in els if e["election_name"].strip().upper() == ELECTION)
    days = [datetime.strptime(x["date"], "%m/%d/%Y").date() for x in e["early_voting_dates"]]
    return e["id"], sorted(d for d in days if d < date.today())     # a day's numbers post the next morning


def fips_by_name():
    r = shapefile.Reader(str(ROOT / "data" / "raw" / "geo" / "cb_2024_us_county_500k" / "cb_2024_us_county_500k"))
    return {rec["NAME"].upper().replace(" ", ""): rec["GEOID"] for rec in r.records() if rec["STATEFP"] == "48"}


def main():
    eid, days = election()
    COUNTY_OUT.mkdir(parents=True, exist_ok=True)
    ROSTERS.mkdir(parents=True, exist_ok=True)
    latest = None
    for d in days:
        iso, mdy = d.isoformat(), d.strftime("%m/%d/%Y")
        out = COUNTY_OUT / f"turnout_{iso}.csv"
        if not out.exists():
            raw = get(f"type=EVR_EARLYVOTING&electionId={eid}&electionDate={mdy}")
            rows = json.loads(raw)["turnout_by_county"] if raw else []
            if not rows:
                print(f"{iso}: county turnout not posted yet")
                continue
            with out.open("w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["county", "registered", "inperson", "mail"])
                w.writerows(sorted((r["name"].strip().upper(), r["registered_voters"],
                                    r["total_in_person_votes_for_election"], r["total_mail_votes_for_election"])
                                   for r in rows))
        latest = (iso, out)
        roster = ROSTERS / f"STATEWIDE.{ELECTION}.EarlyVoting.{iso}.csv"
        if not roster.exists():
            raw = get(f"type=EVR_STATEWIDE&electionId={eid}&electionDate={mdy}")
            if raw:
                roster.write_bytes(raw)
                print(f"{iso}: roster {raw.count(b'\n') - 1:,} voters")
            else:
                print(f"{iso}: roster not posted yet")
    if not latest:
        raise SystemExit("no county turnout posted yet")

    iso, path = latest
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    fips = fips_by_name()
    missing = [r["county"] for r in rows if r["county"].replace(" ", "") not in fips]
    if missing:
        raise SystemExit(f"no FIPS for {missing}")
    LIVE.mkdir(parents=True, exist_ok=True)
    with (LIVE / "tx_current.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["state", "county_fips", "ballots"])
        w.writerows(sorted(("TX", fips[r["county"].replace(" ", "")], int(r["inperson"])) for r in rows))
    ip, ml = sum(int(r["inperson"]) for r in rows), sum(int(r["mail"]) for r in rows)
    (LIVE / "tx_meta.json").write_text(json.dumps({"as_of": iso, "ballots": ip, "inperson": ip, "mail": ml,
                                                   "mail_counties": sum(int(r["mail"]) > 0 for r in rows),
                                                   "counties": len(rows), "basis": "in-person only",
                                                   "source": "Texas Secretary of State early-voting turnout"}, indent=1))
    reg_p = ROOT / "data" / "reference" / "registration.csv"     # TX registered voters, from the same feed
    keep = [r for r in csv.DictReader(reg_p.open(encoding="utf-8")) if r["state"] != "TX"]
    keep += [{"state": "TX", "county_fips": fips[r["county"].replace(" ", "")], "county_name": r["county"],
              "registered": r["registered"]} for r in rows]
    with reg_p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["state", "county_fips", "county_name", "registered"])
        w.writeheader()
        w.writerows(keep)
    print(f"TX through {iso}: {ip + ml:,} early voters ({ip:,} in person, {ml:,} mail) in {len(rows)} counties")


if __name__ == "__main__":
    sys.exit(main())
