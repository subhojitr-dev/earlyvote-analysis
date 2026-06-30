# earlyvote-analysis

Reads the **partisan early-voting signal** by state and county in U.S. swing states,
so campaigns can act proactively. Sibling to `election-forecast` (which handles
election-night results); this one covers the weeks *before* election day.

**The question it answers:** is the early electorate so far tilting more Democratic or
more Republican than a comparable past cycle — statewide, and which counties drive it?

Because the ballot is secret, this is a *composition* signal, not a vote prediction:
each county's early-vote volume is weighted by its historical partisan lean to read
whether the people voting early are coming from more-D or more-R places than usual.

- **v1 states:** NC + GA (best public feeds), then NV/AZ/PA, then WI/MI.
- **Method:** county-lean (works with or without party registration). See `CONTEXT.md`.

## Quickstart
```bash
pip install -r requirements.txt          # (analytics core needs no deps)
python analytics/build_baseline.py       # one-time: extracts NC/GA county baseline
python analytics/county_lean.py          # -> data/baseline/county_lean.csv
python analytics/make_fixture.py NC      # synthetic "voting in progress"
python analytics/evote_signal.py NC      # -> the signal + per-county pull
```

See **`CONTEXT.md`** for status, decisions, and the next-session roadmap.
