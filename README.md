# earlyvote-analysis

Partisan **early-voting signal** by state and county for U.S. swing states (NC, GA, AZ, NV,
PA). Reads whether the early electorate is tilting more Democratic or Republican than in
2020 / 2022 / 2024, so campaigns can act before election day. Sibling to `election-forecast`
(which handles election-night results); this covers the weeks before.

- **Live:** https://earlyvote-analysis.vercel.app
- **Repo:** https://github.com/subhojitr-dev/earlyvote-analysis (branch `main`)
- **Docs:** `Overview.md` (what/why/who) · `Architecture.md` (how it works) · `DASHBOARD.md` (how to read it)

> The 2026 figures are **synthetic stand-ins** until real early voting opens (~Oct 2026).
> The engine, baselines, and ingestor parsers are real and tested.

## Requirements
- Python 3.9+ (analytics core uses only the standard library; `requirements.txt` lists
  extras for the optional API/ingestor niceties).
- The nationwide MEDSL source CSVs (~0.9 GB) live in the sibling `election-forecast/data/raw`
  and are **not** stored here. The compact NC/GA/AZ/NV/PA baseline they produce **is**
  committed (`data/baseline/*.csv`), so you can run everything below without them; you only
  need the big files to rebuild the baseline from scratch (`build_baseline.py`).

## Quickstart (analytics + build the dashboard)
```bash
python analytics/build_baseline.py      # (one-time; needs election-forecast/data/raw)
python analytics/county_lean.py         # -> data/baseline/county_lean.csv
python analytics/build_registration.py  # -> data/reference/registration.csv
for S in GA NC AZ NV PA; do python analytics/make_fixture.py $S; done   # synthetic 2026
python web/build_dashboard.py           # -> web/index.html (self-contained)
```
Terminal analyses (no browser):
```bash
python analytics/performance_matrix.py GA     # overall + partisan groups + county matrix
python analytics/turnout_compare.py NC        # per-county share shift vs 2020/2022/2024
```

## Launch it

### Locally
The dashboard is a **single self-contained file** with data baked in — no backend:
- **Simplest:** open `web/index.html` in a browser (double-click / `file://`).
- **Static server:** `python web/serve.py` → http://127.0.0.1:8123
  (binds `$PORT` if set; `.claude/launch.json` wires it to the Claude Code preview).

Unlike `election-forecast` (FastAPI backend + Vite frontend, two servers), this has **no
app/API server** — it's pure static output.

### Remote (production)
Deployed on **Vercel** as a static site, auto-redeploying on every push to `main`.
- Config: `vercel.json` (`outputDirectory: "web"`, so `web/index.html` serves at `/`).
- Redeploy = `git push`. To import fresh: vercel.com/new → pick the repo → framework
  **Other** → leave build empty → Deploy.
- GitHub Pages alternative: serve from the `web/` folder.

## Refreshing data (live season)
```bash
# 1) drop each state's downloaded raw file into data/incoming/{STATE}.csv
python ingestor/run.py           # parses -> data/live/{state}_current.csv (--demo for samples)
# 2) rebuild + redeploy
python web/build_dashboard.py
git commit -am "feed update" && git push     # Vercel auto-redeploys
```
The analytics automatically prefer `data/live/` (real feed) over the synthetic fixture.

## Where the files are
| Kind | Location |
|---|---|
| **Analytics code** | `analytics/` (build_baseline, county_lean, turnout_compare, performance_matrix, composite/progress/rate, make_fixture, build_registration) |
| **Ingestors** | `ingestor/` (nc_absentee, county_totals, run, SOURCES.md, samples/) |
| **Dashboard generator + output** | `web/build_dashboard.py`, `web/index.html`, `web/serve.py` |
| **Committed baseline data** | `data/baseline/*.csv`, `data/fixtures/*.csv`, `data/reference/registration.csv` |
| **Live feed output** (gitignored) | `data/live/`, raw drop-ins in `data/incoming/` |
| **Logs** (gitignored) | `logs/ingestor.log` — ingest runs, warnings (unmapped counties), errors |
| **Errors** | ingestor errors go to `logs/ingestor.log` *and* stderr; analytics raise to console; the dashboard is static (no server logs — use the browser console for client errors) |
| **Analytics output** | the CSVs above + `web/index.html`; terminal reports print to stdout |

## Project layout
```
analytics/     partisan-lean baseline, signal math, synthetic fixtures, registration
ingestor/      live state feed parsers + orchestrator + source docs + samples
web/           dashboard generator, generated index.html, static server
data/
  baseline/    compact NC/GA/AZ/NV/PA county results + lean (committed)
  fixtures/    synthetic 2026 "in progress" per state (committed)
  reference/   registered-voter denominators (committed)
  live/        real feed output (gitignored)     incoming/  raw drop-ins (gitignored)
logs/          ingestor.log (gitignored)
CONTEXT.md Overview.md Architecture.md DASHBOARD.md   docs
vercel.json .claude/launch.json                        deploy/dev config
```
