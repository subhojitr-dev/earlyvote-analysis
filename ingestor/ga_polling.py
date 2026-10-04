"""
ga_polling.py — polls, polling averages, race ratings and betting odds for the 2026
U.S. Senate and Governor races in Georgia, Michigan, Ohio and Texas, for the
"View Polling Data" page (web/ga/). Add a state by adding two race(...) lines below.

Sources (all public, no keys):
  * Wikipedia race pages (wikitext via the MediaWiki API): the general-election poll
    table, the poll-aggregator table and the race-ratings table. Wikipedia is used
    because every row there cites its original source; rows WITHOUT a citation are
    skipped.
  * Kalshi    — api.elections.kalshi.com  (last traded price of each candidate's market)
  * Polymarket — gamma-api.polymarket.com (last traded price of each candidate)
  * PredictIt — www.predictit.org/api/marketdata (last traded price of each party)

Output: web/ga/polling.json. If a source fails, its last good data is kept and
labelled with the time it was fetched.

Run:  python ingestor/ga_polling.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "ga" / "polling.json"
UA = "earlyvote-analysis/1.0 (https://earlyvote-analysis.vercel.app)"

N_POLLS = 10
# Up to 5 well-known raters, in display order.
RATERS = ["The Cook Political Report", "Sabato's Crystal Ball", "Inside Elections",
          "Decision Desk HQ", "Silver Bulletin"]

STATES = {"GA": "Georgia", "MI": "Michigan", "OH": "Ohio", "TX": "Texas"}


def race(st, office, wiki, d, r, kalshi, polymarket, predictit, title=None):
    """d / r = (full name, word that identifies them in Wikipedia table headers[, incumbent])"""
    cand = lambda c, party: {"name": c[0], "match": c[1], "party": party, **({"inc": True} if len(c) > 2 else {})}
    return {"state": st, "state_name": STATES[st], "office": office,
            "title": title or ("U.S. Senate" if office == "senate" else "Governor"),
            "wiki": wiki, "cands": [cand(d, "D"), cand(r, "R")],
            "kalshi": {"D": f"{kalshi}-26-D", "R": f"{kalshi}-26-R"},
            "polymarket": polymarket, "predictit": predictit}


_RACES = [
    race("GA", "senate", "2026_United_States_Senate_election_in_Georgia",
         ("Jon Ossoff", "Ossoff", 1), ("Mike Collins", "Collins"), "SENATEGA", "georgia-senate-election-winner", 8156),
    race("GA", "governor", "2026_Georgia_gubernatorial_election",
         ("Keisha Lance Bottoms", "Bottoms"), ("Rick Jackson", "Jackson"), "GOVPARTYGA", "georgia-governor-winner-2026", 8416),
    race("MI", "senate", "2026_United_States_Senate_election_in_Michigan",
         ("Abdul El-Sayed", "El-Sayed"), ("Mike Rogers", "Rogers"), "SENATEMI", "michigan-senate-election-winner", 8158),
    race("MI", "governor", "2026_Michigan_gubernatorial_election",
         ("Jocelyn Benson", "Benson"), ("John James", "James"), "GOVPARTYMI", "michigan-governor-winner-2026", 8212),
    race("OH", "senate", "2026_United_States_Senate_special_election_in_Ohio",
         ("Sherrod Brown", "Brown"), ("Jon Husted", "Husted", 1), "SENATEOHS", "ohio-senate-election-winner", 8175,
         title="U.S. Senate (special election)"),
    race("OH", "governor", "2026_Ohio_gubernatorial_election",
         ("Amy Acton", "Acton"), ("Vivek Ramaswamy", "Ramaswamy"), "GOVPARTYOH", "ohio-governor-winner-2026", 8441),
    race("TX", "senate", "2026_United_States_Senate_election_in_Texas",
         ("James Talarico", "Talarico"), ("Ken Paxton", "Paxton"), "SENATETX", "texas-senate-election-winner", 8173),
    race("TX", "governor", "2026_Texas_gubernatorial_election",
         ("Gina Hinojosa", "Hinojosa"), ("Greg Abbott", "Abbott", 1), "GOVPARTYTX", "texas-governor-winner-2026", 8418),
]
RACES = {f"{r['state']}-{r['office']}": r for r in _RACES}


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# ------------------------------------------------------------------ wikitext tables
def clean(cell: str) -> str:
    """Wikitext cell -> plain text."""
    s = re.sub(r"<ref[^>]*/>", "", cell)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{[Ee]fn[^{}]*(\{\{[^{}]*\}\}[^{}]*)*\}\}", "", s)
    s = re.sub(r"\{\{(sdash|ndash|mdash)\}\}", "–", s)
    s = re.sub(r"\{\{nowrap\|([^{}]*)\}\}", r"\1", s)
    s = re.sub(r"\{\{party shading/[^}]*\}\}\s*\|?", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "").replace("''", "").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def split_attr(cell: str):
    """'style="x" rowspan="2" | value' -> (attrs, value). Ignores '|' inside templates/links."""
    depth, i = 0, 0
    while i < len(cell):
        two = cell[i:i + 2]
        if two in ("{{", "[["):
            depth += 1; i += 2; continue
        if two in ("}}", "]]"):
            depth -= 1; i += 2; continue
        if cell[i] == "|" and depth == 0:
            attrs = cell[:i]
            if "=" in attrs or attrs.strip() == "":
                return attrs, cell[i + 1:]
            return "", cell
        i += 1
    return "", cell


def tables(text: str):
    """Yield raw wikitables ({| ... |}) in order."""
    i = 0
    while True:
        a = text.find("{|", i)
        if a < 0:
            return
        depth, j = 0, a
        while j < len(text):
            if text.startswith("{|", j):
                depth += 1; j += 2; continue
            if text.startswith("|}", j):
                depth -= 1; j += 2
                if depth == 0:
                    break
                continue
            j += 1
        yield text[a:j]
        i = j


def parse_table(t: str):
    """-> (headers, rows). rows: list of lists of raw cell strings, with rowspans filled."""
    lines = t.split("\n")[1:-1]
    headers, rows, cur = [], [], None
    carry = {}                                    # col -> [remaining, raw]
    for ln in lines:
        if ln.startswith("|-"):
            if cur is not None:
                rows.append(cur)
            cur = []
            continue
        if ln.startswith("!"):
            for h in re.split(r"!!", ln[1:]):
                headers.append(clean(split_attr(h)[1]))
            continue
        if ln.startswith("|") and cur is not None:
            for raw in re.split(r"\|\|", ln[1:]):
                attrs, val = split_attr(raw)
                while len(cur) in carry:          # columns filled by an earlier rowspan
                    c = len(cur)
                    cur.append(carry[c][1])
                    carry[c][0] -= 1
                    if carry[c][0] == 0:
                        del carry[c]
                m = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
                if m and int(m.group(1)) > 1:
                    carry[len(cur)] = [int(m.group(1)) - 1, val]
                span = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
                cur.append(val)
                for _ in range(int(span.group(1)) - 1 if span else 0):
                    cur.append("")
            continue
        if cur is not None and cur:
            cur[-1] += "\n" + ln                  # continuation line
    if cur:
        rows.append(cur)
    # fill trailing carried cells for rows that ended early
    return headers, [r for r in rows if r]


def pct(s: str):
    m = re.search(r"(\d+(?:\.\d+)?)\s*%?", clean(s))
    return float(m.group(1)) if m else None


def cand_cols(headers, cands):
    return {c["party"]: next((i for i, h in enumerate(headers) if c["match"] in h), None) for c in cands}


def find_table(text, cands, must):
    for t in tables(text):
        h, rows = parse_table(t)
        if all(c["match"] in " ".join(h) for c in cands) and must(h):
            yield h, rows


def wiki_race(race):
    data = get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": race["wiki"], "prop": "wikitext", "format": "json", "formatversion": 2}))
    full = data["parse"]["wikitext"]
    # Only the "General election" section; polls/averages come from its Polling
    # subsection (earlier sections hold primary and hypothetical-matchup tables).
    m = re.search(r"\n==\s*General election\s*==\s*\n", full)
    if not m:
        raise ValueError("no 'General election' section")
    end = re.search(r"\n==[^=]", full[m.end():])
    general = full[m.end(): m.end() + end.start()] if end else full[m.end():]
    pm = list(re.finditer(r"\n===\s*Polling\s*===", general))
    if not pm:
        raise ValueError("no Polling subsection in General election")
    text = general[pm[-1].start():]
    cands = race["cands"]
    out = {"polls": [], "averages": [], "ratings": []}

    # aggregator table: header has "aggregation"
    for h, rows in find_table(text, cands, lambda h: any("aggregation" in x for x in h)):
        cols = cand_cols(h, cands)
        for r in rows:
            src = clean(r[0])
            vals = {p: pct(r[i]) if i is not None and i < len(r) else None for p, i in cols.items()}
            if None in vals.values():
                continue
            if src.lower() == "average":
                out["average_of_averages"] = vals
                continue
            out["averages"].append({"source": src, "dates": clean(r[1]), "updated": clean(r[2]), **vals})
        break

    # poll table: header has "Poll source" and "Sample"
    for h, rows in find_table(text, cands, lambda h: any("Poll source" in x for x in h)
                              and any("Sample" in x for x in h)):
        cols = cand_cols(h, cands)
        seen = {}
        for r in rows:
            if len(r) < len(h) - 2 or "<ref" not in r[0] and "{{Cite" not in r[0]:
                continue                          # separator rows and rows without a citation
            pollster = clean(r[0])
            vals = {p: pct(r[i]) if i is not None and i < len(r) else None for p, i in cols.items()}
            if None in vals.values():
                continue
            leaners = any("lean" in (r[i] or "").lower() for i in cols.values() if i is not None and i < len(r))
            sample = clean(r[2])
            key = (pollster, clean(r[1]))
            row = {"pollster": pollster, "dates": clean(r[1]), "sample": sample,
                   "moe": clean(r[3]).replace("±", "±"), **vals}
            score = (2 if "LV" in sample else 1) * (0 if leaners else 1)
            if key not in seen:
                seen[key] = (score, len(out["polls"]))
                out["polls"].append(row)
            elif score > seen[key][0]:               # prefer likely voters, no leaners
                out["polls"][seen[key][1]] = row
                seen[key] = (score, seen[key][1])
        out["polls"] = out["polls"][:N_POLLS]
        break

    # ratings table: header has "Source" and "Ranking"
    for t in tables(general):
        h, rows = parse_table(t)
        if not ("Source" in h and any(x in ("Ranking", "Rating") for x in h)):
            continue
        got = {}
        for r in rows:
            if len(r) < 3:
                continue
            src = clean(r[0])
            m = re.search(r"\{\{(?:USRaceRating|US political race rating)\|([^}]*)\}\}", r[1])
            if not m:
                continue
            parts = [p.strip() for p in m.group(1).split("|")]
            if parts[0].lower() == "tossup":
                rating = "Toss-up"
            else:
                rating = f"{parts[0]} {parts[1]}" if len(parts) > 1 else parts[0]
                if len(parts) > 2 and parts[2].lower() == "flip":
                    rating += " (flip)"
            got[src] = {"source": src, "rating": rating, "as_of": clean(r[2])}
        out["ratings"] = [got[s] for s in RATERS if s in got]
        break

    if out["polls"]:
        out["poll_avg"] = {c["party"]: round(sum(p[c["party"]] for p in out["polls"]) / len(out["polls"]), 1)
                           for c in cands}
    out["url"] = "https://en.wikipedia.org/wiki/" + race["wiki"]
    return out


# ------------------------------------------------------------------ betting markets
def kalshi(race):
    res = {}
    for party, ticker in race["kalshi"].items():
        m = get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}")["market"]
        res[party] = round(float(m["last_price_dollars"]) * 100, 1)
    return {"source": "Kalshi", "url": "https://kalshi.com", **res}


def polymarket(race):
    ev = get("https://gamma-api.polymarket.com/events?slug=" + race["polymarket"])[0]
    res = {}
    for m in ev["markets"]:
        title = m.get("groupItemTitle") or ""
        for c in race["cands"]:
            if c["match"] in title and m.get("outcomePrices"):
                res[c["party"]] = round(float(json.loads(m["outcomePrices"])[0]) * 100, 1)
    return {"source": "Polymarket", "url": "https://polymarket.com/event/" + race["polymarket"], **res}


def predictit(race, _cache={}):
    if "all" not in _cache:
        _cache["all"] = get("https://www.predictit.org/api/marketdata/all/")
    m = next(x for x in _cache["all"]["markets"] if x["id"] == race["predictit"])
    res = {}
    for c in m["contracts"]:
        n = c["name"].lower()          # e.g. "Democratic", "Democrats (Talarico)", "Republican (Paxton)"
        p = "D" if n.startswith("democrat") else "R" if n.startswith("republican") else None
        if p and c.get("lastTradePrice") is not None:
            res[p] = round(c["lastTradePrice"] * 100, 1)
    return {"source": "PredictIt", "url": m["url"], **res}


# ------------------------------------------------------------------ main
def main() -> int:
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"races": {}}
    now = datetime.now(timezone.utc).isoformat(timespec="minutes")
    out = {"updated": now, "races": {}}
    problems = 0
    for key, race in RACES.items():
        prev = old.get("races", {}).get(key, {})
        r = {k: race[k] for k in ("state", "state_name", "office", "title", "cands")}
        try:
            w = wiki_race(race)
            if not w["polls"] or not w["ratings"]:
                raise ValueError(f"parsed {len(w['polls'])} polls / {len(w['ratings'])} ratings")
            r.update(w, wiki_fetched=now)
        except Exception as e:                   # keep last good copy
            problems += 1
            print(f"{key}: Wikipedia failed ({e}); keeping previous data", file=sys.stderr)
            for f in ("polls", "averages", "average_of_averages", "ratings", "poll_avg", "url", "wiki_fetched"):
                if f in prev:
                    r[f] = prev[f]
        markets = []
        prev_m = {m["source"]: m for m in prev.get("markets", [])}
        for fn in (kalshi, polymarket, predictit):
            name = fn.__name__.capitalize().replace("Predictit", "PredictIt").replace("Polymarket", "Polymarket")
            try:
                markets.append({**fn(race), "fetched": now})
            except Exception as e:
                problems += 1
                print(f"{key}: {name} failed ({e}); keeping previous", file=sys.stderr)
                for src, m in prev_m.items():
                    if src.lower() == fn.__name__:
                        markets.append(m)
        r["markets"] = markets
        out["races"][key] = r
        print(f"{key}: {len(r.get('polls', []))} polls, {len(r.get('averages', []))} averages, "
              f"{len(r.get('ratings', []))} ratings, {len(markets)} markets")
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}" + (f" ({problems} source(s) fell back to previous data)" if problems else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
