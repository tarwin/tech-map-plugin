// Check the built page: script syntax, and that the model hangs together.
// Usage: node scripts/validate.js <built-page.html>
// Exits 1 on any problem so it can gate a build.
const fs = require("fs");
const file = process.argv[2];
if (!file) { console.error("usage: node validate.js <page.html>"); process.exit(2); }
const html = fs.readFileSync(file, "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const problems = [];
scripts.forEach((s, i) => { try { new Function(s); } catch (e) { problems.push(`script ${i}: syntax error: ${e.message}`); } });
if (/__TITLE__|\/\*FINDINGS\*\/|\/\*INV\*\/null|<!--MODEL-->/.test(html)) problems.push("a build placeholder was not replaced");

// Evaluate the model + data scripts (everything before the UI IIFE) in a sandbox.
const vm = require("vm");
const ctx = {};
try { vm.runInNewContext(scripts.filter(s => !s.trim().startsWith("(() =>")).join("\n").replace(/^const /gm, "var "), ctx); }
catch (e) { problems.push("evaluating model: " + e.message); }
const { MAPS = {}, DOMAINS = {}, KINDS = {}, NODES = [], EDGES = [], FLOWS = [], FINDINGS = [], COLUMNS = [] } = ctx;
const ids = new Map();
NODES.forEach(n => {
  if (ids.has(n.id)) problems.push(`duplicate node id ${n.id}`);
  ids.set(n.id, n);
  if (!DOMAINS[n.d]) problems.push(`node ${n.id}: unknown domain ${n.d}`);
  if (!KINDS[n.kind]) problems.push(`node ${n.id}: unknown kind ${n.kind}`);
  if (!(n.col >= 0 && n.col < COLUMNS.length)) problems.push(`node ${n.id}: column ${n.col} out of range`);
  if (n.vol != null && !["req", "msg", "inv"].includes(n.volUnit)) problems.push(`node ${n.id}: vol without volUnit req|msg|inv`);
});
Object.entries(DOMAINS).forEach(([k, d]) => { if (!MAPS[d.map]) problems.push(`domain ${k}: unknown map ${d.map}`); });
Object.keys(MAPS).forEach(m => { if (!NODES.some(n => DOMAINS[n.d] && DOMAINS[n.d].map === m)) problems.push(`map ${m} has no nodes`); });
const TYPES = ["http", "sqs", "sns", "invoke", "s3", "data", "sched"];
const ek = new Set();
EDGES.forEach(e => {
  const [a, b, t] = e;
  if (!ids.has(a) || !ids.has(b)) problems.push(`edge ${a} → ${b}: unknown node`);
  if (!TYPES.includes(t)) problems.push(`edge ${a} → ${b}: unknown type ${t}`);
  ek.add(a + ">" + b);
});
FLOWS.forEach(f => {
  if (!DOMAINS[f.d]) problems.push(`flow ${f.id}: unknown domain ${f.d}`);
  f.steps.forEach(s => { if (!ek.has(s[0] + ">" + s[1])) problems.push(`flow ${f.id}: step ${s[0]} → ${s[1]} has no matching edge`); });
});
FINDINGS.forEach(f => { if (f.node && !ids.has(f.node)) problems.push(`finding "${f.title}": unknown node ${f.node}`); });
const lonely = NODES.filter(n => !EDGES.some(e => e[0] === n.id || e[1] === n.id)).map(n => n.id);

console.log(`${NODES.length} nodes, ${EDGES.length} edges, ${FLOWS.length} flows, ${FINDINGS.length} findings, ${Object.keys(MAPS).length} maps`);
if (lonely.length) console.log(`note: unconnected nodes (fine for leftovers): ${lonely.join(", ")}`);
if (problems.length) { console.log("PROBLEMS:\n- " + problems.join("\n- ")); process.exit(1); }
console.log("ok");
