"""
tx_districts.py — Texas congressional / State House / State Senate early-vote
aggregates (mail and in-person), plus a surname-based estimate of Hispanic and
Asian early voters.

INPUTS (data/incoming/tx/, gitignored)
  tx_ev_2022.json, tx_ev_2024.json
      Counts already reduced in the browser from the Secretary of State's daily
      statewide early-voting rosters (earlyvoting.texas-election.com):
      {"days": {"2024-10-21": {"rows": [[county, precinct, method, n, hisp_est, asian_est], ...]}}}
  2026/*.csv
      The 2026 daily statewide rosters, downloaded by hand from the SoS early-voting
      site (goelect.txelections.civixapps.com/ivis-evr-ui/evr → "Generate Statewide
      Report"), one file per early-voting day. Columns are found by name (county,
      voter name, voting method, precinct); the date comes from the file name
      (…EarlyVoting.2026-10-19.csv) or from the --date argument.
  The rosters carry NO race, age or party. Hispanic / Asian are ESTIMATES: each
  voter's surname is looked up in the Census 2010 surname table (share of people
  with that surname who are Hispanic / Asian-Pacific Islander) and the shares are
  summed. Names are used only for that lookup and never written out.

PRECINCT → DISTRICT (Texas Legislative Council, data.capitol.texas.gov)
  data/raw/tlc/Precincts{22G,24G,26P}_Districts.*   precinct → House (PLANH2316),
      Senate (PLANS2168) and, for 2026 precincts, Congress (PLANC2333, the 2025 map)
  data/raw/tlc/PLANC2333_r365_Prec24G.xls             2024 precincts → 2025 congressional map
  House and Senate lines are unchanged since 2022 → compared with 2022.
  Congressional lines were redrawn in 2025 → compared with 2024 (re-tallied on the new lines).
  Votes whose precinct code can't be matched (~1%) are shared out within their county
  in proportion to that county's matched votes.

OUTPUTS (data/tx_districts/, committed) — same shape as GA / NC:
  early_{year}.csv   county, chamber, district, mode, days_out, ballots
  demo_{year}.csv    chamber, district, dim, group, days_out, ballots   (dim = surname)
  redraw.csv         chamber, district, matched, same_pct

Run:  python ingestor/tx_districts.py            (all years)
      python ingestor/tx_districts.py 2026       (after adding today's roster)
"""
from __future__ import annotations

import csv
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

import openpyxl
import xlrd

ROOT = Path(__file__).resolve().parent.parent
INCOMING = ROOT / "data" / "incoming" / "tx"
TLC = ROOT / "data" / "raw" / "tlc"
OUT = ROOT / "data" / "tx_districts"
SURNAMES = ROOT / "web" / "tx" / "surnames.txt"

ELECTION_DAY = {2022: date(2022, 11, 8), 2024: date(2024, 11, 5), 2026: date(2026, 11, 3)}
CHAMBERS = ("house", "senate", "congress")


# ------------------------------------------------------------------ precincts
def pcands(p: str):
    """Possible spellings of a roster precinct code in the TLC tables."""
    p = str(p).strip().upper()
    a = re.sub(r"[^A-Z0-9-]", "", p)
    b = a.replace("-", "")
    out = [a.zfill(4), b.zfill(4), a, b]
    m = re.match(r"0*(\d+)-(\d+)$", a)                    # "2-2" -> "02-2"
    if m:
        out.append(f"{int(m.group(1)):02d}-{m.group(2)}")
    m = re.match(r"0*(\d+)", b)                           # "43 MAC" -> "0043"
    if m:
        out.append(m.group(1).zfill(4))
    m = re.match(r"0*(\d+)([A-Z]+)$", b)                  # "1B" -> "001B"
    if m:
        out += [m.group(1).zfill(3) + m.group(2), m.group(1).zfill(4 - len(m.group(2))) + m.group(2)]
    return out


def _rows(path: Path):
    if path.suffix == ".xls":
        s = xlrd.open_workbook(path, logfile=open(__import__("os").devnull, "w")).sheet_by_index(0)
        return [s.row_values(i) for i in range(s.nrows)]
    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def load_xwalk(year: int):
    """{(COUNTY, PREC): [ {house, senate, congress}, ... ]}  (several rows = split precinct)."""
    f = {2022: "Precincts22G_Districts.xlsx", 2024: "Precincts24G_Districts.xlsx", 2026: "Precincts26P_Districts.xls"}[year]
    rows = _rows(TLC / f)
    h = [str(x) for x in rows[0]]
    ix = {k: next((i for i, c in enumerate(h) if c.upper().startswith(k)), None)
          for k in ("FENAME", "PREC", "PLANH", "PLANS", "PLANC2333")}
    if ix["FENAME"] is None:                          # 2022 file calls it COUNTY
        ix["FENAME"] = h.index("COUNTY")
    out = defaultdict(list)
    for r in rows[1:]:
        if not r[ix["FENAME"]]:
            continue
        k = (str(r[ix["FENAME"]]).strip().upper(), str(r[ix["PREC"]]).strip().upper())
        d = {"house": str(int(r[ix["PLANH"]])), "senate": str(int(r[ix["PLANS"]]))}
        if ix["PLANC2333"] is not None and r[ix["PLANC2333"]] not in (None, ""):
            d["congress"] = str(int(r[ix["PLANC2333"]]))
        out[k].append(d)
    if year == 2024:          # 2024 precincts on the 2025 congressional map (Red-365 report)
        cd, county = defaultdict(list), None
        for r in _rows(TLC / "PLANC2333_r365_Prec24G.xls"):
            v = [x for x in r if x not in ("", None)]
            if len(v) == 1 and isinstance(v[0], str) and v[0].strip() and not v[0].startswith(" "):
                county = v[0].replace("*", "").strip().upper()      # "Harris *" = county split between districts
            elif len(v) == 2 and isinstance(v[0], str) and county:
                cd[(county, v[0].strip().upper())].append(str(int(v[1])))
        for k, rows_ in out.items():
            cds = next((cd[(k[0], c)] for c in pcands(k[1]) if (k[0], c) in cd), None)
            if cds:
                for i, d in enumerate(rows_):
                    d["congress"] = cds[i % len(cds)]
    return out


# ------------------------------------------------------------------ surnames
SUF = {"JR", "SR", "II", "III", "IV", "V"}


def load_surnames():
    sn, other = {}, (0.1367, 0.0797)
    for line in SURNAMES.read_text(encoding="utf-8").splitlines():
        n, h, a = line.split(",")
        if n.startswith("#"):
            other = (float(h) / 100, float(a) / 100)
        else:
            sn[n] = (float(h) / 100, float(a) / 100)
    return sn, other


def surname_p(last: str, sn, other):
    s = re.sub(r"[^A-Z \-']", "", last.upper()).strip()
    toks = [t for t in re.split(r"[ \-]+", s) if t and t not in SUF]
    for k in ("".join(toks).replace("'", ""), toks[0] if toks else "", toks[-1] if toks else ""):
        if k and k in sn:
            return sn[k]
    return other


# ------------------------------------------------------------------ inputs
def days_from_json(year: int):
    p = INCOMING / f"tx_ev_{year}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {day: v["rows"] for day, v in d["days"].items()}


def days_from_csv(year: int):
    """Raw daily rosters (2026). Reduced here to the same rows as the browser JSON."""
    sn, other = load_surnames()
    out = {}
    for f in sorted(glob.glob(str(INCOMING / str(year) / "*.csv"))):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(f).name) or re.search(r"(\d{2})[._-](\d{2})[._-](\d{4})", Path(f).name)
        if not m:
            print(f"skip {f}: no date in file name")
            continue
        day = m.group(1) if len(m.groups()) == 1 else f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        agg = defaultdict(lambda: [0, 0.0, 0.0])
        with open(f, encoding="utf-8-sig", errors="replace", newline="") as fh:
            r = csv.reader(fh)
            hdr = [c.strip().upper() for c in next(r)]
            col = lambda *keys: next(i for i, c in enumerate(hdr) if any(k in c for k in keys))
            ci, ni, mi, pi = col("COUNTY"), col("NAME"), col("METHOD", "TYPE"), col("PRECINCT", "PCT")
            for row in r:
                if len(row) <= max(ci, ni, mi, pi):
                    continue
                h, a = surname_p(row[ni].split(",")[0], sn, other)
                k = (row[ci].strip().upper(), row[pi].strip(), "mail" if "MAIL" in row[mi].upper() else "inperson")
                v = agg[k]
                v[0] += 1; v[1] += h; v[2] += a
        out[day] = [[*k, v[0], v[1], v[2]] for k, v in agg.items()]
        print(f"{Path(f).name}: {sum(v[0] for v in agg.values()):,} voters")
    return out


# ------------------------------------------------------------------ main
def aggregate(year: int):
    days = days_from_json(year) or days_from_csv(year)
    if not days:
        return None
    xw = load_xwalk(year)
    eday = ELECTION_DAY[year]
    early, demo = Counter(), Counter()
    unmatched = []                                  # (county, mode, days_out, n, h, a)
    no_cd = []                                      # matched precinct, but no congressional district
    cd_mix = defaultdict(Counter)                   # county -> Counter(congressional district)
    county_mix = defaultdict(Counter)               # county -> Counter(district-triple)
    tot = hit = 0
    for day, rows in days.items():
        days_out = (eday - date.fromisoformat(day)).days
        if days_out < 0:
            continue
        for county, prec, mode, n, h, a in rows:
            county = county.strip().upper()
            mode = "mail" if str(mode).lower().startswith("mail") else "inperson"
            tot += n
            match = next((xw[(county, k)] for k in pcands(prec) if (county, k) in xw), None)
            if not match:
                unmatched.append((county, mode, days_out, n, h, a))
                continue
            hit += n
            share = 1 / len(match)
            for d in match:
                trip = tuple(d.get(ch) for ch in CHAMBERS)
                county_mix[county][trip] += n * share
                _add(early, demo, county, d, mode, days_out, n * share, h * share, a * share)
                if d.get("congress"):
                    cd_mix[county][d["congress"]] += n * share
                elif year != 2022:                  # 2022 isn't used for congressional comparisons
                    no_cd.append((county, mode, days_out, n * share, h * share, a * share))
    for county, mode, days_out, n, h, a in unmatched:       # share out within the county
        mix = county_mix.get(county)
        if not mix:
            continue
        s = sum(mix.values())
        for trip, w in mix.items():
            f = w / s
            _add(early, demo, county, dict(zip(CHAMBERS, trip)), mode, days_out, n * f, h * f, a * f)
    for county, mode, days_out, n, h, a in no_cd:           # congressional district from the county's mix
        mix = cd_mix.get(county)
        if not mix:
            continue
        s = sum(mix.values())
        for cdn, w in mix.items():
            f = w / s
            _add(early, demo, county, {"congress": cdn}, mode, days_out, n * f, h * f, a * f)
    print(f"{year}: {tot:,} early/mail voters; precinct matched {hit / tot:.1%}; "
          f"congressional district from county mix for {sum(x[3] for x in no_cd) / max(tot, 1):.1%}")
    return early, demo


def _add(early, demo, county, d, mode, days_out, n, h, a):
    for ch in CHAMBERS:
        dist = d.get(ch)
        if not dist:
            continue
        early[(county, ch, dist, mode, days_out)] += n
        demo[(ch, dist, "surname", "Hispanic (est.)", days_out)] += h
        demo[(ch, dist, "surname", "Asian (est.)", days_out)] += a
        demo[(ch, dist, "surname", "All others (est.)", days_out)] += n - h - a


def _write(p: Path, header, rows):
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main(years):
    OUT.mkdir(parents=True, exist_ok=True)
    for y in years:
        res = aggregate(y)
        if not res:
            print(f"{y}: no input found")
            continue
        early, demo = res
        _write(OUT / f"early_{y}.csv", ["county", "chamber", "district", "mode", "days_out", "ballots"],
               sorted((*k, round(v)) for k, v in early.items() if round(v)))
        _write(OUT / f"demo_{y}.csv", ["chamber", "district", "dim", "group", "days_out", "ballots"],
               sorted((*k, round(v)) for k, v in demo.items() if round(v)))
    # House / Senate lines unchanged since 2022; congressional lines redrawn in 2025.
    dists = {ch: set() for ch in CHAMBERS}
    for d in load_xwalk(2026).values():
        for x in d:
            for ch in CHAMBERS:
                if x.get(ch):
                    dists[ch].add(x[ch])
    _write(OUT / "redraw.csv", ["chamber", "district", "matched", "same_pct"],
           [(ch, d, 0, 1.0 if ch != "congress" else 0.0)
            for ch in CHAMBERS for d in sorted(dists[ch], key=int)])


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or sorted(ELECTION_DAY))
