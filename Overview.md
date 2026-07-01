# Overview — Early-Vote Analysis

**Live dashboard:** https://earlyvote-analysis.vercel.app
**Source:** https://github.com/subhojitr-dev/earlyvote-analysis

---

## What this application does

It reads the **partisan early-voting signal** in U.S. swing states — county by county —
during the weeks before an election, and shows whether the early electorate is tilting
more Democratic or more Republican than in comparable past cycles (2020, 2022, 2024).

Because the ballot is secret, we never see *who* someone voted for during early voting.
Instead the app measures the **composition** of the early electorate: it weights each
county's early-vote volume by that county's historical partisan lean, so you can read
whether the people voting early are coming disproportionately from Democratic-leaning or
Republican-leaning places. It answers three questions at a glance:

1. **Partisan shift** — is each county a bigger or smaller slice of the early vote than in
   2020 / 2022 / 2024? (Dem-leaning counties over-voting + Rep-leaning under-voting = a
   Democratic turnout edge, and vice-versa.)
2. **Aggregate Dem tilt** — combining all counties, is the early electorate more
   Democratic-tilted than past cycles, and does this year erase prior slippage?
3. **Turnout progress** — how far along is early voting, both as a % of each county's full
   prior turnout and as a true % of registered voters.

## Purpose

Give campaigns, analysts, and journalists an **early, actionable read** on turnout so they
can act *before* election day — e.g. spot a Democratic stronghold that is under-performing
its baseline (Chatham/Savannah lagging while Fulton/DeKalb surge) and redirect
get-out-the-vote effort to where it moves the needle.

## Who can use it

- **Campaign / party operations** — where to concentrate GOTV in the final days.
- **Analysts & forecasters** — a leading indicator to complement election-night models
  (this is the sibling of the author's `election-forecast` project).
- **Journalists & the civically curious** — an interpretable, transparent turnout tracker.

It is a **turnout-composition tool, not a vote-prediction tool**: it tells you *where*
early voters are coming from, not *who* they voted for.

## States covered (v1)

| State | Party registration? | Early-vote breakdown in baseline |
|---|---|---|
| North Carolina | ✅ | full (in-person early + mail) |
| Georgia | ❌ (county-lean) | full |
| Arizona | ✅ | full (incl. late-early) |
| Nevada | ✅ | totals-only (uses total-vote share) |
| Pennsylvania | ✅ | totals-only (mail-heavy) |

Roadmap: WI/MI next; registration-based sharpening for NC/NV/AZ/PA.

## Data sources

- **Partisan lean & historical turnout** — MIT Election Data & Science Lab (MEDSL)
  precinct returns via Harvard Dataverse: 2020 President, **2022 Senate**
  (`doi:10.7910/DVN/IAD3XR`), 2024 President.
- **Live early-vote feeds** (activate ~Oct 2026) — each state's election office; see
  `ingestor/SOURCES.md` for exact URLs and formats (NC `dl.ncsbe.gov`, GA `sos.ga.gov`,
  AZ `azsos.gov` + Maricopa recorder, NV `nvsos.gov`, PA `vote.pa.gov`).
- **Registered-voter denominators** — estimated from 2024 turnout now; swappable for real
  Secretary-of-State registration files (`data/reference/registration_real.csv`).

## Important caveat

Until real early voting opens (~**October 2026**), the 2026 numbers are **synthetic
stand-ins** generated from the historical baseline. The analytical engine, the historical
baselines, and the live-ingestor parsers are all real and tested; only the current-cycle
values are placeholders until the state feeds go live — at which point the ingestors drop
real data into `data/live/` and the whole dashboard updates on the next build + push.

See `README.md` (run it), `Architecture.md` (how it works), and `DASHBOARD.md` (how to
read the dashboard).
