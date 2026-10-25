// oh_browser_return.js — run in the browser pane on https://data.ohiosos.gov/portal/election-dashboards
// (javascript tool). Same counts-only reduction as oh_browser_aggregate.js, but instead of a file
// download (pane downloads don't reach disk) it RETURNS the counts wrapped in <<<OHSTART>>> ...
// <<<OHEND>>> and padded, so the tool result is too long to show inline and is saved to a
// tool-results file. Then:  python ingestor/oh_save_agg.py <that tool-results file>
//
// The statewide file is ~270 MB; fetching + reducing takes ~20-40 s. If the tool times out, run
// it again — it reuses window.__oh once the first run has finished.
(async () => {
  if (!window.__oh || window.__oh.status !== "done") {
    const t = await (await fetch("https://publicfiles.ohiosos.gov/free/absentee_public_export/Absentee_Request_Report.txt",
                                 {cache: "no-store"})).text();
    const L = t.split("\r\n"), H = L[0].split("\t"), ix = n => H.indexOf(n), q = s => (s || "").replace(/"/g, "");
    const ret = ix("BALLOT_RETURNED_DATE"), sent = ix("BALLOT_SENT_DATE"), par = ix("VOTER_PARTY"),
          cty = ix("COUNTY"), ts = ix("Report_TS");
    const agg = {}, pty = {}, req = {};
    let stamp = "";
    for (let i = 1; i < L.length; i++) {
      const f = L[i].split("\t");
      if (f.length < H.length) continue;
      stamp = q(f[ts]);
      const c = q(f[cty]);
      req[c] = (req[c] || 0) + 1;
      const r = q(f[ret]).slice(0, 10);
      if (!/^2026-(09|10|11)-/.test(r)) continue;
      const m = q(f[sent]).slice(0, 10) === r ? "I" : "M";
      agg[`${c}|${r}|${m}`] = (agg[`${c}|${r}|${m}`] || 0) + 1;
      const pk = `${r}|${m}|${q(f[par]) || "U"}`;
      pty[pk] = (pty[pk] || 0) + 1;
    }
    const j = o => Object.entries(o).map(([k, v]) => `${k}|${v}`).join(";");
    window.__oh = {status: "done", stamp, out: `STAMP=${stamp}\nAGG=${j(agg)}\nPARTY=${j(pty)}\nREQ=${j(req)}\n`};
  }
  return "<<<OHSTART>>>" + window.__oh.out + "<<<OHEND>>>" + " ".repeat(40000);
})()
