# Georgia daily early-vote update

> **Since Oct 24 2026 this is automatic:** the noon daily task downloads the official GA file itself in Claude's built-in browser and runs these steps. You only need this guide if the task reports "GA SoS page unavailable" (blank page or CAPTCHA), in which case do it by hand as below.


**Every Georgia comparison is against 2022 only** (the last midterm), at the same day of
early voting. In-person early voting opened Mon Oct 17 2022 and Tue Oct 13 2026, so day 3 of 2026
(Oct 15) is compared with day 3 of 2022 (Oct 19). 2020 and 2024 are not used for GA.
- Main dashboard (`/`, GA tab): county shares vs 2022 (`analytics/ga_sameday.py`).
- District page (`/ga/`): every House / Senate district vs 2022. Districts redrawn in Dec 2023
  use the 2022 votes **re-counted on today's lines** (`data/ga_districts/early_2022_cur.csv`, built
  once by `python ingestor/ga_districts.py recount`; each 2022 voter placed by their precinct).

**When:** download the official file daily, **9:00–10:00 AM Eastern** (the SoS rebuilds it ~8 AM,
weekends included; any later time that day gets the same file). Steps 1–3 below.

**Skipped a day?** The main dashboard can still refresh without the download (the district page
can't): `python ingestor/ga_georgiavotes.py`, then `python web/build_dashboard.py`, then commit
`web/index.html`. Georgia Votes rebuilds its county table each morning from the same SoS file.
Whichever source is newer wins automatically.

---

## District page (`/ga/`): manual download, ~2 minutes

The Georgia State House / State Senate drill-down page (`web/ga/`) is fed by the
Georgia Secretary of State's **absentee voter file**: one row per voter who requested
or cast an absentee/early ballot, including their congressional, State Senate and
State House district. The SoS page has a reCAPTCHA (anti-bot check), so the file is
downloaded **by hand** once a day. Do not try to automate around the check.

**When:** once a day, **after ~9:00 AM**. The SoS rebuilds the file early each morning
(the Oct 4, 2026 file was stamped 08:08), including weekends.
**Season:** now through Election Day (Tue Nov 3, 2026). In-person early voting runs
**Tue Oct 13 – Fri Oct 30, 2026** (plus mandatory Saturdays Oct 17 & 24); until then the file holds mail ballots only.

---

## Step 1 — Download the statewide 2026 file

1. Open this direct link (it pre-selects 2026 / Nov 3 general / statewide and goes
   straight to the download):

   https://mvp.sos.ga.gov/s/voter-absentee-files?electionYear=2026&electionName=11%2F3%2F2026%20-%20NOVEMBER%203%2C%202026%20-%20GENERAL%20%26%20SPECIAL%20ELECTIONS&elecId=a0pcs00000J6eJBAAZ&countyName=&name=A-12601&page=voterAbsenteeFilesDetails

   *If the link stops working*, do it by hand at https://mvp.sos.ga.gov/s/voter-absentee-files :
   - **Election Year:** `2026`
   - **Election Name:** `11/3/2026 - NOVEMBER 3, 2026 - GENERAL & SPECIAL ELECTIONS`
     (not any "RUNOFF" or "SPECIAL ELECTION" entry)
   - **County:** leave **blank** (= statewide)
   - Click **SUBMIT**

2. Click the file link that appears:
   `11/3/2026 - NOVEMBER 3, 2026 - GENERAL & SPECIAL ELECTIONS.zip (xx MB)`
   - **Click it within about a minute.** The link is a temporary signed link and expires
     quickly. If you get an "expired" / "AccessDenied" page, just reload the SoS page
     and click again.
   - Size: ~9 MB on Oct 4; it will grow to a few hundred MB by the end of early voting
     (the 2024 final file was ~300 MB).

## Step 2 — Put it in the project

Save / move the downloaded zip to the following location, **renaming it exactly**:

```
C:\Users\subho\earlyvote-analysis\data\incoming\ga\GA_2026_general.zip
```

Overwrite yesterday's copy (only the latest file is needed, because it is cumulative).
Do not unzip it.

> 🔒 This file contains voters' names and addresses. `data/incoming/` is gitignored, so it
> never goes to GitHub, and the processing step writes **only counts**. Never move it
> anywhere else, email it, or commit it.

## Step 3 — Process and publish

From `C:\Users\subho\earlyvote-analysis`:

```bash
python ingestor/ga_districts.py 2026
```
```bash
python ingestor/ga_county.py 2026
```
```bash
python web/build_ga_districts.py
```
```bash
python web/build_dashboard.py
```
```bash
python ingestor/ga_polling.py
```
```bash
python analytics/check_ga_districts.py
```
```bash
git add data/ga_districts data/ga_county web/ga web/index.html && git commit -m "GA early-vote update" && git push
```

- `ga_districts.py 2026` feeds the district page; `ga_county.py 2026` feeds the main dashboard's GA tab
  (it prints `2026: N accepted ballots ... through <yesterday>`).

- `ga_polling.py` refreshes the **View Polling Data** page for GA, MI, OH & TX (polls, averages, ratings, betting
  odds) from public sources. **No download needed**, and it can be run any time, even on days you
  skip the early-vote file. If a source is down it keeps the last good copy and says when that was fetched.
- `check_ga_districts.py` should end with **ALL CHECKS PASSED**. If it fails, don't push; ask Claude.

Vercel redeploys automatically a minute or two after the push.

**Quick check:** the `ingestor` step prints `2026: N accepted early/mail ballots`. N should
be **higher than yesterday**. If it is lower or zero, you probably grabbed the wrong
election (a runoff/special) or the download was incomplete. Re-download.

---

## One-time files (already downloaded, no daily action)

| File in `data/incoming/ga/` | What | Why |
|---|---|---|
| `GA_2024_general.zip` | Nov 5 2024 general, final | Comparison year for districts redrawn before 2024 |
| `GA_2022_general.zip` | Nov 8 2022 general, final (**not** the Dec 6 runoff) | Comparison year for districts unchanged since 2022; redraw detection |

Also `data/raw/medsl/ga24.csv`: MIT Election Lab's official 2024 Georgia precinct results, all races
(from `ga24.zip` at github.com/MEDSL/2024-elections-official → `individual_states`). It gives each
district's 2024 presidential lean and its 2024 State House / Senate result.

Same page, Election Year `2024` → `11/5/2024 - NOVEMBER 5, 2024 - GENERAL ELECTION`,
and `2022` → `11/8/2022 - 11/08/2022 GENERAL/SPECIAL ELECTION`, County blank.

## Testing before early voting opens

- **Now (real file, small):** the 2026 file already exists with mail ballots. Doing steps
  1–3 today is a real end-to-end test of the download → process → publish routine.
- **Volume / page test (simulated):** until Oct 13 the page also builds a clearly labelled
  **demo snapshot** (2024's pattern a week into early voting, scaled to midterm size), so the
  page can be checked at realistic early-voting volumes.
- **First real in-person day:** Wed Oct 14 morning's file (covering Tue Oct 13) is the
  first one with in-person early votes. Check that the counts jump and the page updates.

---

## North Carolina (no manual download; runs in the daily noon task)

The NC pages use the NC State Board of Elections absentee file, a **public direct download** (no anti-bot
check), rebuilt ~5 AM ET each day. One command fetches and processes it. It also carries each early voter's
race, ethnicity, gender, age and party, which feed the "Who has voted early" tables.
NC in-person early voting runs **Thu Oct 15 – Sat Oct 31, 2026**.

```bash
python ingestor/nc_districts.py 2026
```
```bash
python web/build_ga_districts.py NC
```
```bash
python web/build_dashboard.py
```
```bash
python analytics/check_ga_districts.py NC
```
```bash
git add data/nc_districts data/nc_county web/nc web/index.html && git commit -m "NC early-vote update" && git push
```

- **Everything compares with 2022 only**, at the same day of early voting (opened 19 days before Election
  Day both years: Thu Oct 20 2022, Thu Oct 15 2026).
- `nc_districts.py 2026` also writes the main dashboard's NC tab feed (`data/nc_county/early_2026.csv`,
  `data/live/nc_current.csv`).
- Districts redrawn in Oct 2023 (70 of 120 House, 28 of 50 Senate) use the 2022 votes **and demographics
  re-counted on today's lines** (`data/nc_districts/early_2022_cur.csv`, `demo_2022_cur.csv`; built once by
  `python ingestor/nc_districts.py recount`, each 2022 voter placed by their precinct). Check: unchanged
  districts match the original 2022 counts within 0.17% (House) / 0.01% (Senate) median.

One-time files (already downloaded): `data/incoming/nc/NC_2022_general.zip`, `NC_2024_general.zip`, and
`data/raw/ncsbe/STATEWIDE_PRECINCT_SORT_2024.txt`, the Board's **precinct-sorted** 2024 results, used
for the district lean. That file matters: other 2024 files report many counties' early votes by voting
*site*, which mixes districts and threw some NC district leans off by up to 14 points.

`data/nc_districts/demo_*.csv` also holds the early electorate's make-up for each **congressional**
district, for the Demographic Analysis app.

---

## Michigan (automatic, no download; runs in the daily noon task)

```bash
python ingestor/mi_fetch.py
```
```bash
python web/build_dashboard.py
```
```bash
git add data/mi_county data/reference/registration.csv web/index.html && git commit -m "MI early-vote update" && git push
```

- **2026:** the SoS Michigan Voting Dashboard is a public Power BI report; `mi_fetch.py` asks Power BI's public
  query service for the same tables the page shows (daily, by county: absentee ballots returned / sent, early
  in-person votes from Oct 24, registered voters). Checked: Oct 13 statewide returned = 440,677, the SoS figure.
- **2022:** the dashboard has no 2022 data. Each weekly SoS press release attaches 2022 ballot stats by
  jurisdiction for the same point (file dated the day before the 2022 count it pairs with). `mi_fetch.py` checks
  for new ones each run (`data/incoming/mi/MI_2022_<date>.xlsx`); towns are rolled up to counties.
- **Compared on absentee ballots returned** (Michigan had no early in-person voting in 2022), with 2026 cut back
  to the same days before Election Day as the latest 2022 snapshot. Early in-person votes are shown as 2026-only.
- County lean = 2022 governor by county (`python analytics/add_baseline_2022.py MI`; the MIT file reports some
  precincts both as TOTAL and by mode, so the script uses TOTAL when present).
- No district page (the dashboard has no district data).

---

## Ohio (automatic since Oct 25 2026: in the noon task; file posted weekdays and Saturdays ~11:30 AM)

> The noon task runs `ingestor/oh_browser_return.js` in Claude's built-in browser and saves the counts with
> `ingestor/oh_save_agg.py`; the steps below are what it does, and what to do by hand if it reports a problem.

Ohio's statewide absentee / early-vote file (one row per voter, ~270 MB, updated **weekdays** ~11 AM) is
refused to scripts, but opens normally in a browser on the Secretary of State's data portal. So Claude:

1. opens https://data.ohiosos.gov/portal/election-dashboards in the browser pane,
2. runs `ingestor/oh_browser_aggregate.js` there, which reduces the file to **counts only** (county x day x
   in-person/mail, plus party by day) and saves `data/incoming/oh/OH_2026_agg_<date>.txt`,
3. runs:

```bash
python ingestor/oh_absentee.py
```
```bash
python web/build_dashboard.py
```
```bash
git add data/oh_county web/index.html && git commit -m "OH early-vote update" && git push
```

- **Compared with 2022 on in-person early votes by county.** For 2022 Ohio only published county numbers at
  three points (votes as of Oct 21, Oct 28 and Nov 7 2022 = 18, 11 and 1 days before Election Day;
  `data/incoming/oh/oh22_*.xlsx`, from the Internet Archive). 2026 is cut back to the same number of days out
  as the latest of those points it has reached. Before the first one (data through Mon Oct 19, posted ~Tue
  Oct 20) the OH tab shows the statewide comparison only (2022: 50,368 in person through Oct 17).
- In person = ballot issued and cast the same day; matches the state's own week-1 total (194,841) within 1%.
- County lean = 2022 **U.S. Senate** race (Vance vs Ryan); the governor race (DeWine +25) was too lopsided.
- No district page: no 2022 district-level data exists for Ohio.

---

## Maine (automatic, no download; runs in the daily noon task)

Maine has no separate early voting: voting early = **absentee**, cast in person at the town clerk or returned
by mail / drop box. The Secretary of State posts one statewide absentee voter file (one row per voter: town,
party, ward, congressional / State Senate / State House district, received type and date), refreshed during
the voting period. The site returns 403 to bare scripts, so the ingestor sends a normal browser User-Agent
(the file is public; no login or CAPTCHA).

```bash
python ingestor/me_absentee.py 2026
```
```bash
python web/build_ga_districts.py ME
```
```bash
python web/build_dashboard.py
```
```bash
python analytics/check_ga_districts.py ME
```
```bash
git add data/me_county data/me_districts web/me web/index.html && git commit -m "ME early-vote update" && git push
```

- **Compared with 2022 only**, by days before Election Day (both Tuesdays). District lines are unchanged
  since 2022 (town/ward → district agrees for 608 of 611 pairs), so no re-count is needed.
- The file is named "as of <date>" and that day is only partly counted, so the data runs through the day before.
- Town → county from MIT Election Lab's 2022 Maine file (`data/raw/medsl/me22.zip`) plus a few unorganized
  townships; ~0.1% of ballots (tiny townships) have no county and are left out.
- County lean = 2022 governor by county (`python analytics/add_baseline_2022.py ME`); district lean = 2024
  presidential (`data/raw/medsl/me24.csv`). Party registration feeds the "Who has voted early" tables.
- One-time file: `data/incoming/me/ME_2022_general.txt` (Nov 8 2022 final), downloaded automatically.

---

## Texas (automatic, no download)

The Texas Secretary of State's early-voting site runs on a public JSON API, so the county counts and the
statewide voter roster are **fetched automatically**. No browser, no CAPTCHA. Run once a day after ~11 AM
(Texas law requires each day's report by 11 AM the next morning):

```bash
python ingestor/tx_fetch.py
```
```bash
python ingestor/tx_districts.py 2026
```
```bash
python web/build_ga_districts.py TX
```
```bash
python web/build_dashboard.py
```
```bash
python analytics/check_ga_districts.py TX
```
```bash
git add data/tx_county data/tx_districts web/tx web/index.html && git commit -m "TX early-vote update" && git push
```

- `tx_fetch.py` gets every posted day not already on disk: county totals → `data/tx_county/turnout_{date}.csv`
  (+ the main dashboard's TX tab) and the statewide roster → `data/incoming/tx/2026/` (names, gitignored).
- **The 2026 rosters are cumulative** (each day's file = everyone through that day), unlike the old site's
  one-day files. `tx_districts.py` turns them into daily counts by differencing consecutive days.
- **Everything compares with 2022 only.** House and Senate lines are unchanged since 2022; congressional
  lines were redrawn in 2025, so 2022 votes are re-counted on the new lines (each 2022 precinct takes the
  2025 district of the same precinct code in 2024; codes are stable).
- Early voting opened 15 days before Election Day in both years (Mon Oct 24 2022, Mon Oct 19 2026).
- **Main dashboard TX tab = in-person early votes only.** The new site's mail counts lag badly by county
  (on Oct 15 only 85 of 254 counties had reported any), which would fake a partisan signal. Until in-person
  voting opens the tab shows a "first comparison Tue Oct 20" notice.
- County lean = 2022 governor's race by county (MIT Election Lab, `python analytics/add_baseline_2022.py`).

### How the Texas district numbers are built
- Precinct → district: Texas Legislative Council tables (2022 / 2024 general and 2026 primary
  precincts), `data/raw/tlc/`. ~1% of votes have precinct codes that don't match; those are shared
  out within their county.
- District lean: 2024 presidential vote by district from the Council's Red-206 reports.
- Hispanic / Asian: Census 2010 surname table (`web/tx/surnames.txt`). Checked against the Council's
  Spanish-surname registration share: correlation 0.99 across House districts.
- 2022 history: `data/incoming/tx/tx_ev_2022.json`, counts reduced in the browser from the Secretary of
  State's old early-voting site (earlyvoting.texas-election.com).
