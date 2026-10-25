"""
oh_save_agg.py — save the Ohio counts returned by ingestor/oh_browser_return.js.

The browser step returns the counts between <<<OHSTART>>> and <<<OHEND>>>; the tool result is
saved to a file (JSON, possibly with escaped newlines). This pulls the counts out and writes
data/incoming/oh/OH_2026_agg_<report date>.txt, which ingestor/oh_absentee.py reads.

Run:  python ingestor/oh_save_agg.py <tool-results file>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "incoming" / "oh"


def main(path: str) -> int:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        txt = "".join(x.get("text", "") for x in json.loads(raw))
    except (ValueError, AttributeError, TypeError):
        txt = raw
    if "<<<OHSTART>>>" not in txt or "<<<OHEND>>>" not in txt:
        print("no <<<OHSTART>>> ... <<<OHEND>>> block found")
        return 1
    body = txt[txt.index("<<<OHSTART>>>") + 13:txt.index("<<<OHEND>>>")]
    body = body.replace("\\n", "\n").replace('\\"', '"')      # undo JSON-in-JSON escaping
    lines = body.split("\n")
    if not (lines[0].startswith("STAMP=") and any(l.startswith("AGG=") for l in lines)):
        print("unexpected content:", body[:120])
        return 1
    stamp = lines[0].split("=", 1)[1][:10]
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / f"OH_2026_agg_{stamp}.txt"
    dst.write_text(body, encoding="utf-8", newline="")
    print(f"saved {dst.name} ({len(body):,} chars, report {lines[0].split('=', 1)[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]) if len(sys.argv) > 1 else (print(__doc__) or 1))
