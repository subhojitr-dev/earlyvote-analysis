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

## 6. Source data — origin, local storage, retrieval & injection

### 6a. Historical baseline (partisan lean + past turnout)
The partisan lean and historical turnout come from **MIT Election Data & Science Lab (MEDSL)**
precinct-level returns, published on **Harvard Dataverse**. The raw nationwide CSVs are large
(~0.9 GB total) and are **shared with the sibling `election-forecast` project**, so they live
there and are gitignored — this repo reads them once to produce the tiny committed baseline.

| File | Year / office | Size | Harvard Dataverse DOI |
|---|---|---|---|
| `PRESIDENT_precinct_general.csv` | 2020 President (national precinct) | ~358 MB | `doi:10.7910/DVN/JXPREB` |
| `2022-SENATE-precinct-general.csv` | 2022 Senate | ~140 MB | `doi:10.7910/DVN/IAD3XR` |
| `2024-PRESIDENT-precinct-general.csv` | 2024 President | ~399 MB | `doi:10.7910/DVN/XDJYKC` |

- **Stored locally at:** `C:\Users\subho\election-forecast\data\raw\`
  (override with the `MEDSL_SRC` env var; that path is the default in `build_baseline.py`).
- **Retrieval URL / mechanism:** each dataset page is
  `https://dataverse.harvard.edu/dataset.xhtml?persistentId=<doi>`. Programmatic download:
  ```bash
  # 1) find the datafile id inside the dataset
  curl -s "https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=doi:10.7910/DVN/IAD3XR"
  # 2) download the original CSV by that id
  curl -L -o 2022-SENATE-precinct-general.csv \
    "https://dataverse.harvard.edu/api/access/datafile/13996913?format=original"
  ```
- **Injection into the app:** `analytics/build_baseline.py` streams these files, filters to
  `state_po ∈ {NC,GA,NV,AZ,PA}`, removes GA duplicate contests (`stage=RUNOFF`, `special=TRUE`),
  and aggregates to `(year, office, state, county_fips, county_name, party, mode) → votes`,
  writing the compact **`data/baseline/county_results.csv`** (committed). `analytics/county_lean.py`
  then derives per-county lean + early mix into **`data/baseline/county_lean.csv`**.

### 6b. Live early-vote feeds (current cycle, activates ~Oct 2026)
Each state's election office publishes its own early-vote file. Full table of URLs and formats
is in **`ingestor/SOURCES.md`**; summary:

| State | Retrieval URL | Parser |
|---|---|---|
| NC | https://dl.ncsbe.gov/?prefix=ENRS/ (absentee/one-stop, per ballot) | `ingestor/nc_absentee.py` |
| GA | https://sos.ga.gov/page/voting-statistics | `ingestor/county_totals.py --state GA` |
| AZ | https://azsos.gov/elections · Maricopa recorder | `ingestor/county_totals.py --state AZ` |
| NV | https://www.nvsos.gov/sos/elections | `ingestor/county_totals.py --state NV` |
| PA | https://www.vote.pa.gov | `ingestor/county_totals.py --state PA` |

- **Retrieval & injection mechanism:** download each state's raw file into
  `data/incoming/{STATE}.csv` → run `python ingestor/run.py` → each parser aggregates to county
  and writes **`data/live/{state}_current.csv`** (`state, county_fips, ballots`). The analytics
  layer (`turnout_compare.load_current`) automatically **prefers `data/live/` over the synthetic
  `data/fixtures/`**, so live data flows through with no code change. Logs → `logs/ingestor.log`.

### 6c. Registered-voter denominators
`analytics/build_registration.py` writes **`data/reference/registration.csv`**. Default is an
**estimate** (2024 county turnout ÷ 0.72); to use real numbers, drop each state's
Secretary-of-State registration-by-county file into `data/reference/registration_real.csv`
(same columns) and it is used verbatim.

## 7. Directory & file map

```
earlyvote-analysis/
├── analytics/                 signal math + baseline builders (Python, stdlib only)
│   ├── build_baseline.py      reads the big MEDSL files → data/baseline/county_results.csv
│   ├── county_lean.py         county Dem lean + early mix + total votes → county_lean.csv
│   ├── build_registration.py  registered-voter denominators → data/reference/registration.csv
│   ├── make_fixture.py        synthetic "2026 in progress" per state → data/fixtures/
│   ├── turnout_compare.py     core engine: compare / group_deviation / composite_lean /
│   │                          turnout_progress / turnout_rate / load_current (live-pref)
│   ├── performance_matrix.py  one-screen terminal report (overall + groups + county matrix)
│   ├── evote_signal.py        earlier lean-composite "pull" signal (secondary/reference)
│   └── __init__.py
├── ingestor/                  live state feed parsers (Python)
│   ├── common.py              shared: county→FIPS map, write_live(), logging to logs/
│   ├── nc_absentee.py         NC per-ballot parser (accepted early/mail, + party of record)
│   ├── county_totals.py       generic county-count parser (GA/AZ/NV/PA)
│   ├── run.py                 orchestrator: data/incoming/ → parsers → data/live/
│   ├── SOURCES.md             per-state feed URLs, formats, run instructions
│   ├── samples/               tiny realistic sample feeds for testing (nc_*, az_*)
│   └── __init__.py
├── web/                       dashboard (Python generator → static HTML + JS)
│   ├── build_dashboard.py     builds state data + bakes it into web/index.html
│   ├── index.html             the deployed dashboard (self-contained; vanilla JS)
│   └── serve.py               tiny static server for local dev (binds $PORT)
├── data/
│   ├── baseline/              county_results.csv, county_lean.csv   (committed, small)
│   ├── fixtures/              {state}_current.csv synthetic 2026    (committed)
│   ├── reference/             registration.csv                      (committed)
│   ├── live/                  {state}_current.csv real feed output  (gitignored)
│   └── incoming/              raw per-state drop-ins                (gitignored)
├── logs/                      ingestor.log                          (gitignored)
├── Overview.md README.md Architecture.md DASHBOARD.md CONTEXT.md    docs
├── vercel.json                Vercel static config (outputDirectory: web)
├── .claude/launch.json        Claude Code preview-server config
└── requirements.txt           optional extras (fastapi/uvicorn/requests)
```

### Source-file descriptions

**Python — analytics/**
- `build_baseline.py` — extracts the 5 swing states from the nationwide MEDSL files, dedups GA
  contests, aggregates to county×party×mode; the only step that needs the big source files.
- `county_lean.py` — per-county Dem two-party lean + early-vote mix + blended total, with
  order-independent TOTAL-vs-modes dedup (totals-only safe for NV/PA).
- `build_registration.py` — registered-voter denominators (real file if present, else estimate).
- `make_fixture.py` — generates plausible synthetic "2026 early voting in progress" per state.
- `turnout_compare.py` — the heart: share-based per-county comparison, blue/red group deviation,
  composite Dem tilt, turnout progress, turnout rate, and the live-preferring `load_current`.
- `performance_matrix.py` — assembles the terminal "performance matrix" report per state.
- `evote_signal.py` — the original lean-weighted composite signal with additive per-county pull
  (kept as a secondary/validation view).

**Python — ingestor/**
- `common.py` — county-name→FIPS mapping from the baseline, the `write_live()` feed writer, and
  the shared logger (`logs/ingestor.log`).
- `nc_absentee.py` — parses NC's per-ballot absentee/one-stop file; counts accepted early/mail
  ballots by county and by registered party; tolerant to column-name drift across cycles.
- `county_totals.py` — generic parser for states that publish county-level early-vote counts;
  auto-detects the county and count columns.
- `run.py` — the orchestrator that turns `data/incoming/` drop-ins into `data/live/` feeds.

**Python — web/**
- `build_dashboard.py` — pulls every metric from the analytics layer, serializes it to JSON, and
  bakes it into a single self-contained `index.html`; also emits a widget partial.
- `serve.py` — minimal static file server for local viewing (`$PORT` or 8123).

**JavaScript — inside `web/index.html`** (generated, not a separate file)
- Vanilla JS embedded in the page: renders the state tabs, summary cards, the two aggregate
  panels (Dem-tilt trajectory + turnout-progress bars), and the sortable/filterable county table
  with the Partisan-shift ↔ Turnout-progress view toggle and conditional cell coloring. No
  framework, no build step, no external calls — all data is baked into the page as a JS object.
