"""
ia_save.py — save the Iowa SoS absentee PDFs returned by ingestor/ia_browser_return.js.

Writes data/incoming/ia/sos/<name>_<report date>.pdf (the report date is read from inside the
PDF, so re-saving the same day's report is harmless), then ingestor/ia_fetch.py parses them.

Run:  python ingestor/ia_save.py <tool-results file>
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ia_fetch import INC, parse_pdf  # noqa: E402


def main(path: str) -> int:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        txt = "".join(x.get("text", "") for x in json.loads(raw))
    except (ValueError, AttributeError, TypeError):
        txt = raw
    if "<<<IASTART>>>" not in txt:
        print("no <<<IASTART>>> ... <<<IAEND>>> block found")
        return 1
    body = txt[txt.index("<<<IASTART>>>") + 13:txt.index("<<<IAEND>>>")]
    if body.startswith("{\\"):                       # JSON-in-JSON escaping
        body = json.loads('"' + body + '"')
    files = json.loads(body)
    out = INC / "sos"
    out.mkdir(parents=True, exist_ok=True)
    ok = 0
    for name, f in files.items():
        if f.get("status") != 200 or not f.get("b64"):
            print(f"{name}: HTTP {f.get('status')} — skipped")
            continue
        tmp = out / f"{name}.tmp.pdf"
        tmp.write_bytes(base64.b64decode(f["b64"]))
        rd, data = parse_pdf(tmp)
        dst = out / f"{name}_{rd.isoformat()}.pdf"
        tmp.replace(dst)
        print(f"saved {dst.name}: report {rd}, {len(data) - 1} areas, statewide received "
              f"{data['STATE'].get('TOTAL', 0):,} (site last-modified {f.get('modified')})")
        ok += 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]) if len(sys.argv) > 1 else (print(__doc__) or 1))
