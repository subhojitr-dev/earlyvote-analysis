# Georgia daily early-vote download (manual, ~2 minutes)

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
python web/build_ga_districts.py
```
```bash
python ingestor/ga_polling.py
```
```bash
python analytics/check_ga_districts.py
```
```bash
git add data/ga_districts web/ga && git commit -m "GA early-vote update" && git push
```

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

## North Carolina (no manual download)

The NC page (`/nc/`) uses the NC State Board of Elections absentee file, which is a **public
direct download** (no anti-bot check), so one command fetches it. It also carries each early
voter's race, ethnicity, gender, age and party, which feed the "Who has voted early" tables.
NC in-person early voting runs **Thu Oct 15 – Sat Oct 31, 2026**.

```bash
python ingestor/nc_districts.py 2026
```
```bash
python web/build_ga_districts.py NC
```
```bash
python analytics/check_ga_districts.py NC
```
```bash
git add data/nc_districts web/nc && git commit -m "NC early-vote update" && git push
```

One-time files (already downloaded): `data/incoming/nc/NC_2022_general.zip`, `NC_2024_general.zip`, and
`data/raw/ncsbe/STATEWIDE_PRECINCT_SORT_2024.txt`, the Board's **precinct-sorted** 2024 results, used
for the district lean. That file matters: other 2024 files report many counties' early votes by
voting *site*, which mixes districts and threw some NC district leans off by up to 14 points.

`data/nc_districts/demo_*.csv` also holds the early electorate's make-up for each **congressional**
district, for the Demographic Analysis app.

---

## Texas (manual daily download, from Mon Oct 19)

The TX page (`/tx/`) shows mail and in-person early votes by **congressional, State House and State
Senate district**, plus an **estimate** of Hispanic and Asian early voters from surnames. Texas posts a
daily list of everyone who voted early (name, voter ID, voting method, precinct), but the site has a
browser check, so it's downloaded by hand. Texas early voting runs **Mon Oct 19 – Fri Oct 30, 2026**.

### Step 1: download yesterday's statewide report (after ~11 AM; the law requires posting by 11 AM)

1. Open https://goelect.txelections.civixapps.com/ivis-evr-ui/evr
2. **Select Election:** `2026 NOVEMBER GENERAL ELECTION`
3. **Unofficial Early Voting Turnout by Date:** pick the day → **Submit**
4. On the turnout page click **Generate Statewide Report**. It saves a CSV like
   `STATEWIDE.<election>.EarlyVoting.<date>.csv`.
5. Move it, **without renaming it** (the date in the name is used), into
   `C:\Users\subho\earlyvote-analysis\data\incoming\tx\2026\`.
   Each day's file holds only that day's voters, so **keep every day's file** (unlike GA/NC).
   If you missed a day, download that day too.

> 🔒 These files contain voters' names. `data/incoming/` is gitignored; the processing step
> uses surnames only to look up the Census surname table and writes **only counts**.

### Step 2: process and publish

```bash
python ingestor/tx_districts.py 2026
```
```bash
python web/build_ga_districts.py TX
```
```bash
python analytics/check_ga_districts.py TX
```
```bash
git add data/tx_districts web/tx && git commit -m "TX early-vote update" && git push
```

**First day (Oct 19):** the 2026 file format on the new Texas site hasn't been seen yet (the site
takes reports down after each election). The script finds columns by name, but check that
`tx_districts.py 2026` prints a sensible voter count, and ask Claude if it doesn't.

### How the Texas numbers are built
- Precinct → district: Texas Legislative Council tables (2022 / 2024 general and 2026 primary
  precincts), `data/raw/tlc/`. ~1% of votes have precinct codes that don't match; those are shared
  out within their county.
- House and Senate lines are unchanged since 2022 → compared with 2022. Congressional lines were
  redrawn in 2025 → compared with 2024 votes re-counted on the new lines (6% of 2024 votes got their
  congressional district from their county's mix).
- District lean: 2024 presidential vote by district from the Council's Red-206 reports.
- Hispanic / Asian: Census 2010 surname table (`web/tx/surnames.txt`). Checked against the Council's
  Spanish-surname registration share: correlation 0.99 across House districts.
- 2022 / 2024 history: `data/incoming/tx/tx_ev_{2022,2024}.json`, counts reduced in the browser from
  the Secretary of State's old early-voting site (earlyvoting.texas-election.com).
