"""Netlify inventory via the REST API (read-only). Config: providers.netlify = {tokenEnv: "NETLIFY_AUTH_TOKEN"}.

Collects sites (custom domains, repo, last publish) and Netlify DNS zones/records. Build environment
variables are never requested. Create a personal access token under User settings → Applications.
The token is read from the environment only."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir; common.py lives here
from common import config, token, http_json, row, write

cfg = config()["providers"]["netlify"]
tok = token(cfg.get("tokenEnv", "NETLIFY_AUTH_TOKEN"), "netlify")
API = "https://api.netlify.com/api/v1"

def listing(path):
    out, page = [], 1
    while True:
        d = http_json(f"{API}{path}?page={page}&per_page=100", tok) or []
        out += d
        if len(d) < 100:
            return out
        page += 1

res, dns = [], []
print("== netlify")
for s in listing("/sites"):
    hosts = [h for h in [s.get("custom_domain")] + (s.get("domain_aliases") or []) + [(s.get("default_domain") or s.get("url", "").split("://")[-1])] if h]
    pub = (s.get("published_deploy") or {}).get("published_at", "")[:10] or "never"
    repo = (s.get("build_settings") or {}).get("repo_url", "") or "manual deploys"
    res.append(row(s.get("account_slug", ""), "", "Site", s["name"], ",".join(hosts), f"{repo} · last publish {pub}",
                   flags=["no published deploy"] if pub == "never" else []))
for z in listing("/dns_zones"):
    res.append(row(z.get("account_slug", ""), "", "DNS zone", z["name"], z["name"]))
    for r in http_json(f"{API}/dns_zones/{z['id']}/dns_records", tok) or []:
        if r.get("type") in ("CNAME", "A", "AAAA", "NETLIFY"):
            dns.append({"zone": z["name"], "name": r["hostname"] + ".", "type": r["type"], "target": r.get("value")})
write("netlify", res, dns)
