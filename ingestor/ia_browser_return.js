// ia_browser_return.js — run in the browser pane on any https://sos.iowa.gov/ page (javascript tool).
// The Iowa SoS site refuses scripted downloads (403), so the daily task reads the two absentee
// statistics PDFs from inside the site and RETURNS them base64-encoded between <<<IASTART>>> and
// <<<IAEND>>> (padded, so the result is saved to a tool-results file). Then:
//     python ingestor/ia_save.py <that tool-results file>
// NOTE: open an HTML page first (e.g. https://sos.iowa.gov/elections-voting). Navigating the pane
// straight to a .pdf URL makes the site send a file download, which pops a save dialog.
(async () => {
  const files = {};
  for (const f of ["AbsenteeCounty2026", "AbsenteeCongressional2026"]) {
    const r = await fetch(`/elections/pdf/2026/general/${f}.pdf`, {cache: "no-store"});
    if (!r.ok) { files[f] = {status: r.status}; continue; }
    const b = new Uint8Array(await r.arrayBuffer());
    let s = "";
    for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
    files[f] = {status: r.status, modified: r.headers.get("last-modified"), b64: btoa(s)};
  }
  return "<<<IASTART>>>" + JSON.stringify(files) + "<<<IAEND>>>" + " ".repeat(40000);
})()
