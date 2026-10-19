"""Vercel inventory via the REST API (read-only). Config: providers.vercel = {tokenEnv: "VERCEL_TOKEN", teams?: ["team_id", ...]}.

Collects projects (framework, git repo, production domains, last production deploy) and domains with
their DNS records. Environment variables are never requested. Create the token under Account Settings → Tokens,
scoped to the team. The token is read from the environment only."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir; common.py lives here
import datetime
from common import config, token, http_json, row, write

cfg = config()["providers"]["vercel"]
tok = token(cfg.get("tokenEnv", "VERCEL_TOKEN"), "vercel")
API = "https://api.vercel.com"

def listing(path, key, team):
    out, until = [], None
    while True:
        q = [f"limit=100"] + ([f"teamId={team}"] if team else []) + ([f"until={until}"] if until else [])
        d = http_json(f"{API}{path}?{'&'.join(q)}", tok) or {}
        out += d.get(key) or []
        until = (d.get("pagination") or {}).get("next")
        if not until:
            return out

teams = cfg.get("teams") or [None]
res, dns = [], []
for team in teams:
    scope = team or "personal"
    print("== vercel", scope)
    for p in listing("/v9/projects", "projects", team):
        prod = (p.get("targets") or {}).get("production") or {}
        aliases = prod.get("alias") or []
        link = p.get("link") or {}
        repo = f"{link.get('org') or link.get('projectNamespace') or ''}/{link.get('repo') or link.get('projectName') or ''}".strip("/")
        last = prod.get("createdAt")
        when = datetime.datetime.fromtimestamp(last / 1000, datetime.UTC).date().isoformat() if last else "never"
        res.append(row(scope, "", "Project", p["name"], ",".join(aliases), f"{p.get('framework') or 'other'} · {repo or 'no git link'} · prod deploy {when}",
                       flags=["no production deployment"] if not last else []))
    for d in listing("/v5/domains", "domains", team):
        res.append(row(scope, "", "Domain", d["name"], d["name"], "Vercel DNS" if d.get("serviceType") == "zeit.world" else "external DNS"))
        for r in (http_json(f"{API}/v4/domains/{d['name']}/records" + (f"?teamId={team}" if team else ""), tok) or {}).get("records", []):
            if r.get("type") in ("CNAME", "A", "AAAA", "ALIAS"):
                fq = (r["name"] + "." if r.get("name") else "") + d["name"] + "."
                dns.append({"zone": d["name"], "name": fq, "type": r["type"], "target": r.get("value")})
write("vercel", res, dns)
