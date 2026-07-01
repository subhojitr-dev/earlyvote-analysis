# Architecture

How the early-vote analysis works, end to end — functional flow, the signal math, the
data model, and the technical layout.

---

## 1. Functional architecture (data flow)

```
  MEDSL precinct returns              State early-vote feeds            SoS registration
  (2020 Pres, 2022 Sen, 2024 Pres)    (NC/GA/AZ/NV/PA, live ~Oct)       (real or estimated)
        │                                     │                               │
        ▼                                     ▼                               ▼
  build_baseline.py                     ingestor/run.py                 build_registration.py
  → data/baseline/county_results.csv    → data/live/{st}_current.csv    → data/reference/
        │                                     │   (else synthetic            registration.csv
        ▼                                     │    data/fixtures/)                │
  county_lean.py                              │                                  │
  → data/baseline/county_lean.csv             │                                  │
        │                                     │                                  │
        └──────────────┬──────────────────────┴──────────────────────────────────┘
                       ▼
              analytics/turnout_compare.py  (+ performance_matrix.py)
              compare · group_deviation · composite_lean · turnout_progress · turnout_rate
                       │
                       ▼
              web/build_dashboard.py  → web/index.html  (self-contained static)
                       │
                       ▼
              Vercel (static host, auto-deploy on push)  →  earlyvote-analysis.vercel.app
```

Three inputs (historical results, live early-vote feeds, registration) converge in one
analytics layer, which a generator bakes into a single static HTML file that Vercel serves.

## 2. The signal math (what each metric means)

All partisan metrics use **share of the vote** (a normalized %), never raw counts, so they
are immune to two confounds: the midterm-vs-presidential turnout gap, and early voting being
only partway done.

- **County partisan lean** (`county_lean.py`) — Dem two-party share of a county's total vote,
  blended across baseline cycles. Fixed input; the "color" of each county.
- **Partisan shift** (`compare`) — `share_now(county) / share_in_year(county) − 1`. Positive
  (green) = the county is a bigger slice of the early electorate than that year.
- **Group deviation** (`group_deviation`) — the same, aggregated over Dem-leaning vs
  Rep-leaning counties (lean ≥ 0.5 vs < 0.5). The **net** (Dem-group − Rep-group) is the
  headline partisan turnout edge.
- **Composite Dem tilt** (`composite_lean`) — `Σ county_share × county_lean` per year. Since
  lean is fixed, year-to-year change comes purely from *where* the early votes concentrate:
  a higher number = early voters from more-Democratic places. Comparing 2026 to 2020/2022/2024
  shows whether the current tilt erases prior slippage.
- **Turnout progress** (`turnout_progress`) — `early_2026 / total_turnout(prior year)`, per
  county and aggregate. A volume ratio: >100% means early votes alone already exceeded that
  whole past election.
- **Turnout rate** (`turnout_rate`) — `early_2026 / registered_voters`. A *true* rate: what
  share of the electorate has voted early so far.

### Data-hygiene rules baked into the pipeline
- **TOTAL vs modes** — some state/years report only a `TOTAL` row, others per-mode rows. Code
  uses the TOTAL row if present, else the sum of modes — never both (mixing double-counts).
- **GA duplicates removed** — GA 2020 had two Senate races and GA 2022 a December runoff; the
  baseline switched to the 2020/2024 **President** files and filters `stage=RUNOFF` /
  `special=TRUE` so no GA voter is counted twice.
- **Mode-label drift normalized** — NC `ONE STOP`↔`EARLY VOTING`, GA `ADVANCED`/`ADVANCED
  VOTING`, AZ `EARLY`/`LATE EARLY`/`LATE VOTES` all map to the same buckets.
- **Totals-only states** — NV/PA report only totals (no early split); they fall back to
  total-vote share, and `make_fixture` scales off total turnout so they still populate.

## 3. Live-feed design

`load_current(state)` prefers `data/live/{state}_current.csv` (written by the ingestors) and
falls back to `data/fixtures/{state}_current.csv` (synthetic). So flipping from demo to live
is just a matter of the ingestors producing files — no code change downstream.

- `ingestor/nc_absentee.py` — NC's per-ballot absentee/one-stop file → county counts **+ party
  of record** (`*_party.csv`, for a future registration-based signal).
- `ingestor/county_totals.py` — generic county-count parser for GA/AZ/NV/PA.
- `ingestor/run.py` — orchestrator: reads `data/incoming/{STATE}.csv`, dispatches to the right
  parser, logs to `logs/ingestor.log`. States with no incoming file keep their fixture.

## 4. Technical stack & choices

| Layer | Tech | Why |
|---|---|---|
| Analytics | **Python 3, stdlib only** (`csv`, `collections`) | zero-dependency, portable, trivially auditable |
| Data format | flat **CSV** | diffable, inspectable in Excel, no DB to operate |
| Dashboard | **single static HTML** (vanilla JS, data baked in) | no backend, no build step; deploys anywhere, works from `file://` |
| Hosting | **Vercel** static (`outputDirectory: web`) | auto-deploy on push; free tier is plenty |
| Ingestors | Python + `requests` (optional) | tolerant column detection; file- or URL-driven |

Deliberately **no database and no API server** (unlike the sibling `election-forecast`,
which needs live FastAPI + WebSockets for election-night streaming). Early-vote data updates
daily at most, and the county-level dataset is tiny (~360 rows), so a rebuild-and-redeploy
pipeline is simpler and cheaper than a running service.

## 5. Extending it

- **New state** — add it to `STATES` in `build_baseline.py` (+ `web/build_dashboard.py`),
  ensure its mode labels are in the `EARLY` sets, rebuild. Add a feed to `ingestor/SOURCES.md`.
- **New baseline year** — add the MEDSL file to `SOURCES` in `build_baseline.py`.
- **Registration-based signal** (NC/NV/AZ/PA) — consume the ingestors' `*_party.csv` to weight
  by registered party instead of (or alongside) county lean.
- **Real registration** — drop `data/reference/registration_real.csv`; `build_registration.py`
  uses it automatically over the estimate.
