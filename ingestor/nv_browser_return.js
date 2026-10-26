// nv_browser_return.js — run in the browser pane on https://www.nvsos.gov/vivid/ (javascript tool).
// Nevada's VIVID dashboard data (aggregate counts by county and party, no voter rows) refuses
// scripts, so the daily task reads it from the page and RETURNS it between <<<NVSTART>>> and
// <<<NVEND>>> (padded, so the result is saved to a tool-results file). Then:
//     python ingestor/nv_save.py <that tool-results file>
// Do NOT download the report-*.csv files on that page: they are per-voter lists.
(async () => {
  const get = async f => (await fetch(`/vivid/data/${f}`, {cache: "no-store"})).json();
  const out = {turnout: await get("turnout-seed.json"), ballots: await get("ballot-seed.json")};
  return "<<<NVSTART>>>" + JSON.stringify(out) + "<<<NVEND>>>" + " ".repeat(40000);
})()
