"""
nv_save.py — save Nevada's VIVID dashboard data returned by ingestor/nv_browser_return.js.

Writes data/incoming/nv/vivid_<generatedAt date>.json (aggregate counts only); keeping one per day
builds the 2026 mail-ballot history, which the dashboard itself only shows as a current total.

Run:  python ingestor/nv_save.py <tool-results file>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "incoming" / "nv"


def main(path: str) -> int:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        txt = "".join(x.get("text", "") for x in json.loads(raw))
    except (ValueError, AttributeError, TypeError):
        txt = raw
    if "<<<NVSTART>>>" not in txt:
        print("no <<<NVSTART>>> ... <<<NVEND>>> block found")
        return 1
    body = txt[txt.index("<<<NVSTART>>>") + 13:txt.index("<<<NVEND>>>")]
    if body.startswith("{\\"):                       # JSON-in-JSON escaping
        body = json.loads('"' + body + '"')
    data = json.loads(body)
    stamp = data["ballots"].get("generatedAt") or data["turnout"]["generatedAt"]
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / f"vivid_{stamp[:10]}.json"
    dst.write_text(json.dumps(data), encoding="utf-8")
    days = data["turnout"]["days"]
    print(f"saved {dst.name}: in-person days {days[0]['date']}..{days[-1]['date']}, "
          f"ballot data generated {stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]) if len(sys.argv) > 1 else (print(__doc__) or 1))
