// oh_browser_aggregate.js — run in the browser pane on https://data.ohiosos.gov/portal/election-dashboards
//
// Ohio's statewide absentee/early-vote file (publicfiles.ohiosos.gov/.../Absentee_Request_Report.txt,
// one row per voter, ~270 MB, updated weekdays ~11 AM) is refused to scripts but is readable from the
// Secretary of State's own data portal page. This reduces it IN THE BROWSER to counts only (no names,
// addresses or IDs) and saves them as OH_2026_agg_<report date>.txt in the Downloads folder:
//   STAMP=<report timestamp>
//   AGG=county|returned date|I or M|n;...      I = in person (ballot sent and returned the same day), M = mail
//   PARTY=date|I or M|party|n;...              party from primary-ballot history (D/R/L, U = none)
//   REQ=county|requests;...
// Then run:  python ingestor/oh_absentee.py   (it picks the newest Downloads/OH_2026_agg_*.txt)
(async () => {
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
  const out = `STAMP=${stamp}\nAGG=${j(agg)}\nPARTY=${j(pty)}\nREQ=${j(req)}\n`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([out], {type: "text/plain"}));
  a.download = `OH_2026_agg_${stamp.slice(0, 10)}.txt`;
  document.body.appendChild(a); a.click(); a.remove();
  return `saved ${a.download}: ${Object.keys(agg).length} county-day rows, report ${stamp}`;
})()
