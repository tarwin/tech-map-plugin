"""Cloudflare inventory via the REST API (read-only). Config: providers.cloudflare = {tokenEnv: "CLOUDFLARE_API_TOKEN", accounts?: [id]}.

Use an API token with read-only permissions: Account Settings, Zone, DNS, Workers Scripts, Workers Routes,
Pages, R2, D1, Workers KV, Queues, and Analytics (all :Read). The token is read from the environment only.
Collects zones (with request totals), DNS records, Workers (with invocation totals) and their routes,
Pages projects, R2 buckets, D1 databases, KV namespaces and Queues."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir; common.py lives here
from common import config, window, token, http_json, row, write

cfg = config()["providers"]["cloudflare"]
tok = token(cfg.get("tokenEnv", "CLOUDFLARE_API_TOKEN"), "cloudflare")
API = "https://api.cloudflare.com/client/v4"
days, start, end = window()

def pages(path, key=None):
    """All results of a paginated list endpoint."""
    out, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        d = http_json(f"{API}{path}{sep}page={page}&per_page=50", tok) or {}
        r = d.get("result") or []
        r = r.get(key, []) if key and isinstance(r, dict) else r
        out += r
        info = d.get("result_info") or {}
        if not r or page >= (info.get("total_pages") or 1):
            return out
        page += 1

def gql(query, variables):
    d = http_json(f"{API}/graphql", tok, "POST", {"query": query, "variables": variables}) or {}
    if d.get("errors"):
        print("  skip: analytics:", (d["errors"][0].get("message") or "")[:100]); return {}
    return d.get("data") or {}

since, until = start.date().isoformat(), end.date().isoformat()
res, dns = [], []
accounts = cfg.get("accounts") or [a["id"] for a in pages("/accounts")]
for z in pages("/zones"):
    print("== cloudflare zone", z["name"])
    q = gql("""query($z: String!, $s: Date!, $u: Date!) { viewer { zones(filter: {zoneTag: $z}) {
               httpRequests1dGroups(limit: 400, filter: {date_geq: $s, date_leq: $u}) { sum { requests } } } } }""",
            {"z": z["id"], "s": since, "u": until})
    groups = ((q.get("viewer") or {}).get("zones") or [{}])[0].get("httpRequests1dGroups", []) if q else []
    vol = sum(g["sum"]["requests"] for g in groups) if groups else None
    recs = pages(f"/zones/{z['id']}/dns_records")
    for r in recs:
        if r["type"] in ("CNAME", "A", "AAAA"):
            dns.append({"zone": z["name"], "name": r["name"] + ".", "type": r["type"], "target": r["content"], "proxied": r.get("proxied")})
    res.append(row(z["account"]["name"], "", "Zone", z["name"], z["name"], f"{z.get('plan', {}).get('name', '')} · {len(recs)} DNS records · {z['status']}", vol))
    for rt in pages(f"/zones/{z['id']}/workers/routes"):
        res.append(row(z["account"]["name"], "", "Worker route", rt.get("pattern"), rt.get("pattern", "").split("/")[0].replace("*", ""), f"→ {rt.get('script') or '(none)'}",
                       flags=[] if rt.get("script") else ["route with no script"]))

for a in accounts:
    print("== cloudflare account", a)
    q = gql("""query($a: String!, $s: Time!, $u: Time!) { viewer { accounts(filter: {accountTag: $a}) {
               workersInvocationsAdaptive(limit: 1000, filter: {datetime_geq: $s, datetime_leq: $u}) { sum { requests errors } dimensions { scriptName } } } } }""",
            {"a": a, "s": start.isoformat().replace("+00:00", "Z"), "u": end.isoformat().replace("+00:00", "Z")})
    inv = {}
    for g in (((q.get("viewer") or {}).get("accounts") or [{}])[0].get("workersInvocationsAdaptive", []) if q else []):
        n = g["dimensions"]["scriptName"]; s = inv.setdefault(n, [0, 0]); s[0] += g["sum"]["requests"]; s[1] += g["sum"]["errors"]
    for w in pages(f"/accounts/{a}/workers/scripts"):
        req, err = inv.get(w["id"], [None, None])
        res.append(row(a, "", "Worker", w["id"], "", f"modified {w.get('modified_on', '')[:10]}" + (f" · {err} errors" if err else ""), req))
    for p in pages(f"/accounts/{a}/pages/projects"):
        src = (p.get("source") or {}).get("config", {})
        last = (p.get("latest_deployment") or {}).get("modified_on", "")[:10]
        res.append(row(a, "", "Pages project", p["name"], ",".join([p.get("subdomain", "")] + (p.get("domains") or [])),
                       f"{src.get('owner', '')}/{src.get('repo_name', '')} · last deploy {last}".strip(" /·")))
    for b in pages(f"/accounts/{a}/r2/buckets", "buckets"):
        res.append(row(a, b.get("location", ""), "R2 bucket", b["name"], "", f"created {b.get('creation_date', '')[:10]}"))
    for d in pages(f"/accounts/{a}/d1/database"):
        res.append(row(a, "", "D1 database", d["name"], "", f"{d.get('num_tables', '?')} tables"))
    for k in pages(f"/accounts/{a}/storage/kv/namespaces"):
        res.append(row(a, "", "KV namespace", k["title"]))
    for qd in pages(f"/accounts/{a}/queues"):
        res.append(row(a, "", "Queue", qd.get("queue_name"), "", f"{len(qd.get('producers') or [])} producers · {len(qd.get('consumers') or [])} consumers",
                       flags=[] if qd.get("consumers") else ["no consumer"]))
write("cloudflare", res, dns)
