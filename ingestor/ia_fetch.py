"""
ia_fetch.py — Iowa absentee (= early) voting by congressional district, county and party.

In Iowa all early voting is absentee voting (by mail, at the county auditor's office, at
satellite sites, drop boxes), and voters register by party, so the Secretary of State's daily
"Absentee Ballot Statistics" reports show ballots RECEIVED by party (Republican / Democrat /
No Party / Other) for every county and congressional district.

Sources
  2026  The SoS daily PDFs (AbsenteeCounty2026.pdf, AbsenteeCongressional2026.pdf; the site refuses
        scripts, so the daily task fetches them in the browser: ingestor/ia_browser_return.js +
        ingestor/ia_save.py) saved as data/incoming/ia/sos/<kind>_<report date>.pdf, plus Bleeding
        Heartland's copies of each earlier 2026 report (data/incoming/ia/bh2026/, Oct 15-23).
  2022  Congressional district + statewide, EVERY report Oct 20 - Nov 8 2022: Bleeding Heartland's
        2022 tracker post, which reproduces each SoS report as tables by district, party and return
        method (data/incoming/ia/bh2022.html). The day's total = the sum of the method tables.
        County level only exists at three points (Internet Archive copies of AbsenteeCounty2022.pdf,
        report dates Oct 20, Nov 7 and Nov 9 2022, data/incoming/ia/arch2022/).

Dates: a report dated D holds ballots received through the night before (the 2026 PDFs say "Data
as of 08:00 on D"); everything here is keyed by REPORT date, and 2026 vs 2022 is lined up by days
before Election Day of the report date.

Outputs (counts only)
  data/ia_state/cd_{2022,2026}.csv       report_date, district, party, received
                                         (district = STATE or 1..4; party = R, D, NP, O)
  data/ia_county/county_{2022,2026}.csv  report_date, county, party, received
  data/ia_county/county_cd.csv           county, district   (whole counties; Iowa never splits them)

Run:  python ingestor/ia_fetch.py
"""
from __future__ import annotations

import csv
import glob
import html
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parent.parent
INC = ROOT / "data" / "incoming" / "ia"
OUT_S = ROOT / "data" / "ia_state"
OUT_C = ROOT / "data" / "ia_county"
PARTY = {"Republican": "R", "Democrat": "D", "No Party": "NP", "Other": "O"}
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"], 1)}


def _int(s):
    return int(s.replace(",", ""))


# ------------------------------------------------------------------ SoS PDFs
def parse_pdf(path: Path):
    """-> (report_date, {area: {party: received}}) for county or congressional PDFs, either layout.
    area = 'STATE', a county name (upper case), or '1'..'4' for congressional districts."""
    r = pypdf.PdfReader(str(path))
    pages = [p.extract_text() or "" for p in r.pages]
    head = pages[0]
    m = re.search(r"Data as of [\d:]+ on (\w+) (\d+), (\d{4})", head)
    if m:                                                    # new layout (from Oct 20 2026): one page per area
        rd = date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
        out = {}
        for t in pages:
            L = [l.strip() for l in t.split("\n") if l.strip()]
            try:
                i = next(k for k, l in enumerate(L) if re.search(r"\|\s+Page \d+", l))
            except StopIteration:
                continue
            name = L[i + 1]
            if "Received" not in L:
                continue
            j = L.index("Received", L.index("Ballot status"))
            vals = [_int(x) for x in L[j + 1:j + 6]]
            area = ("STATE" if name.startswith("Iowa Statewide") else
                    re.sub(r"\D", "", name) if name.startswith("United States Representative") else name.upper())
            out[area] = dict(zip(["R", "D", "NP", "O", "TOTAL"], vals))
        return rd, out
    # old layout (2022, and 2026 up to Oct 16): one long list
    text = "\n".join(pages)
    m = re.search(r"report date (\d+)/(\d+)/(\d{4})", text) or re.search(r"Data Pulled[^\n]*\n\s*(\d+)/(\d+)/(\d{4})", text)
    rd = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    out, cur = defaultdict(dict), None
    skip = ("Absentee Ballot", "County/", "Prepared by", "Data ", "report date", "November", "Grand Total",
            "Ballot not yet", "Counter", "Mail", "E-Mail", "Email", "Health Care", "Satellite", "Drop Box", "Fax",
            "In-Person", "In Person", "Mailing")
    for line in text.split("\n"):
        line = line.strip()
        mm = re.match(r"^(.*?)\s+(\d+)\s+(\d+)(?:\s+(\d+))?$", line)
        if not mm or line.startswith(skip):
            if line.startswith("Grand Total") and mm:
                out["STATE"]["TOTAL"] = int(mm.group(4) or 0)
            continue
        name, rec = mm.group(1).strip(), int(mm.group(4) or 0)
        if name in PARTY:
            if cur:
                out[cur][PARTY[name]] = rec
        elif not any(name.startswith(s.strip()) for s in skip):
            cur = re.sub(r"^United States Representative District\s*", "", name).upper()
            out[cur]["TOTAL"] = rec
    out = dict(out)
    if not any(p in out.get("STATE", {}) for p in PARTY.values()):      # old layout: statewide party totals
        st = defaultdict(int)
        for area, v in out.items():
            if area != "STATE":
                for p in PARTY.values():
                    st[p] += v.get(p, 0)
        out["STATE"] = {**st, "TOTAL": out.get("STATE", {}).get("TOTAL", sum(st.values()))}
    return rd, out


# ------------------------------------------------------------------ 2022 tracker tables
def bh2022():
    """{report_date: {district: {party: received}}} summed over the return-method tables."""
    s = (INC / "bh2022.html").read_text(encoding="utf-8", errors="replace")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    L = [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", t)).split("\n") if l.strip()]
    acc = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))      # summed method tables
    tot = {}                                                                 # stated totals, where given
    for i, l in enumerate(L):
        if l not in ("Congressional district", "District") or L[i + 1:i + 2] != ["Democrats"]:
            continue
        title = " ".join(L[max(0, i - 4):i])
        if "received" not in title or "November 16 report" in title:
            continue
        m = re.search(r"as of (\w+) (\d+), 2022", title)
        rd = date(2022, MONTHS[m.group(1)], int(m.group(2)))
        rows = {}
        k = i + 6
        while k + 5 <= len(L) and (L[k].startswith("IA-0") or L[k] == "statewide"):
            rows["STATE" if L[k] == "statewide" else L[k][-1]] = dict(zip(["D", "R", "NP", "O"], map(_int, L[k + 1:k + 5])))
            k += 6
        if "county auditors as of" in title:
            tot.setdefault(rd, rows)          # the stated all-methods total (first = latest version)
        else:
            for a, ps in rows.items():
                for p, v in ps.items():
                    acc[rd][a][p] += v
    out = {d: {a: dict(ps) for a, ps in acc[d].items()} for d in acc}
    for d, rows in tot.items():           # prefer stated totals (the method tables miss a few ballots)
        if d in out or d.month == 11:
            out[d] = rows
    return {d: out[d] for d in out if d.month == 10 or d <= date(2022, 11, 7)}


def county_cd():
    """Whole-county -> congressional district (119th Congress = 2021 map), from Census boundaries."""
    p = OUT_C / "county_cd.csv"
    if p.exists():
        return {r["county"]: r["district"] for r in csv.DictReader(p.open(encoding="utf-8"))}
    import shapefile
    from shapely.geometry import shape
    geo = ROOT / "data" / "raw" / "geo"
    cds = {}
    for sr in shapefile.Reader(str(next(geo.glob("cb_*_us_cd11[89]_500k/*.shp")))).iterShapeRecords():
        if sr.record["STATEFP"] == "19":
            cds[str(int(sr.record[next(f[0] for f in sr.record.as_dict().items() if f[0].startswith("CD1"))]))] = \
                shape(sr.shape.__geo_interface__).buffer(0)
    out = {}
    for sr in shapefile.Reader(str(geo / "cb_2024_us_county_500k" / "cb_2024_us_county_500k")).iterShapeRecords():
        if sr.record["STATEFP"] == "19":
            g = shape(sr.shape.__geo_interface__).buffer(0)
            out[sr.record["NAME"].upper()] = max(cds, key=lambda d: cds[d].intersection(g).area)
    OUT_C.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["county", "district"])
        w.writerows(sorted(out.items()))
    return out


def _write(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main():
    cd26, co26, co22 = {}, {}, {}
    pdfs = sorted(set(glob.glob(str(INC / "bh2026" / "*.pdf")) + glob.glob(str(INC / "sos" / "*.pdf")) +
                      glob.glob(str(INC / "arch2022" / "AbsenteeCounty2022_*.pdf"))))
    for f in pdfs:
        name = Path(f).name
        if "Senate" in name or "House" in name:
            continue
        rd, data = parse_pdf(Path(f))
        target = (cd26 if "Congressional" in name else co26) if rd.year == 2026 else (co22 if "County" in name else None)
        if target is not None:
            target[rd] = data
    cd22 = bh2022()
    _write(OUT_S / "cd_2022.csv", ["report_date", "district", "party", "received"],
           [(d.isoformat(), a, p, v) for d in sorted(cd22) for a in sorted(cd22[d]) for p, v in cd22[d][a].items()])
    _write(OUT_S / "cd_2026.csv", ["report_date", "district", "party", "received"],
           [(d.isoformat(), a, p, v) for d in sorted(cd26) for a in sorted(cd26[d])
            for p, v in cd26[d][a].items() if p != "TOTAL"])
    for yr, data in ((2022, co22), (2026, co26)):
        _write(OUT_C / f"county_{yr}.csv", ["report_date", "county", "party", "received"],
               [(d.isoformat(), a, p, v) for d in sorted(data) for a in sorted(data[d]) if a != "STATE"
                for p, v in data[d][a].items() if p != "TOTAL"])
    county_cd()
    for yr, cd in ((2022, cd22), (2026, cd26)):
        last = max(cd)
        print(f"IA {yr}: {len(cd)} district reports ({min(cd)} .. {last}); latest statewide received "
              f"{sum(cd[last]['STATE'].get(p, 0) for p in ('R', 'D', 'NP', 'O')):,}")
    print(f"IA county reports: 2022 {sorted(d.isoformat() for d in co22)}; 2026 {sorted(d.isoformat() for d in co26)}")


if __name__ == "__main__":
    main()
