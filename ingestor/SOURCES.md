# Live early-vote data sources (per state)

Each ingestor writes `data/live/{state}_current.csv` (`state, county_fips, ballots`),
which the analytics prefer over the synthetic fixture. Real early voting for the
2026 general opens ~October 2026; until then the parsers run against sample files
(`ingestor/samples/`) and the dashboard shows synthetic data.

| State | Feed & format | Party of record? | Source URL | Parser |
|---|---|---|---|---|
| **NC** | Statewide absentee/one-stop file, one row per ballot (`ballot_req_type`, `ballot_rtn_status`, `voter_party_code`) | ✅ Yes | https://www.ncsbe.gov/results-data/absentee-data · files: https://dl.ncsbe.gov/?prefix=ENRS/ | `nc_absentee.py` |
| **GA** | Daily advanced-voting / absentee county counts | ❌ No | https://sos.ga.gov/page/voting-statistics · https://elections.sos.ga.gov | `county_totals.py --state GA` |
| **AZ** | Early-ballot returns by county (SoS + county recorders, esp. Maricopa) | ✅ Yes | https://azsos.gov/elections · https://recorder.maricopa.gov | `county_totals.py --state AZ` |
| **NV** | Early-vote turnout by county | ✅ Yes | https://www.nvsos.gov/sos/elections | `county_totals.py --state NV` |
| **PA** | Mail-ballot applications/returns by county | ✅ Yes | https://www.vote.pa.gov · https://www.pa.gov/agencies/dos | `county_totals.py --state PA` |

Best historical cross-reference for early-vote-by-state: **UF Election Lab** —
https://election.lab.ufl.edu (Prof. Michael McDonald).

## How to run

```bash
# 1) drop each state's downloaded raw file into data/incoming/{STATE}.csv
# 2) refresh the canonical feeds
python ingestor/run.py            # or: --demo to use ingestor/samples/
# 3) rebuild + redeploy
python web/build_dashboard.py && git commit -am "feeds" && git push
```

Notes
- NC records each voter's **registered party** (`*_party.csv` is also written) —
  a future analytics step can use it for a sharper, registration-based signal.
- GA/WI/MI have **no party registration**; those states rely on the county-lean
  method (partisan lean from prior results, weighted by where early votes come from).
- Logs: `logs/ingestor.log`.
