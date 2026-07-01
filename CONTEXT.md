# CONTEXT.md — START HERE EACH SESSION
# Early-Vote Analysis — partisan early-voting signal by state & county
# Last updated: 2026-07-01 (DEPLOYED — 5 states, ingestors, turnout rate, full docs)

> Sibling to the **election-forecast** project. That one forecasts election-NIGHT
> results; THIS one reads the EARLY-VOTE signal in the weeks before.
> LIVE: https://earlyvote-analysis.vercel.app  ·  Repo: github.com/subhojitr-dev/earlyvote-analysis

---

## 🎯 WHAT THIS IS
For each swing state, by county: **is the early electorate tilting more D or more R
than a comparable past cycle?** Statewide signal + county drill-down + turnout progress.
Read the four docs: Overview.md (what/why/who), Architecture.md (how), DASHBOARD.md
(how to read), README.md (run/deploy).

## 🚦 WHERE WE ARE (2026-07-01)
- **DEPLOYED & public** on Vercel (static, auto-deploys on push to `main`).
- **5 states live: GA, NC, AZ, NV, PA** (358 counties). WI/MI next.
- **Baseline: 2020 President + 2022 Senate + 2024 President** (all via MEDSL). GA
  double-count bugs fixed (2020 two Senate races, 2022 runoff). NV/PA are totals-only.
- **County-lean method** for partisanship; registration split is the next sharpening
  (NC ingestor already captures party of record in *_party.csv).
- **Live-ingestor framework built** (ingestor/): NC per-ballot parser (tested), generic
  county-totals for GA/AZ/NV/PA, orchestrator, SOURCES.md. Flips on ~Oct 2026; analytics
  prefer data/live/ over the synthetic fixture automatically.
- **Turnout rate** added (early / registered voters; estimate now, real SoS files swappable).

## ✅ DONE — analytics core (runnable NOW, validated)
  data/baseline/county_results.csv  — NC+GA county×party×mode, from MEDSL precinct files
  data/baseline/county_lean.csv     — per-county Dem two-party lean + early-vote share
  analytics/build_baseline.py       — extract NC/GA from the big nationwide files
  analytics/county_lean.py          — lean + early-mix baseline (mode labels normalized;
                                      GA "TOTAL" double-count dropped)
  analytics/performance_matrix.py   — HEADLINE: one-screen matrix per state —
                                      [1] overall turnout volume vs 2020/2022/2024,
                                      [2] Dem-leaning vs Rep-leaning aggregation (%
                                      over/under share + net D-vs-R pts), [3] full
                                      per-county matrix. Built on 2020+2022+2024.
  analytics/turnout_compare.py      — per-county + group helpers (used by the matrix)
                                      2026 early-vote SHARE vs 2020/2022/2024, over/
                                      under-performing %, Dem strongholds flagged +
                                      a plain-English "read". Uses SHARE (not raw
                                      counts) to cancel the midterm-vs-presidential
                                      gap and mid-stream incompleteness.
  analytics/evote_signal.py         — secondary: composite early-electorate lean vs
                                      baseline → signal in two-party pts + per-county
                                      additive "pull" (sums to the headline; verified)
  analytics/make_fixture.py         — synthetic "voting in progress" snapshot so the
                                      pipeline runs before real Oct-2026 feeds exist

  Validation: NC 48.7% / GA 49.3% statewide Dem two-party (correct); Durham 81% D,
  Orange 75% D (Triangle); GA top D-pullers DeKalb/Fulton/Clayton (correct).

## 🔴 NEXT SESSION — START HERE
  1. **Live ingestors** (ingestor/nc_absentee.py, ingestor/ga_evote.py) — pull the
     daily county early-vote files. NC: dl.ncsbe.gov ENRS absentee files (one row per
     early/absentee ballot; has county + registered party). GA: SOS / county feeds.
     NO live early voting until ~Oct 2026, so build the PARSER against last cycle's
     posted files and replay them; the fixture proves the downstream already works.
  2. **2022 baseline** — add NC-2022-SENATE + GA-2022 precinct files to build_baseline
     SOURCES (best midterm comparator). Get from MEDSL/Dataverse or state results.
  3. **API** (api/main.py, FastAPI like election-forecast) — endpoints: /api/states,
     /api/state/{st} (signal + counties), serving evote_signal.compute() output.
  4. **UI** (ui/, React+Vite) — state list w/ signal chips → county table (lean, pace,
     pull, up/down). Reuse election-forecast/ui components.
  5. Then deploy (Vercel + Render), then add NV/AZ/PA, then WI/MI.

## ⚠️ DATA-HYGIENE GOTCHAS (don't re-discover these)
  - GA precinct files emit a **"TOTAL"** mode row — drop it or you double-count.
  - Early-vote label drifts: NC "ONE STOP" (2020) = "EARLY VOTING" (2024); GA
    "ADVANCED VOTING". Normalized in county_lean.bucket().
  - Secret ballot: you NEVER get who-they-voted-for early. The signal is about the
    COMPOSITION of the early electorate (lean-weighted), not a vote prediction.
  - WI & MI & GA have NO party registration → county-lean is the only universal method.
  - **GA 2024 in MEDSL is TOTALS-ONLY** (no early/election-day split); only GA 2020 has
    the mode breakdown. NC has it for BOTH 2020 & 2024. turnout_compare falls back to
    total-vote share for totals-only years. For real GA early-vote-by-county history,
    pull GA SOS daily files / UF Election Lab — not MEDSL.
  - **2022 is missing** and is the IDEAL midterm comparator for 2026 — top data TODO.
  - Compare SHARE of the vote, never raw counts across cycle types (midterm vs prez).

## ▶️ RUN IT
  python analytics/build_baseline.py      # one-time, needs election-forecast/data/raw
  python analytics/county_lean.py
  python analytics/make_fixture.py GA && python analytics/performance_matrix.py GA  # headline
  python analytics/make_fixture.py NC && python analytics/performance_matrix.py NC
  python analytics/turnout_compare.py GA   # per-county + group detail
  python analytics/evote_signal.py GA      # secondary lean-composite view
