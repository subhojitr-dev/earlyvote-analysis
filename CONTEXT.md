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

## 🟢 2026-10-20: FLORIDA + SOUTH CAROLINA ADDED (main dashboard tabs), vs 2022, in the noon task
- FL (ingestor/fl_fetch.py): Division of Elections daily stats files Stats_49894_{EarlyVoted,VbmVoted}.txt
  (public; add a cache-busting ?ts= or a 1-2 day old copy comes back), county x party, cumulative through
  the previous day; one snapshot stored per run (data/fl_county/snapshots_2026.csv). 2022 = Internet
  Archive copies of the PublicStats page (14 days Oct 6-Nov 6 2022); early-Oct 2022 pages still list the
  PRIMARY, so rows are filtered to election 26906. Compared in person + mail, by day of early voting
  (counties may open 15 days out: Oct 24 2022 / Oct 19 2026). Day 1: 1,104,849 = 79% of 2022.
- SC (ingestor/sc_fetch.py): 2022 = Commission's archived "EV Stats (2022 GE)" workbook (in person by
  county by day, 561,563 total); 2026 = the general-election early-voting CSV on scvotes.gov
  voter-participation page (found automatically; NOT posted yet on Oct 20 -> SC tab shows a waiting
  notice via build_dashboard WAITING). In-person only (2022 mail exists only as a final total).
- County leans: 2022 FL US Senate, 2022 SC Governor (analytics/add_baseline_2022.py, MEDSL fl22/sc22).

## 🟢 2026-10-16: GA IS ON REAL DATA, COMPARED WITH 2022 ONLY
- **User's rule: GA compares with 2022 only** (no 2020, no 2024), at the same DAY OF EARLY VOTING
  (opened Oct 17 2022 / Oct 13 2026; 2026 day k vs 2022 day k).
- Main dashboard GA tab: real 2026 county counts — official SoS file (ingestor/ga_county.py 2026)
  or georgiavotes.com fallback (ingestor/ga_georgiavotes.py), newer wins — vs 2022 same day
  (analytics/ga_sameday.py, hooked into turnout_compare.series_by_year_county).
- District page /ga/: every district vs 2022. Redrawn (Dec 2023) districts use 2022 votes re-counted
  on today's lines: ingestor/ga_districts.py recount -> data/ga_districts/early_2022_cur.csv (precinct
  crosswalk from voters in both 2022 & 2024 files; validated: unchanged districts match the original
  2022 counts within 0.17% median, 2.8% worst). Builder: STATES["GA"] only_2022 + shift {2022: 1}.
- First read (through Oct 15, day 3): 552,066 ballots = 124% of 2022 same day; net share edge
  +3.1 pts toward D. District page live view waits on the user's daily SoS download (9–10 AM ET).
- NC/AZ/NV/PA main-dashboard tabs still synthetic (footnote says so). Routine: GA_DAILY_DOWNLOAD.md.

## 🟢 2026-10-18: MICHIGAN ADDED (main dashboard MI tab), vs 2022, AUTOMATIC
- ingestor/mi_fetch.py: Power BI public querydata API (wabi-us-gov-iowa, resource key 197238ed..., model 764331)
  → COUNTY_AV_BALLOT_COUNT (running totals per COUNT_DATE), COUNTY_IN_PERSON_EV_VOTE_COUNT_SUM, COUNTY_VOTER_COUNT.
  Model holds 2024 general, 2026 primary, 2026 general only (no 2022).
- 2022 = weekly SoS xlsx by jurisdiction attached to 2026 press releases (file date + 1 = 2022 count date);
  2026 cut back to the latest snapshot's days-out. Metric = absentee returned (no MI EV in 2022).
- add_baseline_2022.py now uses each precinct's TOTAL row when present (MI file double-reports some precincts).
- First read: 2026 Oct 13 440,677 vs 2022 Oct 18 432,960 = 102%; county share net -3.6 pts (toward R).

## 🟢 2026-10-18: OHIO ADDED (main dashboard OH tab), vs 2022, ON REQUEST
- 2026: SoS DATA Act file (per voter) blocks scripts; readable from the data.ohiosos.gov page in the browser pane:
  ingestor/oh_browser_aggregate.js → counts-only OH_2026_agg_<date>.txt → ingestor/oh_absentee.py.
  (Pane downloads don't reach Downloads; returning a padded result string that gets saved to a tool-result
  file, then parsing it, works.) In person = sent date == returned date (validated vs SoS week-1 194,841).
- 2022: only county snapshots through Oct 24 / Oct 31 / Nov 6 2022 (Internet Archive xlsx); early_2022.csv
  holds in-person increments; 2026 cut back to the latest reached snapshot's days-out. Pending notice
  (statewide 3.9x) until data through Oct 19. Lean = 2022 US Senate (add_baseline_2022.py OFFICE map).
- Not in the noon task (needs the browser); run on request. No OH district page (no 2022 district data).

## 🟢 2026-10-17: MAINE ADDED (main dashboard ME tab + /me/ district page), vs 2022 only
- ingestor/me_absentee.py: SoS statewide absentee voter file (per voter: town, party, CG/SS/SR, rec type/date);
  needs a browser User-Agent (403 otherwise). Data through the day before the file's "as of" date.
- District lines unchanged since 2022 → direct comparison; builder STATES["ME"] with house/senate/congress
  (congress shapes from national cb_2024_us_cd119, stem "us:cd119"). Lean = MEDSL 2024 (me24.csv).
- Builder fixes for all states: precinct names matched case-insensitively; district page uses the live
  {st}_meta.json as-of day; small city districts kept on county maps; non-candidate rows ("Total Ballots
  Cast") skipped in 2024 race results; congressional race label "U.S. House".
- First read (thru Oct 15): 96,762 = 138% of 2022 same day; county share net +11.2 D, but party mix about flat
  (D-R gap 34.2 vs 33.6), growth among unenrolled (25.0% vs 21.1%).

## 🟢 2026-10-16: NC ON REAL DATA, COMPARED WITH 2022 ONLY
- nc_districts.py 2026 (public SBE file) now also writes data/nc_county/early_{y}.csv + data/live/nc_*;
  main dashboard NC tab = real vs 2022 same day (analytics/sameday.py, NC opened 19 days out both years).
- District page: every NC district vs 2022; redrawn (Oct 2023) use early_2022_cur.csv + demo_2022_cur.csv
  (nc_districts.py recount, NCID precinct crosswalk). Builder STATES["NC"] only_2022 + demo_2022.
- Day 1 (Oct 15): 237,539 ballots = 125% of 2022 same day; net +8.7 pts D by county share; party mix
  D 46.9 / U 33.4 / R 19.5 vs 2022 day 1 D 41.8 / U 29.4 / R 28.6.
- Daily noon scheduled task "daily-tx-ga-earlyvote-refresh" runs TX + NC + GA fallback, checks, pushes.

## 🟢 2026-10-16: TX AUTOMATED, COMPARED WITH 2022 ONLY
- TX SoS site = public JSON API (getFile?type=EVR_ELECTION / EVR_EARLYVOTING / EVR_STATEWIDE, base64
  payloads): ingestor/tx_fetch.py pulls county totals + statewide rosters daily, no manual download.
- 2026 rosters are CUMULATIVE; tx_districts.py differences consecutive days (per-file counts cached
  in data/incoming/tx/2026/.agg_*.json).
- Every TX district vs 2022; congressional (2025 map) uses 2022 re-counted via same precinct code in
  2024 (House district agrees 9,570/9,571). Builder STATES["TX"] only_2022.
- Main dashboard TX tab (analytics/sameday.py, generic GA/TX): IN-PERSON ONLY (mail reporting lags by
  county: 85/254 on Oct 15) and a pending notice until in-person opens Oct 19. Lean = 2022 governor
  (analytics/add_baseline_2022.py, MEDSL tx22.zip).

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
