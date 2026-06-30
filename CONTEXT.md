# CONTEXT.md — START HERE EACH SESSION
# Early-Vote Analysis — partisan early-voting signal by state & county
# Last updated: 2026-06-30 (kickoff — analytics core built & validated)

> Sibling to the **election-forecast** project (same ETL→analytics→API→React→deploy
> shape). That one forecasts election-NIGHT results; THIS one reads the EARLY-VOTE
> signal in the weeks before, so campaigns can act proactively.

---

## 🎯 WHAT THIS IS
For each swing state, by county: **is the early electorate tilting more D or more R
than a comparable past cycle?** Roll up to a statewide signal; drill down to the
counties driving it ("where to act"). Deploy as a web dashboard (by state → county,
how much up/down).

## 🚦 WHERE WE ARE (decisions locked 2026-06-30)
- **Standalone repo**, reusing election-forecast patterns (not coupled to the live one).
- **v1 states: NC + GA**, end-to-end first. Then NV/AZ/PA (registration), then WI/MI.
- **County-lean method** for partisanship (works in registration AND no-registration
  states). Registration splits (NC/NV/AZ/PA) are a later sharpening.
- **Comparator cycle: 2022 (midterm) is ideal** for the 2026 midterm; we currently have
  2020 Senate + 2024 President as baseline (2022 precinct data is the top data TODO).

## ✅ DONE — analytics core (runnable NOW, validated)
  data/baseline/county_results.csv  — NC+GA county×party×mode, from MEDSL precinct files
  data/baseline/county_lean.csv     — per-county Dem two-party lean + early-vote share
  analytics/build_baseline.py       — extract NC/GA from the big nationwide files
  analytics/county_lean.py          — lean + early-mix baseline (mode labels normalized;
                                      GA "TOTAL" double-count dropped)
  analytics/turnout_compare.py      — PRIMARY VIEW (what the user wants): per-county
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
  python analytics/make_fixture.py GA && python analytics/turnout_compare.py GA   # primary
  python analytics/make_fixture.py NC && python analytics/turnout_compare.py NC
  python analytics/evote_signal.py GA   # secondary lean-composite view
