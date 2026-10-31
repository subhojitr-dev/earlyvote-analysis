"""
build_dashboard.py -- generate a self-contained, deployable HTML dashboard from
the early-vote performance matrix. Excel-like: sortable columns, search/group
filter, two table views (partisan shift / turnout progress), conditional color,
state tabs, plus aggregate panels (partisan trajectory + turnout progress bars).

No backend, no build step, no dependencies: it writes ONE static file
(web/index.html) with the data baked in. Deploy on any static host (Vercel,
GitHub Pages, Netlify) or just double-click to open locally.

Run:  python web/build_dashboard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analytics"))
from turnout_compare import (compare, group_deviation, composite_lean,   # noqa: E402
                             turnout_progress, turnout_rate, sameday_info)
from performance_matrix import overall_turnout, SPLIT             # noqa: E402

STATES = ["GA", "TX", "NC", "PA", "FL", "SC", "OH", "IA", "KS", "MI", "ME", "NV"]
WAITING = {"SC"}   # real feed wired, but the state hasn't posted 2026 data yet -> notice, never synthetic


def fix2022_note(state):
    """Plain-English note when the 2022 comparison file had holes we estimated (GA)."""
    p = Path(__file__).resolve().parent.parent / "data" / f"{state.lower()}_county" / "fix2022.json"
    if not p.exists():
        return ""
    import json as _j
    from datetime import date as _d
    fx = _j.loads(p.read_text(encoding="utf-8"))
    md = lambda s: _d.fromisoformat(s).strftime("%b ") + str(_d.fromisoformat(s).day)
    parts = [f"{c.title()} ({md(i['days'][0])} &ndash; {md(i['days'][1])})" for c, i in sorted(fx.items())]
    return ("2022 note: the Secretary of State's 2022 file is missing most early in-person votes for "
            + " and ".join(parts) + ". Those days are estimated so each county matches its certified 2022 total.")


def nv_info():
    """Nevada: in-person early votes (daily, by county and party) and mail ballots returned (current
    snapshot) from the SoS VIVID dashboard, vs the SoS 2022 weekly reports (end of early-voting week 1
    and week 2). Data: ingestor/nv_fetch.py."""
    import csv as _csv
    from collections import defaultdict as _dd
    from datetime import date as _d, timedelta as _td
    root = Path(__file__).resolve().parent.parent / "data" / "nv_county"
    if not (root / "inperson_2026.csv").exists():
        return {"waiting": True}
    E = {2022: _d(2022, 11, 8), 2026: _d(2026, 11, 3)}
    ref = _dd(lambda: _dd(lambda: _dd(dict)))                 # point -> mode -> county -> party
    for r in _csv.DictReader((root / "ref_2022.csv").open(encoding="utf-8")):
        ref[r["point"]][r["mode"]][r["county"]][r["party"]] = int(r["ballots"])
    ip = _dd(lambda: _dd(lambda: _dd(int)))                  # date -> county -> party
    for r in _csv.DictReader((root / "inperson_2026.csv").open(encoding="utf-8")):
        ip[r["date"]][r["county"]][r["party"]] += int(r["ballots"])
    mail = _dd(lambda: _dd(dict))                            # snapshot -> county -> party
    for r in _csv.DictReader((root / "mail_2026.csv").open(encoding="utf-8")):
        mail[r["snapshot"]][r["county"]][r["party"]] = int(r["received"])
    days = sorted(ip)
    last_full = days[-2] if len(days) > 1 else days[-1]       # the newest day is still being counted
    # latest 2022 point that 2026 has reached (same days before Election Day)
    pts = [p for p in sorted(ref) if (E[2026] - _td(days=(E[2022] - _d.fromisoformat(p)).days)).isoformat() <= last_full]
    point = pts[-1] if pts else None
    p26 = (E[2026] - _td(days=(E[2022] - _d.fromisoformat(point)).days)).isoformat() if point else None

    def cum(upto):
        out = _dd(lambda: _dd(int))
        for d in days:
            if d <= upto:
                for c, ps in ip[d].items():
                    for k, v in ps.items():
                        out[c][k] += v
        return out
    ip_pt = cum(p26) if point else {}
    ip_now = cum(last_full)
    snap = max(mail)
    msnap_pt = max((s for s in mail if p26 and s <= (_d.fromisoformat(p26) + _td(days=1)).isoformat()), default=None)
    final22 = max(ref)

    def st(ps):
        t = sum(ps.values()) or 1
        return {"n": sum(ps.values()), "D": ps.get("D", 0) / t, "R": ps.get("R", 0) / t, "O": ps.get("O", 0) / t}

    def tot(dct):
        out = _dd(int)
        for ps in dct.values():
            for k, v in ps.items():
                out[k] += v
        return out
    counties = []
    for c in sorted(set(ip_now) | set(ref[final22]["inperson"])):
        counties.append({"county": c.title(),
                         "ip_pt": st(ip_pt.get(c, {})) if point else None,
                         "ip22": st(ref[point]["inperson"].get(c, {})) if point else None,
                         "ip_now": st(ip_now.get(c, {})),
                         "mail_now": st(mail[snap].get(c, {})),
                         "mail22_final": st({k: ref[final22]["mail"][c].get(k, 0) for k in "DRO"} if c in ref[final22]["mail"] else {})})
    return {"nv": True, "as_of": last_full, "point22": point, "point26": p26,
            "ip_pt": st(tot(ip_pt)) if point else None, "ip22": st(tot(ref[point]["inperson"])) if point else None,
            "ip_now": st(tot(ip_now)), "mail_now": st(tot(mail[snap])), "mail_snap": snap,
            "mail_pt": st(tot(mail[msnap_pt])) if msnap_pt and point and point != min(ref) else None,
            "mail22_pt": st(tot(ref[point]["mail"])) if point else None,
            "mail22_final": st(tot(ref[final22]["mail"])), "ip22_final": st(tot(ref[final22]["inperson"])),
            "final22": final22, "counties": counties}


def ia_info():
    """Iowa: absentee (= early) ballots received by party, by congressional district (same day as
    2022, from every 2022 report) and county (2026 only + progress vs 2022's full early vote, since
    2022 county numbers exist only as a few snapshots). Data: ingestor/ia_fetch.py."""
    import csv as _csv
    from collections import defaultdict as _dd
    from datetime import date as _d
    root = Path(__file__).resolve().parent.parent
    if not (root / "data" / "ia_state" / "cd_2026.csv").exists():
        return {"waiting": True}
    E = {2022: _d(2022, 11, 8), 2026: _d(2026, 11, 3)}

    def load(p, key):
        out = _dd(lambda: _dd(dict))
        for r in _csv.DictReader(p.open(encoding="utf-8")):
            out[_d.fromisoformat(r["report_date"])][r[key]][r["party"]] = int(r["received"])
        return out
    cd26, cd22 = load(root / "data/ia_state/cd_2026.csv", "district"), load(root / "data/ia_state/cd_2022.csv", "district")
    co26, co22 = load(root / "data/ia_county/county_2026.csv", "county"), load(root / "data/ia_county/county_2022.csv", "county")
    cmap = {r["county"]: r["district"] for r in _csv.DictReader((root / "data/ia_county/county_cd.csv").open(encoding="utf-8"))}
    rd = max(cd26)
    out26 = (E[2026] - rd).days
    # latest 2022 report at or before the same number of days out (Iowa posts no weekend reports)
    rd22 = max(d for d in cd22 if (E[2022] - d).days >= out26)
    rd26 = max(d for d in cd26 if (E[2026] - d).days >= (E[2022] - rd22).days)

    def stats(ps):
        t = sum(ps.values()) or 1
        return {"n": sum(ps.values()), "D": ps.get("D", 0) / t, "R": ps.get("R", 0) / t, "NP": ps.get("NP", 0) / t}
    districts = [{"area": a, "now": stats(cd26[rd26][a]), "then": stats(cd22[rd22][a])}
                 for a in ["STATE", "1", "2", "3", "4"]]
    rdc = max(co26)
    fin22 = max(co22)
    counties = []
    for c in sorted(co26[rdc]):
        now, f22 = stats(co26[rdc][c]), stats(co22[fin22].get(c, {}))
        counties.append({"county": c.title(), "cd": cmap.get(c), "now": now, "final22": f22,
                         "progress": now["n"] / f22["n"] if f22["n"] else None})
    daily = [[d.isoformat(), sum(cd26[d]["STATE"].values()), cd26[d]["STATE"].get("D", 0), cd26[d]["STATE"].get("R", 0)]
             for d in sorted(cd26)]
    return {"ia": True, "as_of": rd.isoformat(), "county_as_of": rdc.isoformat(), "cmp26": rd26.isoformat(),
            "cmp22": rd22.isoformat(), "days_out": (E[2022] - rd22).days, "districts": districts,
            "counties": counties, "final22": fin22.isoformat(), "daily": daily}


def turnout_compare_hist(state):
    from turnout_compare import series_by_year_county
    return series_by_year_county(state)


def ks_info():
    """Kansas: statewide-only advance voting (ingestor/ks_fetch.py); no county or party breakdown."""
    import csv as _csv
    base = Path(__file__).resolve().parent.parent / "data" / "ks_state"
    p = base / "daily_2026.csv"
    if not p.exists():
        return {"waiting": True}
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestor"))
    from ks_fetch import compare as _cmp, REF_2022
    from datetime import date as _d
    daily = [(_d.fromisoformat(r["date"]), int(r["sent"]), int(r["returned"]), int(r["inperson"]))
             for r in _csv.DictReader(p.open(encoding="utf-8"))]
    last = daily[-1]
    final22 = min(REF_2022, key=lambda r: r[0])
    return {"ks": True, "as_of": last[0].isoformat(), "inperson": last[3], "returned": last[2], "sent": last[1],
            "daily": [[d.isoformat(), s, r, i] for d, s, r, i in daily], "cmp": _cmp(daily),
            "ref22": [{"days_out": o, "sent": se, "returned": r, "inperson": i, "source": src} for o, se, r, i, src in REF_2022],
            "final22": {"days_out": final22[0], "total": final22[2] + final22[3]}}


def party_info(state):
    """Early voters by REGISTERED party, 2026 vs 2022 at the same number of days before Election Day
    (registration of the people who voted, not votes cast). NC / ME: district demo files (congressional
    rows, party dimension); PA: data.pa.gov party files; FL: DOS county snapshots (2022 interpolated
    between Internet Archive copies)."""
    import csv as _csv
    from collections import Counter as _C
    from datetime import date as _d, timedelta as _td
    root = Path(__file__).resolve().parent.parent / "data"
    E = {2022: _d(2022, 11, 8), 2026: _d(2026, 11, 3)}
    out26, out22, asof, days_out = _C(), _C(), None, None
    try:
        if state in ("NC", "ME"):
            rows = [r for r in _csv.DictReader((root / f"{state.lower()}_districts" / "demo_2026.csv").open(encoding="utf-8"))
                    if r["dim"] == "party" and r["chamber"] == "congress"]
            # data runs through the live file's as-of day; a stray ballot dated later (a partial
            # day) must not pull the comparison a day further into 2022
            import json as _j
            meta_asof = _j.loads((root / "live" / f"{state.lower()}_meta.json").read_text())["as_of"]
            days_out = (E[2026] - _d.fromisoformat(meta_asof)).days
            for r in rows:
                if int(r["days_out"]) >= days_out:
                    out26[r["group"]] += int(r["ballots"])
            for r in _csv.DictReader((root / f"{state.lower()}_districts" / "demo_2022.csv").open(encoding="utf-8")):
                if r["dim"] == "party" and r["chamber"] == "congress" and int(r["days_out"]) >= days_out:
                    out22[r["group"]] += int(r["ballots"])
            asof = (E[2026] - _td(days=days_out)).isoformat()
        elif state == "PA":
            import json as _j
            asof = _j.loads((root / "live" / "pa_meta.json").read_text())["as_of"]
            days_out = (E[2026] - _d.fromisoformat(asof)).days
            cut22 = (E[2022] - _td(days=days_out)).isoformat()
            names = {"D": "Democrat", "R": "Republican", "O": "Other / no party"}
            for y, cut, acc in ((2026, asof, out26), (2022, cut22, out22)):
                for r in _csv.DictReader((root / "pa_county" / f"party_{y}.csv").open(encoding="utf-8")):
                    if r["date"] <= cut:
                        acc[names[r["party"]]] += int(r["ballots"])
        elif state == "FL":
            names = {"D": "Democrat", "R": "Republican", "N": "No party", "O": "Other party"}
            snaps = {}
            for y in (2026, 2022):
                snaps[y] = {}
                for r in _csv.DictReader((root / "fl_county" / f"snapshots_{y}.csv").open(encoding="utf-8")):
                    snaps[y].setdefault(r["through"], _C())[names.get(r["party"], "Other party")] += int(r["cumulative"])
            asof = max(snaps[2026])
            out26 = snaps[2026][asof]
            days_out = (E[2026] - _d.fromisoformat(asof)).days
            t = E[2022] - _td(days=days_out)
            ds = sorted(_d.fromisoformat(k) for k in snaps[2022])
            lo = max(d for d in ds if d <= t)
            hi = min((d for d in ds if d >= t), default=lo)
            w = 0 if hi == lo else (t - lo).days / (hi - lo).days       # straight-line between archive copies
            for k in set(snaps[2022][lo.isoformat()]) | set(snaps[2022][hi.isoformat()]):
                out22[k] = round(snaps[2022][lo.isoformat()].get(k, 0) * (1 - w) + snaps[2022][hi.isoformat()].get(k, 0) * w)
        else:
            return None
    except (FileNotFoundError, KeyError, ValueError):
        return None
    if not out26 or not out22:
        return None
    n26, n22 = sum(out26.values()), sum(out22.values())
    order = ["Democrat", "Republican"] + sorted(k for k in set(out26) | set(out22) if k not in ("Democrat", "Republican"))
    return {"as_of": asof, "days_out": days_out, "d22": (E[2022] - _td(days=days_out)).isoformat(),
            "n26": n26, "n22": n22,
            "rows": [{"party": k, "now": out26.get(k, 0) / n26, "then": out22.get(k, 0) / n22, "n": out26.get(k, 0)}
                     for k in order if out26.get(k, 0) or out22.get(k, 0)]}


def ga_demo_info():
    """Georgia early voters by race, gender and age, statewide, 2026 vs 2022 on the same day of early
    voting. Georgia Votes joins the SoS early-vote file to the voter list (which records race/gender/age):
    2026 = today's snapshot (ingestor/ga_demographics.py); 2022 = Internet Archive copies of its home page
    (ingestor/ga_demo_2022.py). Dates are the site's 'Last updated' dates; counts run through the day before."""
    import csv as _csv
    from collections import defaultdict as _dd
    from datetime import date as _d, timedelta as _td
    root = Path(__file__).resolve().parent.parent / "data" / "ga_districts"
    try:
        now, asof = _dd(dict), None
        for r in _csv.DictReader((root / "gv_demo_2026.csv").open(encoding="utf-8")):
            if r["chamber"] == "state":
                now[r["dim"]][r["group"]] = int(r["ballots"])
                asof = r["asof"]
        old = _dd(lambda: _dd(dict))
        for r in _csv.DictReader((root / "gv_demo_2022_state.csv").open(encoding="utf-8")):
            old[r["asof"]][r["dim"]][r["group"]] = int(r["ballots"])
    except (FileNotFoundError, KeyError):
        return None
    if not asof or not old:
        return None
    # same day of early voting: 2026 opened Tue Oct 13, 2022 opened Mon Oct 17
    want = (_d.fromisoformat(asof) - (_d(2026, 10, 13) - _d(2022, 10, 17))).isoformat()
    have = [k for k in sorted(old) if k <= want]
    if not have:
        return None
    then = old[have[-1]]
    order = {"race": ["White", "Black", "Hispanic", "Asian", "Other"], "gender": ["Women", "Men"],
             "age": ["18-29", "30-39", "40-49", "50-64", "65+"]}
    through = lambda k: (_d.fromisoformat(k) - _td(days=1)).isoformat()
    return _demo_out(now, then, order, through(asof), through(have[-1]),
                     [("Black voters", "race", ["Black"]), ("Women", "gender", ["Women"]), ("Under 40", "age", ["18-29", "30-39"])],
                     "Race, gender and age come from the state voter list (race is self-reported at registration; &ldquo;Other&rdquo; includes not stated), "
                     "joined to the early-vote file by <a href=\"https://georgiavotes.com\" target=\"_blank\" rel=\"noopener\" style=\"color:var(--accent)\">Georgia Votes</a>; "
                     "2022 from Internet Archive copies of its daily page. District-level breakdowns are on the "
                     "<a href=\"/ga/\" style=\"color:var(--accent)\">Georgia district page</a>.")


def _demo_out(now, then, order, through26, through22, headline, note, title=None):
    """Shared shape for the 'who is voting early' card: shares of each group, 2026 vs 2022."""
    TITLES = {"race": "Race", "gender": "Gender", "age": "Age", "surname": "Surname estimate"}
    dims = []
    for dim, groups in order.items():
        n26, n22 = sum(now[dim].values()), sum(then[dim].values())
        if not n26 or not n22:
            return None
        dims.append({"title": TITLES.get(dim, dim), "rows": [
            {"group": g, "now": now[dim].get(g, 0) / n26, "then": then[dim].get(g, 0) / n22, "n": now[dim].get(g, 0)}
            for g in groups]})
    share = lambda src, dim, gs: sum(src[dim].get(g, 0) for g in gs) / (sum(src[dim].values()) or 1)
    first = next(iter(order))
    return {"title": title, "through26": through26, "through22": through22,
            "n26": sum(now[first].values()), "n22": sum(then[first].values()), "dims": dims, "note": note,
            "headline": [{"label": lab, "now": share(now, dim, gs), "then": share(then, dim, gs)} for lab, dim, gs in headline]}


def district_demo_info(state):
    """NC (race, gender, age from the voter record) and TX (surname-based Hispanic / Asian estimate):
    statewide make-up of early voters, 2026 vs 2022 at the same number of days before Election Day.
    Data: data/{st}_districts/demo_{year}.csv, congressional rows (each voter counted once), cut at the
    latest complete day (live/{st}_meta.json)."""
    import csv as _csv
    import json as _j
    from collections import defaultdict as _dd
    from datetime import date as _d, timedelta as _td
    root = Path(__file__).resolve().parent.parent / "data"
    E = {2022: _d(2022, 11, 8), 2026: _d(2026, 11, 3)}
    try:
        asof = _j.loads((root / "live" / f"{state.lower()}_meta.json").read_text())["as_of"]
        out = (E[2026] - _d.fromisoformat(asof)).days
        got = {}
        for y in (2026, 2022):
            acc = _dd(lambda: _dd(int))
            for r in _csv.DictReader((root / f"{state.lower()}_districts" / f"demo_{y}.csv").open(encoding="utf-8")):
                if r["chamber"] == "congress" and r["dim"] != "party" and int(r["days_out"]) >= out:
                    acc[r["dim"]][r["group"]] += int(r["ballots"])
            got[y] = acc
    except (FileNotFoundError, KeyError, ValueError):
        return None
    through22 = (E[2022] - _td(days=out)).isoformat()
    if state == "NC":
        ages = sorted(got[2026]["age"], key=lambda g: (g == "Not stated", g))
        order = {"race": ["White", "Black", "Hispanic", "Asian", "Other / multiracial"], "gender": ["Women", "Men"],
                 "age": [g for g in ages if g != "Not stated"]}
        young = [g for g in ages if g.startswith("18")]
        return _demo_out(got[2026], got[2022], order, asof, through22,
                         [("Black voters", "race", ["Black"]), ("Women", "gender", ["Women"]), ("Ages 18&ndash;29", "age", young)],
                         "Race, gender and age come from each voter&rsquo;s registration record in the NC State Board of Elections absentee file "
                         "(race is self-reported; shares include voters who did not state one). District-level breakdowns are on the "
                         "<a href=\"/nc/\" style=\"color:var(--accent)\">North Carolina district page</a>.")
    if state == "TX":
        order = {"surname": ["Hispanic (est.)", "Asian (est.)", "All others (est.)"]}
        return _demo_out(got[2026], got[2022], order, asof, through22,
                         [("Hispanic (est.)", "surname", ["Hispanic (est.)"]), ("Asian (est.)", "surname", ["Asian (est.)"])],
                         "<b>An estimate:</b> Texas records no race. Each early voter&rsquo;s surname is looked up in the Census surname table "
                         "(the share of people with that name who are Hispanic or Asian) and the shares are added up. Good for statewide trends, "
                         "rough for any one person. District-level estimates are on the "
                         "<a href=\"/tx/\" style=\"color:var(--accent)\">Texas district page</a>.",
                         title="Who is voting early &middot; statewide Hispanic and Asian share (surname estimate) &middot; 2026 vs 2022 at the same point")
    return None


def state_data(state):
    if state == "KS":
        return {"state": state, "pending": ks_info()}
    if state == "IA":
        return {"state": state, "pending": ia_info()}
    if state == "NV":
        return {"state": state, "pending": nv_info()}
    sd = sameday_info(state)
    if sd is None and state in WAITING:
        return {"state": state, "pending": {"waiting": True}}
    if sd and (sd.get("pending") or (sd["day"] < 1 and state == "TX")):
        # TX before in-person voting opens (patchy mail counts only); OH before its first 2022
        # county snapshot point (only a statewide comparison exists) -> notice, no county table
        return {"state": state, "pending": sd}
    ref_years, basis, rows, hist, cur, lean = compare(state)
    gd = group_deviation(state, SPLIT)
    cur_total, ov = overall_turnout(state)
    _cy, cl = composite_lean(state)
    _py, per, pagg = turnout_progress(state)
    latest_all = None
    if state == "OH" and sd and sd.get("latest_inperson") is not None:
        # The county comparison uses in-person votes cut back to the 2022 report date, but progress
        # toward 2022's TOTAL turnout should count every early vote so far (in person + mail).
        import csv as _csv
        from collections import Counter as _C
        tot26 = _C()
        for r in _csv.DictReader((Path(__file__).resolve().parent.parent / "data" / "oh_county" / "early_2026.csv").open(encoding="utf-8")):
            if r["date"] <= sd["latest"]:
                tot26[r["county"].strip().upper()] += int(r["ballots"])
        latest_all = sd["latest_inperson"] + sd.get("latest_mail", 0)
        _hist = turnout_compare_hist(state)
        for y in _py:
            den = sum(c["total"] for c in _hist[y].values())
            pagg[y] = latest_all / den if den else None
            for c in per:
                t = _hist[y].get(c, {}).get("total", 0)
                per[c][y] = tot26.get(c, 0) / t if t else None
    _tr_per, tr_agg = turnout_rate(state)

    counties = []
    for r in rows:
        name = r["county"]
        ld = r["lean_dem"]
        rec = {"county": name.title(), "lean": ld,
               "group": "D" if (ld or 0) >= SPLIT else "R",
               "share": r["cur_share"], "n": cur.get(name, 0)}
        for y in ref_years:
            rec[f"vs{y}"] = r[f"vs_{y}"]
            rec[f"p{y}"] = per.get(name, {}).get(y)
        counties.append(rec)

    dem, rep = gd["groups"]["Blue-leaning"], gd["groups"]["Red-leaning"]
    groups = {"Dem": {"n": dem["n"], "share": dem["cur_share"], "dev": dem["dev"]},
              "Rep": {"n": rep["n"], "share": rep["cur_share"], "dev": rep["dev"]}}
    net = {}
    for y in ref_years:
        b, r = dem["dev"].get(y), rep["dev"].get(y)
        net[y] = (b - r) if (b is not None and r is not None) else None

    return {
        "state": state, "ref_years": ref_years, "basis": basis,
        "cur_total": cur_total,
        "overall": {y: ov[y]["pct_of"] for y in ref_years},
        "groups": groups, "net": net, "counties": counties,
        "complean": {str(y): cl[y] for y in _cy} | {"cur": cl["cur"]},
        "progress": {str(y): pagg[y] for y in _py},
        "latest_all": latest_all,
        "turnout_rate": tr_agg,
        "sameday": sameday_info(state),
        "partyreg": party_info(state),
        "gademo": ga_demo_info() if state == "GA" else district_demo_info(state) if state == "NC" else None,   # TX: rosters incomplete (see district_demo_info)
        "note2022": fix2022_note(state),
        "live": (Path(__file__).resolve().parent.parent / "data" / "live"
                 / f"{state.lower()}_current.csv").exists(),
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Early-Vote Performance Matrix</title>
<style>
  :root{--bg:#0f1420;--panel:#171e2e;--panel2:#1d2638;--line:#2a3447;--ink:#e7ecf5;
    --muted:#93a0b8;--dem:#3b82f6;--rep:#ef4444;--pos:#22c55e;--neg:#ef4444;--accent:#fbbf24;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
  header{padding:16px 22px;border-bottom:1px solid var(--line);background:var(--panel)}
  h1{margin:0;font-size:19px}
  .sub{color:var(--muted);font-size:12.5px;margin-top:4px}
  .wrap{padding:18px 22px;max-width:1160px;margin:0 auto}
  .tabs{display:flex;gap:8px;margin-bottom:16px}
  .tab{padding:8px 20px;border:1px solid var(--line);background:var(--panel);color:var(--ink);
    border-radius:8px;cursor:pointer;font-weight:600}
  .tab.on{background:var(--accent);color:#1a1300;border-color:var(--accent)}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px}
  .card .lab{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em}
  .card .big{font-size:25px;font-weight:700;margin-top:5px}
  .card .note{color:var(--muted);font-size:11.5px;margin-top:5px;line-height:1.5}
  .panels{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
  @media(max-width:760px){.panels{grid-template-columns:1fr}}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
  .panel h3{margin:0 0 4px;font-size:13.5px}
  .panel .ph{color:var(--muted);font-size:11.5px;margin-bottom:11px;line-height:1.5}
  .brow{display:flex;align-items:center;gap:10px;margin:7px 0}
  .brow .yl{width:38px;color:var(--muted);font-size:12px;flex:none}
  .track{flex:1;height:16px;background:var(--panel2);border-radius:5px;position:relative;overflow:hidden}
  .fill{height:100%;border-radius:5px}
  .brow .vl{width:70px;text-align:right;font-size:12.5px;font-weight:600;flex:none}
  .mark{position:absolute;top:0;bottom:0;width:2px;background:var(--muted);opacity:.6}
  .verdict{margin-top:10px;font-size:12px;line-height:1.5;padding:8px 10px;border-radius:8px;
    background:var(--panel2)}
  .toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:9px}
  input,select{background:var(--panel2);border:1px solid var(--line);color:var(--ink);
    padding:8px 10px;border-radius:8px;font-size:13px}
  input{min-width:190px}
  .seg{display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .seg button{background:var(--panel2);color:var(--muted);border:none;padding:8px 14px;cursor:pointer;font-size:12.5px;font-weight:600}
  .seg button.on{background:var(--accent);color:#1a1300}
  .tablewrap{max-height:60vh;overflow:auto;border:1px solid var(--line);border-radius:10px}
  table{width:100%;border-collapse:collapse}
  th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
  th:first-child,td:first-child{text-align:left}
  thead th{position:sticky;top:0;background:var(--panel2);cursor:pointer;user-select:none;
    font-size:11.5px;color:var(--muted)}
  thead th:hover{color:var(--ink)}
  tbody tr:hover{background:#1b2435}
  .badge{display:inline-block;min-width:20px;text-align:center;padding:1px 7px;border-radius:6px;font-weight:700;font-size:12px}
  .badge.D{background:rgba(59,130,246,.18);color:#93c5fd}
  .badge.R{background:rgba(239,68,68,.18);color:#fca5a5}
  .pbar{display:inline-block;width:52px;height:9px;border-radius:3px;background:var(--panel2);
    position:relative;vertical-align:middle;margin-left:7px;overflow:hidden}
  .pbar i{position:absolute;left:0;top:0;bottom:0;border-radius:3px}
  .foot{color:var(--muted);font-size:12px;margin-top:14px;line-height:1.6}
  .pill{display:inline-block;padding:1px 7px;border-radius:6px;font-weight:600}
</style>
</head>
<body>
<header>
  <h1>Early-Vote Performance Matrix <span style="color:var(--accent)">&middot; 2026</span></h1>
  <div class="sub">County-level early-voting signal vs past cycles (Georgia, Florida, Iowa, Kansas, Maine, Michigan, North Carolina, Ohio, South Carolina &amp; Texas: 2022 at the same point of early voting; Kansas statewide only) &mdash; partisan share shift, aggregate Dem tilt, and turnout progress.</div>
  <div class="sub" style="margin-top:6px"><b>New:</b> early vote by State House &amp; Senate district for <a href="/ga/" style="color:var(--accent)">Georgia &rarr;</a>, <a href="/nc/" style="color:var(--accent)">North Carolina &rarr;</a>, <a href="/tx/" style="color:var(--accent)">Texas &rarr;</a> and <a href="/me/" style="color:var(--accent)">Maine &rarr;</a> &middot; <a href="/ga/#/polls" style="color:var(--accent)">Senate &amp; Governor polling data &rarr;</a></div>
</header>
<div class="wrap">
  <div class="tabs" id="tabs"></div>
  <div class="cards" id="cards"></div>
  <div class="panels" id="panels"></div>
  <div class="toolbar">
    <div class="seg" id="viewSeg">
      <button data-v="partisan" class="on">Partisan shift</button>
      <button data-v="turnout">Turnout progress</button>
    </div>
    <input id="q" placeholder="Filter counties by name...">
    <select id="grp">
      <option value="">All counties</option>
      <option value="D">Dem-leaning only</option>
      <option value="R">Rep-leaning only</option>
    </select>
    <span class="sub" id="count"></span>
  </div>
  <div class="tablewrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
  <div class="foot" id="foot"></div>
</div>
<script>
const DATA = __DATA__;
let cur = "__FIRST__", sortKey="share", sortDir=-1, view="partisan";

const pct=(x,s)=>x==null?"&mdash;":((s&&x*100>0?"+":"")+(x*100).toFixed(1)+"%");
const p0=(x)=>x==null?"&mdash;":Math.round(x*100)+"%";
function shiftBg(x){if(x==null)return"";const a=(Math.min(Math.abs(x)/0.15,1)*0.55).toFixed(2);
  return x>=0?`background:rgba(34,197,94,${a})`:`background:rgba(239,68,68,${a})`;}

function tabs(){document.getElementById("tabs").innerHTML=
  Object.keys(DATA).map(s=>`<div class="tab ${s===cur?'on':''}" onclick="pick('${s}')">${s}</div>`).join("");}
function pick(s){cur=s;sortKey="share";sortDir=-1;tabs();
  const show=!DATA[cur].pending;
  ["panels",".toolbar",".tablewrap","foot"].forEach(id=>{const e=id[0]==="."?document.querySelector(id):document.getElementById(id);e.style.display=show?"":"none";});
  if(!show){pendingView();return;}
  cards();panels();render();}
function pendingView(){const p=DATA[cur].pending;
  if(p.nv){const pc=x=>x==null?"–":(x*100).toFixed(1)+"%", pp=x=>(x>0?"+":"")+(x*100).toFixed(1), n=x=>x.toLocaleString();
    const mg=s=>s.D-s.R, mtxt=x=>(x>=0?"D +":"R +")+Math.abs(x*100).toFixed(1);
    const a=p.ip_pt, b=p.ip22;
    const cmp=a?`<div class="card"><div class="lab">In-person early votes vs 2022, same point</div>
        <div class="big" style="color:var(--accent)">${Math.round(a.n/b.n*100)}%</div>
        <div class="note">${n(a.n)} through ${p.point26} vs ${n(b.n)} through ${p.point22} (${p.point22==="2022-10-28"?"end of early-voting week 1":"end of early voting"}).</div></div>
      <div class="card"><div class="lab">Party margin of in-person early voters vs 2022</div>
        <div class="big" style="color:${mg(a)-mg(b)>=0?'var(--dem)':'var(--rep)'}">${pp(mg(a)-mg(b))} pts</div>
        <div class="note">${mtxt(mg(a))} now vs ${mtxt(mg(b))} in 2022 (Dem ${pc(a.D)} vs ${pc(b.D)}, Rep ${pc(a.R)} vs ${pc(b.R)}; party registration, not votes cast).</div></div>`:"";
    const mailNote=p.mail_pt?`Same point as 2022: ${n(p.mail_pt.n)} vs ${n(p.mail22_pt.n)} (${Math.round(p.mail_pt.n/p.mail22_pt.n*100)}%).`
      :`Nevada's dashboard shows only a current mail total, so a same-point mail comparison starts at the end of early-voting week 2 (2026 data through Oct 30 vs 2022 through Nov 4). 2022 had ${n(p.mail22_pt?p.mail22_pt.n:0)} returned by the end of week 1 and ${n(p.mail22_final.n)} by the end of early voting.`;
    const crow=c=>{const r=c.ip_pt&&c.ip22&&c.ip22.n?Math.round(c.ip_pt.n/c.ip22.n*100)+"%":"–";
      return `<tr><td>${c.county}</td><td>${c.ip_pt?n(c.ip_pt.n):"–"}</td><td>${c.ip22?n(c.ip22.n):"–"}</td><td><b>${r}</b></td>
      <td>${c.ip_pt?mtxt(mg(c.ip_pt)):"–"}</td><td style="color:var(--muted)">${c.ip22?mtxt(mg(c.ip22)):"–"}</td>
      <td>${n(c.mail_now.n)}</td><td>${mtxt(mg(c.mail_now))}</td><td>${c.mail22_final.n?Math.round(c.mail_now.n/c.mail22_final.n*100)+"%":"–"}</td></tr>`;};
    const cs=p.counties.slice().sort((x,y)=>y.ip_now.n-x.ip_now.n);
    document.getElementById("cards").innerHTML=`<div class="card"><div class="lab">Nevada early votes (in person through ${p.as_of}; mail as of ${p.mail_snap})</div>
        <div class="big">${n(p.ip_now.n+p.mail_now.n)}</div><div class="note">${n(p.ip_now.n)} in person &middot; ${n(p.mail_now.n)} mail ballots returned</div></div>`+cmp+
      `<div class="card"><div class="lab">Mail ballots returned (as of ${p.mail_snap})</div><div class="big">${n(p.mail_now.n)}</div>
        <div class="note">Dem ${pc(p.mail_now.D)} &middot; Rep ${pc(p.mail_now.R)} &middot; other ${pc(p.mail_now.O)}. ${mailNote}</div></div>
      <div class="card" style="grid-column:1/-1"><div class="lab">By county &middot; in person vs 2022 at the same point; mail so far</div>
        <div class="tablewrap" style="margin-top:8px;max-height:55vh"><table><thead><tr><th>County</th><th>In person 2026</th><th>2022 same point</th><th>vs 2022</th>
        <th>In-person margin</th><th>2022 margin</th><th>Mail returned</th><th>Mail margin</th><th>% of 2022 full mail</th></tr></thead><tbody>${cs.map(crow).join("")}</tbody></table></div>
        <div class="note" style="margin-top:6px">2026: Nevada Secretary of State VIVID dashboard (in person daily; mail a current total). 2022: the Secretary of State's weekly early-voting
        reports (week 1 through Oct 28, week 2 through Nov 4, by county and party), compared at the same number of days before Election Day.
        Margins are registered Democrats minus Republicans among early voters; "other" includes nonpartisan voters, who are not in the margin.</div></div>`;
    return;}
  if(p.ia){const pc=x=>x==null?"–":(x*100).toFixed(1)+"%", pp=x=>(x>0?"+":"")+(x*100).toFixed(1), n=x=>x.toLocaleString();
    const mg=s=>s.D-s.R, mtxt=x=>(x>=0?"D +":"R +")+Math.abs(x*100).toFixed(1);
    const st=p.districts[0];
    const drow=d=>{const r=d.now.n/d.then.n, dm=mg(d.now)-mg(d.then);
      return `<tr><td>${d.area==="STATE"?"<b>Statewide</b>":"IA-"+d.area}</td><td>${n(d.now.n)}</td><td>${n(d.then.n)}</td>
      <td><b>${Math.round(r*100)}%</b></td><td>${pc(d.now.D)} <span style="color:var(--muted)">(${pc(d.then.D)})</span></td>
      <td>${pc(d.now.R)} <span style="color:var(--muted)">(${pc(d.then.R)})</span></td><td>${mtxt(mg(d.now))}</td>
      <td style="color:${dm>=0?'var(--dem)':'var(--rep)'}">${pp(dm)} pts</td></tr>`;};
    const crow=c=>{const m=mg(c.now), m22=mg(c.final22);
      return `<tr><td>${c.county}</td><td>IA-${c.cd}</td><td>${n(c.now.n)}</td><td>${pc(c.now.D)}</td><td>${pc(c.now.R)}</td><td>${pc(c.now.NP)}</td>
      <td>${mtxt(m)}</td><td>${c.progress==null?"–":Math.round(c.progress*100)+"%"}</td><td style="color:var(--muted)">${mtxt(m22)}</td></tr>`;};
    const cs=p.counties.slice().sort((a,b)=>b.now.n-a.now.n);
    document.getElementById("cards").innerHTML=`<div class="card"><div class="lab">Iowa absentee/early ballots received (report ${p.as_of})</div>
        <div class="big">${n(p.daily[p.daily.length-1][1])}</div><div class="note">Statewide by party of registration (report ${p.cmp26}): Democrats ${pc(st.now.D)} &middot; Republicans ${pc(st.now.R)} &middot; no party ${pc(st.now.NP)}</div></div>
      <div class="card"><div class="lab">Vs 2022, same point (${p.days_out} days before Election Day)</div>
        <div class="big" style="color:var(--accent)">${Math.round(st.now.n/st.then.n*100)}%</div>
        <div class="note">${n(st.now.n)} (report ${p.cmp26}) vs ${n(st.then.n)} (report ${p.cmp22}).</div></div>
      <div class="card"><div class="lab">Party margin of early voters vs 2022, same point</div>
        <div class="big" style="color:${mg(st.now)-mg(st.then)>=0?'var(--dem)':'var(--rep)'}">${pp(mg(st.now)-mg(st.then))} pts</div>
        <div class="note">${mtxt(mg(st.now))} now vs ${mtxt(mg(st.then))} in 2022 (registered Democrats minus Republicans as a share of ballots received; party registration, not votes cast).</div></div>
      <div class="card" style="grid-column:1/-1"><div class="lab">By congressional district &middot; 2026 vs 2022 at the same point</div>
        <div class="tablewrap" style="margin-top:8px"><table><thead><tr><th>District</th><th>2026 received</th><th>2022 same point</th><th>vs 2022</th>
        <th>Dem share (2022)</th><th>Rep share (2022)</th><th>D&minus;R margin</th><th>Margin vs 2022</th></tr></thead><tbody>${p.districts.map(drow).join("")}</tbody></table></div>
        <div class="note" style="margin-top:6px">Every 2022 report is available by district (Iowa SoS reports, as reproduced by
        <a href="https://www.bleedingheartland.com/2022/10/20/iowa-absentee-ballot-numbers-in-the-2022-general-election/" style="color:var(--accent)">Bleeding Heartland</a>),
        so these are true same-day comparisons, lined up by days before Election Day. Iowa posts no weekend reports.</div></div>
      <div class="card" style="grid-column:1/-1"><div class="lab">By county &middot; 2026 (report ${p.county_as_of})</div>
        <div class="tablewrap" style="margin-top:8px;max-height:55vh"><table><thead><tr><th>County</th><th>District</th><th>Received</th><th>Dem</th><th>Rep</th><th>No party</th>
        <th>D&minus;R margin</th><th>% of 2022 full early vote</th><th>2022 full early-vote margin</th></tr></thead><tbody>${cs.map(crow).join("")}</tbody></table></div>
        <div class="note" style="margin-top:6px">2022 county numbers survive only as a few snapshots (final report ${p.final22}), so counties are compared with
        <b>2022's full early vote</b>, not the same day: "% of 2022 full early vote" is how far each county has already got, and the last column is the
        party margin of its whole 2022 early electorate. Iowa's early voters lean more Democratic early in the voting period and less later, so a margin
        above the 2022 figure now does not mean the county will finish above it. Source: Iowa Secretary of State absentee ballot statistics.</div></div>`;
    return;}
  if(p.ks){const c=p.cmp, tot=p.inperson+p.returned, f=p.final22;
    const pc=(a,b)=>Math.round(a/b*100)+"%";
    const cmpCard=c?`<div class="card"><div class="lab">Vs 2022, same point (${c.days_out} days before Election Day)</div>
        <div class="big" style="color:var(--accent)">${pc(c.inperson26+c.returned26,c.inperson22+c.returned22)}</div>
        <div class="note">${(c.inperson26+c.returned26).toLocaleString()} voted through ${c.d26} vs ${(c.inperson22+c.returned22).toLocaleString()} in 2022.
        In person alone: ${pc(c.inperson26,c.inperson22)} (${c.inperson26.toLocaleString()} vs ${c.inperson22.toLocaleString()}).<br>
        2022 source: ${c.source22}.</div></div>`:"";
    const rows=p.daily.slice().reverse().map(([d,s,r,i])=>`<tr><td>${d}</td><td>${(i+r).toLocaleString()}</td><td>${i.toLocaleString()}</td><td>${r.toLocaleString()}</td><td>${s.toLocaleString()}</td></tr>`).join("");
    document.getElementById("cards").innerHTML=`<div class="card"><div class="lab">Kansas advance ballots voted through ${p.as_of}</div>
        <div class="big">${tot.toLocaleString()}</div>
        <div class="note">${p.inperson.toLocaleString()} in person &middot; ${p.returned.toLocaleString()} mail returned (of ${p.sent.toLocaleString()} sent)</div></div>`+cmpCard+
      `<div class="card"><div class="lab">Share of 2022's advance vote (as of ${f.days_out} days out)</div>
        <div class="big">${pc(tot,f.total)}</div><div class="note">2026 so far vs ${f.total.toLocaleString()} advance ballots voted in 2022 by Nov 4 (in person + mail returned).</div></div>
      <div class="card" style="grid-column:1/-1"><div class="lab">Statewide only</div>
        <div class="note">The Kansas Secretary of State publishes advance voting as <b>statewide daily totals only</b>
        (<a href="https://www.sos.ks.gov/elections/advance-voting-data.html" style="color:var(--accent)">sos.ks.gov</a>), with no county or party breakdown,
        so Kansas has no county table or Dem/Rep-leaning county signal. No day-by-day 2022 series exists either: 2026 is compared at the
        latest 2022 point it has reached (12 days out, from Secretary of State figures reported by WIBW; then Nov 4 2022, 4 days out).
        All Kansas counties must offer in-person advance voting by Tue Oct 27 2026 (Nov 1 in 2022).</div>
        <div class="tablewrap" style="margin-top:10px;max-height:40vh"><table><thead><tr><th>Report date</th><th>Voted</th><th>In person</th><th>Mail returned</th><th>Mail sent</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
    return;}
  if(p.waiting){
    document.getElementById("cards").innerHTML=`<div class="card" style="grid-column:1/-1">
      <div class="lab">South Carolina &middot; waiting for the state's first 2026 report</div>
      <div class="big" style="font-size:20px">Early voting opened Mon Oct 19</div>
      <div class="note">The SC Election Commission posts its early-voting report on
        <a href="https://scvotes.gov/elections-statistics/voter-participation/" style="color:var(--accent)">scvotes.gov</a>;
        the 2026 general-election report hasn't appeared yet. As soon as it does, the daily update picks it up and this tab compares
        each county's <b>in-person early votes</b> with the same day of early voting in 2022 (opened Oct 24 2022, Oct 19 2026).
        Mail ballots aren't compared: South Carolina published 2022 mail ballots only as a final total.</div></div>`;
    return;}
  if(cur==="OH"){const s=p.statewide, x=(s.n26/s.n22).toFixed(1);
    document.getElementById("cards").innerHTML=`<div class="card"><div class="lab">Ohio in-person early votes through ${p.latest}</div>
      <div class="big">${p.latest_inperson.toLocaleString()}</div><div class="note">plus ${p.latest_mail.toLocaleString()} mail ballots returned</div></div>
      <div class="card"><div class="lab">Statewide vs 2022, same point (22 days out)</div>
      <div class="big" style="color:var(--accent)">${x}&times;</div><div class="note">${s.n26.toLocaleString()} in person through ${s.d26} vs ${s.n22.toLocaleString()} through ${s.d22}</div></div>
      <div class="card" style="grid-column:1/-1"><div class="lab">County comparison with 2022</div>
      <div class="big" style="font-size:20px">Starts with data through ${p.first_through} (posted ~${p.first_compare})</div>
      <div class="note">For 2022 Ohio published county early-vote numbers only at three points (votes as of Oct 21, Oct 28 and Nov 7, 2022:
      18, 11 and 1 days before Election Day). Ohio is compared on <b>in-person early votes</b> by county, with 2026 cut back to the same number
      of days out as the latest of those points. Until 2026 reaches the first one, only the statewide figure above exists.
      Source: Ohio Secretary of State absentee/early-vote file (in person = ballot issued and cast the same day; matches the state's
      own week-1 total of 194,841 within 1%).</div></div>`;
    return;}
  document.getElementById("cards").innerHTML=`<div class="card" style="grid-column:1/-1">
    <div class="lab">Texas &middot; waiting for in-person early voting</div>
    <div class="big" style="font-size:20px">First comparison with 2022: Tue Oct 20 morning</div>
    <div class="note">In-person early voting opens <b>Mon Oct 19</b>. Through ${p.as_of} the Secretary of State shows only
      <b>${(p.mail||0).toLocaleString()} mail ballots</b>, and just <b>${p.mail_counties} of ${p.counties} counties</b> have reported any
      (in 2022, 233 had by this point), so a county comparison now would only measure which counties have uploaded.
      Texas is compared on <b>in-person early votes</b> (94% of its 2022 early vote), lined up by day of early voting
      (opened Oct 24 2022, Oct 19 2026). State House, Senate and congressional detail: <a href="/tx/" style="color:var(--accent)">Texas &rarr;</a></div></div>`;}

function cards(){const d=DATA[cur],ys=d.ref_years;
  const nc=y=>{const n=d.net[y];if(n==null)return"";const dem=n>0,col=dem?"var(--dem)":"var(--rep)";
    return `<div class="card"><div class="lab">Net turnout edge vs ${y}</div>
      <div class="big" style="color:${col}">${(n*100>0?'+':'')}${(n*100).toFixed(1)} pts</div>
      <div class="note">toward <b>${dem?'Democratic':'Republican'}</b> &middot; Dem-lean ${pct(d.groups.Dem.dev[y],1)}, Rep-lean ${pct(d.groups.Rep.dev[y],1)}</div></div>`;};
  const ov=ys.map(y=>`${y}: <b>${Math.round(d.overall[y]*100)}%</b>`).join(" &middot; ");
  const sd=d.sameday;
  const dayTxt=sd?(sd.day>0?`day ${sd.day}`:`mail only; in-person opens in ${1-sd.day} day${sd.day===0?"":"s"}`):"";
  let lab=sd?`Early ballots through ${sd.as_of} (${dayTxt})`:"Early ballots so far (2026)";
  let ovNote=sd?`vs the same day of early voting &middot; ${ov}`:`of each year's full early vote &middot; ${ov}`;
  let big=d.cur_total;
  if(cur==="OH"&&sd&&d.latest_all){lab=`Early ballots through ${sd.latest}`;big=d.latest_all;
    ovNote=`${sd.latest_inperson.toLocaleString()} in person + ${sd.latest_mail.toLocaleString()} mail ballots returned.<br>`+
      `Compared with 2022 on <b>in-person votes</b> at the same point: ${d.cur_total.toLocaleString()} through ${sd.as_of} vs Ohio's 2022 report as of ${sd.snapshot_2022} &middot; ${ov}`;}
  if(cur==="MI"&&sd){lab=`Absentee ballots returned as of ${sd.as_of}`;
    ovNote=`vs 2022 at the same point (${sd.snapshot_2022}) &middot; ${ov}<br>Latest (${sd.latest}): ${sd.latest_returned.toLocaleString()} returned, ${sd.latest_sent.toLocaleString()} sent`+
      (sd.latest_ev?`; ${sd.latest_ev.toLocaleString()} early in person through ${sd.latest_ev_date||sd.latest} (2026 only; none in 2022)`:`; early in-person voting opens Oct 24 (none in 2022)`);}
  document.getElementById("cards").innerHTML=
    `<div class="card"><div class="lab">${lab}</div>
       <div class="big">${big.toLocaleString()}</div>
       <div class="note">${ovNote}${d.note2022?`<br><span style="color:var(--accent)">${d.note2022}</span>`:""}</div></div>`+ys.slice().reverse().map(nc).join("")+partyCard(d.partyreg)+demoCard(d.gademo);}
function demoCard(g){if(!g)return"";const pc=x=>(x*100).toFixed(1)+"%";
  const tbl=dm=>`<div><div class="lab" style="margin:6px 0 4px">${dm.title}</div><div class="tablewrap" style="max-height:none"><table>
    <thead><tr><th>Group</th><th>2026</th><th>2022</th><th>Change</th></tr></thead><tbody>${dm.rows.map(r=>{const dd=(r.now-r.then)*100;
    return `<tr><td><b>${r.group}</b></td><td>${pc(r.now)}</td><td style="color:var(--muted)">${pc(r.then)}</td><td>${dd>0?"+":""}${dd.toFixed(1)} pts</td></tr>`;}).join("")}</tbody></table></div></div>`;
  const hl=h=>`${h.label} <b>${pc(h.now)}</b> <span style="color:var(--muted)">(2022: ${pc(h.then)})</span>`;
  return `<div class="card" style="grid-column:1/-1"><div class="lab">${g.title||"Who is voting early &middot; statewide by race, gender and age &middot; 2026 vs 2022 on the same day of early voting"}</div>
    <div style="font-size:15px;margin:6px 0">${g.headline.map(hl).join(" &nbsp;&middot;&nbsp; ")}</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px">${g.dims.map(tbl).join("")}</div>
    <div class="note" style="margin-top:6px">2026 through ${g.through26} (${g.n26.toLocaleString()} early voters) vs 2022 through ${g.through22} (${g.n22.toLocaleString()}).
    ${g.note} <b>This is who voted, not how they voted.</b></div></div>`;}
function partyCard(p){if(!p)return"";const pc=x=>(x*100).toFixed(1)+"%";
  const rows=p.rows.map(r=>{const dd=(r.now-r.then)*100, col=r.party==="Democrat"?"var(--dem)":r.party==="Republican"?"var(--rep)":"var(--ink)";
    return `<tr><td style="color:${col}"><b>${r.party}</b></td><td>${pc(r.now)}</td><td style="color:var(--muted)">${pc(r.then)}</td>
      <td>${dd>0?"+":""}${dd.toFixed(1)} pts</td><td>${r.n.toLocaleString()}</td></tr>`;}).join("");
  const dm=p.rows.find(r=>r.party==="Democrat"), rm=p.rows.find(r=>r.party==="Republican");
  const m=x=>x>=0?`D +${(x*100).toFixed(1)}`:`R +${(-x*100).toFixed(1)}`;
  const mNow=dm&&rm?dm.now-rm.now:null, mThen=dm&&rm?dm.then-rm.then:null;
  return `<div class="card" style="grid-column:1/-1"><div class="lab">Early voters by registered party &middot; 2026 vs 2022 at the same point (${p.days_out} days before Election Day)</div>
    ${mNow!=null?`<div class="big" style="font-size:20px">${m(mNow)} <span style="font-size:13px;color:var(--muted)">vs ${m(mThen)} in 2022 (D&minus;R share of early voters)</span></div>`:""}
    <div class="tablewrap" style="margin-top:8px;max-height:none"><table><thead><tr><th>Registered party</th><th>2026 share</th><th>2022 share</th><th>Change</th><th>2026 early voters</th></tr></thead>
    <tbody>${rows}</tbody></table></div>
    <div class="note" style="margin-top:6px">2026 through ${p.as_of} (${p.n26.toLocaleString()} early voters) vs 2022 through ${p.d22} (${p.n22.toLocaleString()}).
    <b>This is the party each early voter is registered with, not how they voted:</b> ballots are secret until counted, registered Democrats and
    Republicans can cross over, and unaffiliated voters can go either way.</div></div>`;}

function panels(){const d=DATA[cur];
  const cl=d.complean, cy=d.ref_years.concat(["cur"]);
  const lab=y=>y==="cur"?"2026":y;
  const clScale=v=>Math.max(0,Math.min(1,(v-0.30)/(0.40)))*100;   // 30%..70% D, 50% marker in the middle
  const clRows=cy.map(y=>{const v=cl[y];const is26=y==="cur";
    return `<div class="brow"><span class="yl">${lab(y)}</span>
      <div class="track"><div class="fill" style="width:${clScale(v).toFixed(0)}%;background:${is26?'var(--accent)':'var(--dem)'}"></div>
      <div class="mark" style="left:${clScale(0.50).toFixed(0)}%"></div></div>
      <span class="vl" style="${is26?'color:var(--accent)':''}">${(v*100).toFixed(1)}% D</span></div>`;}).join("");
  const ry=d.ref_years, best=ry.every(y=>cl.cur>=cl[y]), worst=ry.every(y=>cl.cur<cl[y]);
  const clRead=`2026 early electorate is <b>${(cl.cur*100).toFixed(1)}% Dem-tilted</b> &mdash; `+
    ry.map(y=>`${pct(cl.cur-cl[y],1)} vs ${y}`).join(", ")+". "+
    (best?`<b>Above every comparison year</b>${d.sameday?" at the same point of early voting":""}.`
      :worst?`<b>Below every comparison year</b>.`:`Mixed vs prior cycles.`);

  const pr=d.progress, py=d.ref_years;
  const prScale=v=>Math.min(v,1.5)/1.5*100;
  const prRows=py.map(y=>{const v=pr[y];const over=v>=1;
    return `<div class="brow"><span class="yl">${y}</span>
      <div class="track"><div class="fill" style="width:${prScale(v).toFixed(0)}%;background:${over?'var(--pos)':'var(--accent)'}"></div>
      <div class="mark" style="left:${(100/1.5).toFixed(0)}%"></div></div>
      <span class="vl" style="${over?'color:var(--pos)':''}">${Math.round(v*100)}%</span></div>`;}).join("");
  const prRead=`Marker = 100% (a full prior turnout, all voting methods). Bars past it = 2026 early vote alone has <b>already exceeded</b> that year's total turnout. Climbs daily as early voting runs.`;
  const tr=d.turnout_rate;
  const trStat=tr==null?"":`<div style="margin-bottom:8px;font-size:13px"><b style="font-size:18px;color:var(--accent)">${Math.round(tr*100)}%</b> of registered voters have voted early <span style="color:var(--muted)">(est. — see note)</span></div>`;

  document.getElementById("panels").innerHTML=
    `<div class="panel"><h3>Aggregate Dem tilt of the early electorate</h3>
       <div class="ph">Dem two-party lean weighted by where the early votes come from. Higher = early voters from more-Democratic places.</div>
       ${clRows}<div class="verdict">${clRead}</div></div>
     <div class="panel"><h3>Turnout progress vs full prior turnout</h3>
       ${trStat}<div class="ph">2026 early ballots so far as a % of each county-summed TOTAL turnout in that year.</div>
       ${prRows}<div class="verdict">${prRead}</div></div>`;}

function header(){const ys=DATA[cur].ref_years;
  let cols=[["county","County"],["lean","Lean"],["group","Grp"],["n","2026 early votes"],["share","2026 share"]];
  cols=cols.concat(view==="partisan"
    ? ys.map(y=>["vs"+y,"vs "+y])
    : ys.map(y=>["p"+y,"% of "+y]));
  document.querySelector("#tbl thead").innerHTML="<tr>"+cols.map(([k,l])=>{
    const ar=k===sortKey?(sortDir>0?"&#9650;":"&#9660;"):"";
    return `<th onclick="sortBy('${k}')">${l} ${ar}</th>`;}).join("")+"</tr>";}
function sortBy(k){if(k===sortKey)sortDir*=-1;else{sortKey=k;sortDir=(k==='county'?1:-1);}render();}

function render(){header();const d=DATA[cur],ys=d.ref_years;
  const q=document.getElementById("q").value.trim().toLowerCase();
  const g=document.getElementById("grp").value;
  let rows=d.counties.filter(c=>(!q||c.county.toLowerCase().includes(q))&&(!g||c.group===g));
  rows.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];
    if(sortKey==='county')return x<y?-sortDir:x>y?sortDir:0;
    x=(x==null)?-1e9:x;y=(y==null)?-1e9:y;return(x-y)*sortDir;});
  document.querySelector("#tbl tbody").innerHTML=rows.map(c=>{
    let cells;
    if(view==="partisan"){cells=ys.map(y=>`<td style="${shiftBg(c['vs'+y])}">${pct(c['vs'+y],1)}</td>`).join("");}
    else{cells=ys.map(y=>{const v=c['p'+y];const w=v==null?0:Math.min(v,1.5)/1.5*100;
      const col=v>=1?'var(--pos)':'var(--accent)';
      return `<td>${p0(v)}<span class="pbar"><i style="width:${w.toFixed(0)}%;background:${col}"></i></span></td>`;}).join("");}
    return `<tr><td>${c.county}</td><td>${Math.round(c.lean*100)}%</td>
      <td><span class="badge ${c.group}">${c.group}</span></td>
      <td>${(c.n||0).toLocaleString()}</td><td>${(c.share*100).toFixed(2)}%</td>${cells}</tr>`;}).join("");
  document.getElementById("count").textContent=rows.length+" counties";
  const foot=view==="partisan"
    ? `<b>Partisan shift:</b> each cell = how much bigger (<span class="pill" style="background:rgba(34,197,94,.4)">green</span>) or smaller (<span class="pill" style="background:rgba(239,68,68,.4)">red</span>) a slice of the early vote that county is now, vs that year. Dem-leaning green + Rep-leaning red = Democratic edge.`
    : `<b>Turnout progress:</b> 2026 early ballots as a % of that county's FULL turnout in the given year. <span class="pill" style="background:rgba(34,197,94,.4)">Green bar</span> = already past 100% (exceeded that whole election).`;
  const sd=d.sameday;
  const src=sd?`<br><b>Real 2026 data</b> through ${sd.as_of} (${sd.day>0?"early-voting day "+sd.day:"before in-person early voting opens"}) &middot; source: ${sd.source}. `+
      `Compared with the same day of early voting: `+d.ref_years.map(y=>`${y} through ${sd.years[y].used} (${sd.years[y].source})`).join("; ")+`. Lined up by ${cur==="MI"?"days before Election Day: Michigan published 2022 numbers only weekly (by town, rolled up to counties), so 2026 is cut back to the latest 2022 point it has reached; absentee ballots returned (Michigan had no early in-person voting in 2022)":cur==="OH"?"days before Election Day: Ohio published 2022 county numbers only as of Oct 21, Oct 28 and Nov 7 2022, so 2026 is cut back to the latest of those points it has reached; in-person early votes only":"day of in-person early voting"} (${({MI:"early in-person voting opens Oct 24 2026",OH:"early voting opened Oct 12 2022, Oct 6 2026",TX:"opened Oct 24 2022, Oct 19 2026",FL:"counties could open from Oct 24 2022 / Oct 19 2026; statewide from Oct 29 2022 / Oct 24 2026",SC:"opened Oct 24 2022, Oct 19 2026; in-person early votes only",NC:"opened Oct 20 2022, Oct 15 2026",GA:"opened Oct 17 2022, Oct 13 2026",PA:"Pennsylvania has no in-person early voting: mail ballots returned, lined up by days before Election Day",ME:"in-person absentee from about 29 days out both years: Oct 10 2022, Oct 5 2026"})[cur]}); mail ballots returned by each cutoff are included.`
    :d.live?`<br>Real 2026 data.`:`<br><b>${cur}: 2026 figures are synthetic stand-ins</b> until the real feed for this state is wired in.`;
  document.getElementById("foot").innerHTML=foot+src+` Partisan lean from county results; share metrics measure WHERE early voters come from, not who they voted for.`;}

document.getElementById("viewSeg").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;view=b.dataset.v;
  document.querySelectorAll("#viewSeg button").forEach(x=>x.classList.toggle("on",x===b));
  if((view==="turnout"&&sortKey.startsWith("vs"))||(view==="partisan"&&sortKey.startsWith("p")))sortKey="share";
  render();});
document.getElementById("q").addEventListener("input",render);
document.getElementById("grp").addEventListener("change",render);
// direct links: ?state=NC&view=turnout opens that tab and view (handy for sharing)
(()=>{const q=new URLSearchParams(location.search);const st=(q.get("state")||"").toUpperCase();
  if(DATA[st])cur=st;
  if(q.get("view")==="turnout"){view="turnout";
    document.querySelectorAll("#viewSeg button").forEach(x=>x.classList.toggle("on",x.dataset.v==="turnout"));}})();
pick(cur);
</script>
</body>
</html>
"""


def main():
    data = {s: state_data(s) for s in STATES}
    html = TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__FIRST__", STATES[0])
    out = Path(__file__).resolve().parent / "index.html"
    out.write_text(html, encoding="utf-8")
    body = html.split("<body>", 1)[1].split("</body>", 1)[0]
    (out.parent / "_widget.html").write_text(body, encoding="utf-8")
    print(f"  wrote {out}  ({out.stat().st_size//1024} KB, "
          f"{sum(len(d.get('counties', [])) for d in data.values())} counties)")


if __name__ == "__main__":
    main()
