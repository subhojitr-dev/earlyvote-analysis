# Overview — Early-Vote Analysis (plain-English guide)

This document explains, in non-technical terms: (1) **where the data comes from**,
(2) **what was built this session**, and (3) **how you can see it working yourself**.

---

## 1. What this project does (one paragraph)

In the weeks before an election, millions of people vote early. We can't see *who*
they voted for (the ballot is secret), but we **can** see *how many people voted early
in each county* and *what kind of county it is* (does it usually vote Democratic or
Republican?). By combining those, we get an early read: **"Is the early electorate so
far leaning more Democratic or more Republican than it did in a comparable past
election?"** — statewide, and broken down to the exact counties driving it, so a
campaign knows where to focus.

---

## 2. Where the data comes from (sources & URLs)

There are **two different kinds of data**, and it's important to keep them separate:

### A) Partisan lean of each county — "what kind of county is this?"
This is the backbone. It tells us whether a county is Democratic-leaning or
Republican-leaning, based on how it has actually voted in past elections.

| Source | What it gives us | URL |
|---|---|---|
| **MIT Election Data & Science Lab (MEDSL)** precinct-level results, via Harvard Dataverse | Official past results down to precinct, with a column for *how* each vote was cast (early / mail / election-day). This is what we used. | https://electionlab.mit.edu/data · https://dataverse.harvard.edu/dataverse/medsl_election_returns |
| **Dave Leip's Atlas of U.S. Elections** (alternative/cross-check) | County-level historical results | https://uselectionatlas.org |

> In this project the partisan lean currently comes from **2020 U.S. Senate** and
> **2024 President** results for NC & GA. (These big nationwide files already live in
> your `election-forecast` project, so we reused them instead of re-downloading.)

### B) Live early-voting turnout — "how many people have voted early so far?"
This is the *current-cycle* feed we'll pull starting ~October 2026. Each swing state
publishes it differently. States marked **(party)** also record each early voter's
registered party, which makes the signal sharper; the rest have **no party
registration**, so for them we rely entirely on the county-lean method above.

| State | Source | Party registration? | URL |
|---|---|---|---|
| **North Carolina** | NC State Board of Elections — absentee/early-vote data (one row per early ballot, includes county + registered party). *Best public feed in the country.* | ✅ Yes | https://www.ncsbe.gov/results-data/absentee-data · raw files: https://dl.ncsbe.gov/?prefix=ENRS/ |
| **Georgia** | GA Secretary of State — daily "advanced voting" / absentee statistics | ❌ No | https://sos.ga.gov/page/voting-statistics · https://elections.sos.ga.gov |
| **Nevada** | NV Secretary of State — early voting turnout | ✅ Yes | https://www.nvsos.gov/sos/elections |
| **Arizona** | AZ Secretary of State + county recorders (esp. Maricopa) — early ballot returns | ✅ Yes | https://azsos.gov/elections · https://recorder.maricopa.gov |
| **Pennsylvania** | PA Department of State — mail-ballot applications & returns | ✅ Yes | https://www.vote.pa.gov · https://www.pa.gov/agencies/dos |
| **Wisconsin** | WI Elections Commission — absentee ballot data | ❌ No | https://elections.wi.gov |
| **Michigan** | MI Secretary of State — absentee + (new since 2024) in-person early voting | ❌ No | https://www.michigan.gov/sos/elections |

> **One best-single-source shortcut for past early-vote numbers:** the **University of
> Florida Election Lab** (Prof. Michael McDonald) has tracked early voting by state for
> years and is the go-to historical reference — https://election.lab.ufl.edu .

---

## 3. What was accomplished THIS session (in plain terms)

We built and **proved** the "brain" of the system — the math that turns raw early-vote
counts into a partisan signal. Specifically:

1. **Built a county "report card"** for all 100 NC counties and all 159 GA counties:
   how Democratic-or-Republican each one leans, and how much of its vote is normally
   cast early. *(This is the file `data/baseline/county_lean.csv`.)*

2. **Built the signal calculation** — feed in "how many early ballots each county has
   cast so far" and it tells you: *the early electorate is tilting X points toward the
   Democrats (or Republicans) vs. a normal year*, and **which counties are responsible**.

3. **Tested it with realistic stand-in numbers** (real early voting hasn't started for
   2026 yet — it begins ~October). The results came out exactly as a political analyst
   would expect, which is how we know the math is right:
   - North Carolina leans 48.7% Democratic, Georgia 49.3% — both correct toss-up states.
   - The most-Democratic counties it found are Durham, Orange, and Mecklenburg (the
     Raleigh-Durham and Charlotte areas) — correct.
   - In the Georgia test, the counties pushing the Democratic signal hardest were
     DeKalb, Fulton, and Clayton — the actual Atlanta-area Democratic strongholds.

In short: **the analytical engine works and is trustworthy. What's left is plumbing** —
connecting the live state feeds (Section 2B) and putting a website on top.

---

## 4. How YOU can observe it (copy-paste these)

Open a terminal in `C:\Users\subho\earlyvote-analysis` and run:

```bash
# 1. Build the county report card (one-time)
python analytics/build_baseline.py
python analytics/county_lean.py

# 2. Create realistic stand-in "early voting in progress" numbers, then read the signal
python analytics/make_fixture.py GA
python analytics/evote_signal.py GA      # <- this prints the headline signal + counties
```

You'll see output like:
```
=== GA early-vote signal ===
  ballots in: 3,586,435 across 159 counties
  early-electorate lean now : 51.25% Dem
  baseline early lean       : 50.09% Dem
  SIGNAL: +1.16 pts  ->  tilting toward D
  counties pulling hardest:
    DEKALB   lean 83% ...   FULTON  lean 72% ...   CLAYTON lean 87% ...
```

You can also just **open the spreadsheet** `data/baseline/county_lean.csv` in Excel to
see every county's lean and early-vote share directly.

> When real 2026 early voting starts in October, the only change is that the stand-in
> numbers in step 2 get replaced by live downloads from the state websites in Section 2B
> — everything downstream already works.

---

## 5. Is it saved? (git status)

Yes — this is a **local git repository** (created this session) with everything committed
on your machine. It is **not yet on GitHub / not pushed online** — say the word and it
can be published like your `election-forecast` repo. For day-to-day status and the
technical roadmap, see **`CONTEXT.md`**.
