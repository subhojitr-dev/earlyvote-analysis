# Dashboard guide — how to read it

**Live:** https://earlyvote-analysis.vercel.app

> Screenshots: the live URL is the canonical view. To capture stills, open the site and use
> the state tabs; drop images into a `docs/img/` folder and link them here if desired.

The dashboard answers one question — *is the early electorate tilting more Democratic or more
Republican than in past cycles, and how far along is turnout* — for five swing states
(GA, NC, AZ, NV, PA). Switch states with the **tabs** at the top.

---

## Layout, top to bottom

### 1. Summary cards
- **Early ballots so far (2026)** — total early ballots in the current feed, and that total as
  a % of each year's *full early vote* (a rough "how far along" gauge).
- **Net turnout edge vs 2022** and **vs 2020** — the headline. It combines the Dem-leaning and
  Rep-leaning county groups into one number: `Dem-group share change − Rep-group share change`,
  in points. Blue/positive = toward **Democratic** turnout; red/negative = toward Republican.
  The sub-line shows each group's own shift.

### 2. Aggregate Dem tilt of the early electorate (left panel)
Four bars — 2020, 2022, 2024, and 2026 — showing the **composite Democratic tilt**: each
county's fixed partisan lean weighted by its share of that year's early vote. The vertical tick
marks 50%. Because the lean is fixed, differences between bars come *only* from where the early
votes concentrate. The read line tells you whether 2026 is above all prior years and whether it
**erases** the dip of a weaker year (e.g. GA 2026 ≈ 51.9% D, above 2020/2022/2024 — the jump vs
2024 erases the 2024 dip).

### 3. Turnout progress vs full prior turnout (right panel)
- A headline stat: **≈X% of registered voters have voted early** (a *true* turnout rate; marked
  "est." while registration denominators are estimated from 2024 turnout).
- Three bars — 2026 early vote as a % of each year's **total** turnout. The tick marks 100%; a
  bar **past** it means 2026 early voting alone has already exceeded that entire past election.
  Bars climb daily as early voting runs.

### 4. County table (with a view toggle)
A sortable, filterable grid of every county. Click any column header to sort; type to filter by
name; use the dropdown to show only Dem- or Rep-leaning counties. The **toggle** switches the
right-hand columns between two views:

- **Partisan shift** — `vs 2020 / vs 2022 / vs 2024` cells, each = how much bigger (**green**)
  or smaller (**red**) a slice of the early vote that county is now, vs that year.
- **Turnout progress** — `% of 2020 / 2022 / 2024` cells, each = 2026 early votes as a % of that
  county's full turnout that year, with a small bar (green once past 100%).

Columns: **County · Lean** (Dem two-party %) · **Grp** (D/R badge) · **2026 share** · the three
view-specific columns.

---

## How to interpret it correctly

**The cells are party-neutral; the partisan meaning comes from pairing color with the county's
lean.** A green cell only means "this county is a bigger slice of the early vote than that year."
You read the party signal by combining it with the **Grp** badge:

| Cell | County Grp | Meaning |
|---|---|---|
| 🟢 green | **D** (Dem-leaning) | good for **Democrats** (a Dem area over-voting) |
| 🟢 green | **R** (Rep-leaning) | good for **Republicans** (a Rep area over-voting) |
| 🔴 red | **D** | bad for Democrats |
| 🔴 red | **R** | bad for Republicans |

So the Democratic edge = **Dem-leaning counties green + Rep-leaning counties red**, together —
which is exactly what the "Net turnout edge" card summarizes.

**Cells in one row can be mixed.** Each `vs YEAR` cell is independent. A county can be ahead of
its 2022 pace (green) but behind 2020 and 2024 (red) — e.g. Richmond, GA. That's expected.

**Which year to trust most.** 2026 is a **midterm**, so **2022** (also a midterm) is the
apples-to-apples comparator. 2020 and 2024 are presidential — read those `vs`-cells as
directional context, not literal pace.

## Nuances & caveats

- **It's composition, not vote choice.** The ballot is secret. Everything measures *where* early
  voters come from, not *who* they voted for. A Dem-leaning county turning out heavily is a proxy
  for Democratic strength, not a Democratic vote count.
- **Share is zero-sum.** If Dem-leaning counties gain share, Rep-leaning counties mechanically
  lose it, so the two groups look like mirror images. The **net** line is the clean signal.
- **A few big counties dominate** in AZ (Maricopa) and NV (Clark). The share-weighting handles
  this correctly, but the "# of counties" per group can look lopsided — judge by share, not count.
- **NV & PA are totals-only** in the source data (no early/election-day split), so their signal
  runs on total-vote share rather than early-vote share — slightly less precise, still valid.
- **2026 numbers are synthetic** until real early voting opens (~Oct 2026). When the state feeds
  go live, the ingestors replace the synthetic data and the dashboard updates on the next
  build + push. The historical bars (2020/2022/2024) and the methodology are already real.
- **Turnout rate is an estimate** until real Secretary-of-State registration files replace the
  2024-derived denominator (see `analytics/build_registration.py`).
