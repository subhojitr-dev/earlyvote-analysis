"""
mi_fetch.py — Michigan early vote by county vs the same point in 2022.

2026 — the Secretary of State's Michigan Voting Dashboard is a public Power BI report.
Its data comes from Power BI's public query service (the same calls any visitor's
browser makes), keyed by the report's public resource key. Tables used (daily, by county,
one row per COUNT_DATE = counts as of that morning, running totals):
    COUNTY_AV_BALLOT_COUNT            AV_BALLOT_COUNT (absentee ballots returned), AV_BALLOT_SENT_COUNT
    COUNTY_IN_PERSON_EV_VOTE_COUNT_SUM  IN_PERSON_VOTE_COUNT_RUNNING_TOTAL (early in-person votes, from Oct 24)
    COUNTY_VOTER_COUNT                 VOTER_COUNT (registered voters)
Checked: statewide returned on Oct 13 2026 = 440,677, the SoS press-release figure.

2022 — the model holds no 2022 data. Each weekly 2026 SoS press release attaches the 2022
ballot stats by jurisdiction for the same point ("PRNov2022BallotStatsByJurisdiction_10_17_2022.xlsx":
apps returned, ballots sent, ballots received). The file's date is the day BEFORE the 2022 count
it pairs with (Oct 17 file = Oct 18 2022 = 21 days out; total received 432,960 matches the release).
New files are found by trying the known names for each date (missing ones redirect to /sos/404).

Comparison: ABSENTEE BALLOTS RETURNED by county. Michigan had no early in-person voting in
2022 (it began in 2024), so 2026 early in-person votes are shown as 2026-only, not compared.
2026 is cut back to the same days before Election Day as the latest 2022 snapshot.

Outputs (counts only):
    data/mi_county/daily_2026.csv     county, date, returned, sent, ev_inperson
    data/mi_county/snapshots_2022.csv count_date, county, returned, requested
    data/mi_county/early_{2022,2026}.csv   county, mode, date, ballots (increments; for analytics/sameday.py)
    data/live/mi_current.csv + mi_meta.json
    data/reference/registration.csv (MI rows)

Run:  python ingestor/mi_fetch.py
"""
from __future__ import annotations

import csv
import gzip
import json
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
INCOMING = ROOT / "data" / "incoming" / "mi"
OUT = ROOT / "data" / "mi_county"
LIVE = ROOT / "data" / "live"
KEY = "197238ed-19df-47d1-99e9-87ab97a5f397"          # the dashboard's public resource key (in its embed URL)
QURL = "https://wabi-us-gov-iowa-api.analysis.usgovcloudapi.net/public/reports/querydata?synchronous=true"
MODEL = 764331
EDAY = {2022: date(2022, 11, 8), 2026: date(2026, 11, 3)}
SNAP_BASE = "https://www.michigan.gov/sos/-/media/Project/Websites/sos/Press-releases/2026/documents/"
SNAP_NAMES = ["PRNov2022BallotStatsByJurisdiction_{d}.xlsx", "PRBallotStatsByJurisdiction_{d}.xlsx",
              "PRNov2022BallotStatsByJurisdiction_{d}_V2.xlsx", "PRBallotStatsByJurisdiction_{d}_V2.xlsx"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}


# ---------------------------------------------------------------- Power BI public query
def _q(entity: str, cols: list[str], sums: list[str], election: str | None = None):
    ref = lambda p: {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": p}}
    sel = [dict(ref(c), Name=f"t.{c}") for c in cols] + \
          [{"Aggregation": {"Expression": ref(s), "Function": 0}, "Name": f"Sum(t.{s})"} for s in sums]
    q = {"Version": 2, "From": [{"Name": "t", "Entity": entity, "Type": 0}], "Select": sel}
    if election:
        q["Where"] = [{"Condition": {"Comparison": {"ComparisonKind": 0, "Left": ref("ELECTION_DATE"),
                                                    "Right": {"Literal": {"Value": f"datetime'{election}T00:00:00'"}}}}}]
    body = {"version": "1.0.0", "queries": [{"Query": {"Commands": [{"SemanticQueryDataShapeCommand": {
        "Query": q, "Binding": {"Primary": {"Groupings": [{"Projections": list(range(len(sel)))}]},
                                "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": 30000}}},
                                "Version": 1}}}]}, "QueryId": ""}], "cancelQueries": [], "modelId": MODEL}
    req = urllib.request.Request(QURL, data=json.dumps(body).encode(), headers={
        "X-PowerBI-ResourceKey": KEY, "Content-Type": "application/json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return _rows(json.loads(raw), len(sel))


def _rows(resp, n):
    """Decode Power BI's compressed result rows: 'C' = values, 'R' = bitmask of columns repeated
    from the previous row, 'Ø' = bitmask of null columns; strings come from ValueDicts."""
    ds = resp["results"][0]["result"]["data"]["dsr"]["DS"][0]
    dicts = ds.get("ValueDicts", {})
    dm = ds["PH"][0]["DM0"] if ds.get("PH") else []
    if not dm:
        return []
    dn = [s.get("DN") for s in dm[0].get("S", [])]
    out, prev = [], [None] * n
    for r in dm:
        vals, rep, nul, cur = list(r.get("C", [])), r.get("R", 0), r.get("Ø", 0), []
        for i in range(n):
            if rep >> i & 1:
                cur.append(prev[i])
            elif nul >> i & 1:
                cur.append(None)
            else:
                v = vals.pop(0)
                cur.append(dicts[dn[i]][v] if dn[i] and isinstance(v, int) else v)
        out.append(cur)
        prev = cur
    return out


def _d(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()


def norm(c: str) -> str:
    return re.sub(r"\s+COUNTY$", "", (c or "").strip().upper()).replace(".", "").replace("SAINT ", "ST ")


# ---------------------------------------------------------------- 2022 snapshots
RELEASE_SEED = "https://www.michigan.gov/sos/resources/news/2026/10/13/three-weeks-before-election-day-6-percent-of-voters-have-already-cast-their-ballot"


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def fetch_snapshots():
    """Download every weekly 2022 comparison spreadsheet linked from the SoS's 2026 press releases.
    The file names change from week to week (PRNov2022BallotStatsByJurisdiction_10_17_2022.xlsx,
    PRNov2022AV-BallotStats2022_10_24.xlsx, 10_31_2022_PRNov2022AVBallotStats.xlsx, ...), so links are
    read from the release pages instead of guessed. Saved as MI_2022_<2022 file date>.xlsx."""
    import html as _html
    INCOMING.mkdir(parents=True, exist_ok=True)
    have = {p.stem.split("_")[-1] for p in INCOMING.glob("MI_2022_*.xlsx")}
    try:
        seed = _get(RELEASE_SEED).decode("utf-8", "replace")
    except urllib.error.URLError as e:
        print(f"  could not read SoS releases ({e}); keeping existing 2022 snapshots")
        return
    pages = {RELEASE_SEED} | {"https://www.michigan.gov" + m for m in
                              re.findall(r'href="(/sos/resources/news/2026/1[01]/\d+/[^"#?]+)"', seed)}
    for page in sorted(pages):
        try:
            html_ = seed if page == RELEASE_SEED else _get(page).decode("utf-8", "replace")
        except urllib.error.URLError:
            continue
        for href in re.findall(r'href="([^"]+\.xlsx[^"]*)"', html_):
            name = href.split("/")[-1].split("?")[0]
            if "2022" not in name:
                continue
            m = (re.search(r"(\d{2})_(\d{2})_(2022)", name) or re.search(r"(2022)_(\d{2})_(\d{2})", name))
            if not m:
                continue
            g = m.groups()
            fd = date(2022, int(g[0]), int(g[1])) if g[2] == "2022" else date(2022, int(g[1]), int(g[2]))
            if fd.isoformat() in have:
                continue
            url = href if href.startswith("http") else "https://www.michigan.gov" + _html.unescape(href)
            try:
                data = _get(url)
            except urllib.error.URLError:
                continue
            if data[:2] == b"PK":                        # a real xlsx (missing files redirect to /sos/404)
                (INCOMING / f"MI_2022_{fd.isoformat()}.xlsx").write_bytes(data)
                have.add(fd.isoformat())
                print(f"  new 2022 snapshot: {name}")


def read_snapshots():
    """{count_date (file date + 1): {COUNTY: (returned, requested)}}"""
    out = {}
    for p in sorted(INCOMING.glob("MI_2022_*.xlsx")):
        fd = date.fromisoformat(p.stem.split("_")[-1])
        rows = list(openpyxl.load_workbook(p, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
        h = [str(x or "").upper() for x in rows[0]]
        # column names drift between weekly files ("APPS RETURNED" / "APPS RECEIVED")
        ic, ir = h.index("COUNTY"), h.index("BALLOTS RECEIVED")
        ia = next(i for i, x in enumerate(h) if x in ("APPS RETURNED", "APPS RECEIVED"))
        snap = Counter(), Counter()
        for r in rows[1:]:
            if r[ic]:
                snap[0][norm(r[ic])] += int(r[ir] or 0)
                snap[1][norm(r[ic])] += int(r[ia] or 0)
        out[fd + timedelta(days=1)] = {c: (snap[0][c], snap[1][c]) for c in snap[0]}
    return out


# ---------------------------------------------------------------- main
def _write(p: Path, header, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main():
    el = EDAY[2026].isoformat()
    av = _q("COUNTY_AV_BALLOT_COUNT", ["COUNTY_NAME", "COUNT_DATE"], ["AV_BALLOT_COUNT", "AV_BALLOT_SENT_COUNT"], el)
    ev = _q("COUNTY_IN_PERSON_EV_VOTE_COUNT_SUM", ["COUNTY_NAME", "COUNT_DATE"], ["IN_PERSON_VOTE_COUNT_RUNNING_TOTAL"], el)
    daily = defaultdict(lambda: [0, 0, 0])            # (county, date) -> returned, sent, ev
    for c, d, ret, sent in av:
        daily[(norm(c), _d(d))][0:2] = [int(ret or 0), int(sent or 0)]
    for c, d, n in ev:
        daily[(norm(c), _d(d))][2] = int(n or 0)
    if not daily:
        raise SystemExit("Michigan dashboard returned no 2026 rows")
    latest = max(d for _c, d in daily)
    counties = sorted({c for c, _d2 in daily})
    _write(OUT / "daily_2026.csv", ["county", "date", "returned", "sent", "ev_inperson"],
           sorted((c, d.isoformat(), *v) for (c, d), v in daily.items()))

    fetch_snapshots()
    snaps = read_snapshots()
    _write(OUT / "snapshots_2022.csv", ["count_date", "county", "returned", "requested"],
           sorted((d.isoformat(), c, *v) for d, s in snaps.items() for c, v in s.items()))

    # increments, so summing rows up to a date gives that date's running total (analytics/sameday.py)
    def increments(series):                          # {date: {county: cumulative}}
        prev, out = {}, []
        for d in sorted(series):
            for c, v in sorted(series[d].items()):
                if v != prev.get(c, 0):
                    out.append((c, "mail", d.isoformat(), v - prev.get(c, 0)))
                prev[c] = v
        return out
    s26 = defaultdict(dict)
    for (c, d), v in daily.items():
        s26[d][c] = v[0]
    _write(OUT / "early_2026.csv", ["county", "mode", "date", "ballots"], increments(s26))
    _write(OUT / "early_2022.csv", ["county", "mode", "date", "ballots"],
           increments({d: {c: v[0] for c, v in s.items()} for d, s in snaps.items()}))

    shift = EDAY[2026] - EDAY[2022]
    reached = [d for d in snaps if d + shift <= latest]
    cut = max(reached) + shift if reached else latest
    fips = {r["county_name"].upper(): r["county_fips"]
            for r in csv.DictReader((ROOT / "data" / "baseline" / "county_lean.csv").open(encoding="utf-8"))
            if r["state"] == "MI"}
    fips = {norm(k): v for k, v in fips.items()}
    miss = [c for c in counties if c not in fips]
    if miss:
        raise SystemExit(f"no FIPS for {miss}")
    cur = {c: daily[(c, cut)][0] for c in counties if (c, cut) in daily}
    _write(LIVE / "mi_current.csv", ["state", "county_fips", "ballots"], sorted(("MI", fips[c], v) for c, v in cur.items()))
    tot = lambda d, i: sum(daily[(c, d)][i] for c in counties if (c, d) in daily)
    # early in-person counts for the current day are posted only after it ends (the dashboard shows 0
    # until then), so report them for the latest day that has any
    ev_day = max((d for d in {d for _c, d in daily} if tot(d, 2) > 0), default=latest)
    meta = {"source": "Michigan SoS Voting Dashboard (absentee ballots returned)", "basis": "absentee returned",
            "as_of": cut.isoformat(), "ballots": sum(cur.values()), "pending": not reached,
            "latest": latest.isoformat(), "latest_returned": tot(latest, 0), "latest_sent": tot(latest, 1),
            "latest_ev": tot(ev_day, 2), "latest_ev_date": ev_day.isoformat()}
    if reached:
        meta["snapshot_2022"] = max(reached).isoformat()
    (LIVE / "mi_meta.json").write_text(json.dumps(meta, indent=1))

    vc = _q("COUNTY_VOTER_COUNT", ["COUNTY_NAME", "COUNT_DATE"], ["VOTER_COUNT"])
    if vc:
        last = max(_d(d) for _c, d, _n in vc)
        reg = {norm(c): int(n or 0) for c, d, n in vc if _d(d) == last}
        rp = ROOT / "data" / "reference" / "registration.csv"
        keep = [r for r in csv.DictReader(rp.open(encoding="utf-8")) if r["state"] != "MI"]
        keep += [{"state": "MI", "county_fips": fips[c], "county_name": c, "registered": n} for c, n in sorted(reg.items()) if c in fips]
        _write(rp, ["state", "county_fips", "county_name", "registered"], [list(r.values()) for r in keep])

    print(f"MI latest {latest}: {meta['latest_returned']:,} absentee returned, {meta['latest_sent']:,} sent, "
          f"{meta['latest_ev']:,} early in person through {meta['latest_ev_date']} ({len(counties)} counties)")
    print(f"  2022 snapshots: {[d.isoformat() for d in sorted(snaps)]}")
    if reached:
        s22 = sum(v[0] for v in snaps[max(reached)].values())
        print(f"  compare: 2026 {cut} {meta['ballots']:,} vs 2022 {max(reached)} {s22:,} = {meta['ballots'] / s22:.0%}")


if __name__ == "__main__":
    main()
