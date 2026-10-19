"""Find DNS records that point at hosted services which no longer exist: subdomain-takeover candidates.

Records come from every configured DNS provider: Route 53 (queried live via the pinned AWS profile) plus the
dns.json each other collector wrote (Cloudflare, Azure DNS, Cloud DNS, Vercel, Netlify). Live targets come
from the collected inventories. A CNAME to a takeover-prone service suffix that matches nothing live is reported.
Elastic Beanstalk prefixes are also checked for availability (claimable=True means anyone can register it).

Read-only; prints results, writes nothing.  Usage: python3 -I scripts/dns-check.py [--all]
  --all  also lists targets on providers that weren't collected (shown as "unverified")."""
import glob, json, os, re, subprocess, sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(root, "tech-map.config.json")))
aws = cfg.get("providers", {}).get("aws")
env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
if aws: env["AWS_PROFILE"] = aws["profile"]

def awsj(*a):
    r = subprocess.run(["aws", *a, "--output", "json"], capture_output=True, text=True, env=env)
    return json.loads(r.stdout or "{}") if r.returncode == 0 else {}

def load(*p):
    f = os.path.join(root, "data", *p)
    return json.load(open(f)) if os.path.exists(f) else {}

norm = lambda h: (h or "").lower().rstrip(".").removeprefix("dualstack.")

# ── records
records = []
if aws:
    for z in awsj("route53", "list-hosted-zones").get("HostedZones", []):
        for rr in awsj("route53", "list-resource-record-sets", "--hosted-zone-id", z["Id"]).get("ResourceRecordSets", []):
            tgts = [rr["AliasTarget"]["DNSName"]] if rr.get("AliasTarget") else [r["Value"] for r in rr.get("ResourceRecords", [])]
            records += [{"source": "route53", "name": rr["Name"], "type": rr["Type"], "target": t} for t in tgts if rr["Type"] in ("CNAME", "A", "AAAA")]
for f in glob.glob(os.path.join(root, "data", "*", "dns.json")):
    p = f.split(os.sep)[-2]
    records += [{"source": p, **r} for r in json.load(open(f)).get("records", [])]

# ── live targets from the inventories
live = set()
inv = load("inv.json")
for e in inv.get("eb", []): live.add(norm(e.get("cname")))
for s in load("aws", "cloudfront.json").get("Distributions", []): live.add(norm(s["DomainName"]))
buckets = {b["name"] for b in load("aws", "s3.json").get("Buckets", [])}
for rows in inv.get("other", {}).values():
    for r in rows:
        for h in (r.get("host") or "").split(","):
            if h: live.add(norm(h))
collected = set(cfg.get("providers", {}))

# suffix → (provider that owns it, how claimable it is when missing)
PRONE = [
    (r"\.elasticbeanstalk\.com$", "aws", "EB env"), (r"\.s3[.-].*amazonaws\.com$|\.s3-website[.-].*amazonaws\.com$", "aws", "S3 bucket"),
    (r"\.cloudfront\.net$", "aws", "CloudFront (not claimable by name; stale)"),
    (r"\.azurewebsites\.net$", "azure", "App Service"), (r"\.cloudapp\.(net|azure\.com)$", "azure", "Cloud service / VM"),
    (r"\.trafficmanager\.net$", "azure", "Traffic Manager"), (r"\.blob\.core\.windows\.net$|\.web\.core\.windows\.net$", "azure", "Storage"),
    (r"\.azureedge\.net$|\.azurefd\.net$", "azure", "CDN / Front Door"), (r"\.azurecontainerapps\.io$", "azure", "Container App"),
    (r"\.run\.app$", "gcp", "Cloud Run"), (r"\.appspot\.com$", "gcp", "App Engine"), (r"^c\.storage\.googleapis\.com$", "gcp", "GCS bucket (CNAME)"),
    (r"\.pages\.dev$", "cloudflare", "Pages"), (r"\.workers\.dev$", "cloudflare", "Worker"),
    (r"\.vercel\.app$|^cname\.vercel-dns\.com$", "vercel", "Vercel project"), (r"\.netlify\.(app|com)$", "netlify", "Netlify site"),
    (r"\.herokuapp\.com$|\.herokudns\.com$", "heroku", "Heroku app"), (r"\.github\.io$", "github", "GitHub Pages"),
    (r"\.fly\.dev$", "fly", "Fly app"), (r"\.ondigitalocean\.app$", "digitalocean", "App Platform"),
]
dangling, unverified = [], []
for r in records:
    t = norm(r["target"]); name = norm(r["name"])
    for pat, prov, what in PRONE:
        if not re.search(pat, t):
            continue
        if what == "S3 bucket" or what == "GCS bucket (CNAME)":
            ok = name in buckets if prov == "aws" else name in live or f"storage.googleapis.com/{name}" in live
        elif t.startswith("cname.vercel-dns.com"):
            ok = name in live  # Vercel: the record's own name must be a domain on some project
        else:
            ok = t in live
        if ok:
            break
        if prov not in collected:
            unverified.append(f"{r['name']:<45} -> {t:<60} {what} ({prov} not collected)")
            break
        extra = ""
        if what == "EB env" and ".eba-" not in t and aws:
            region = (re.search(r"(us|eu|ap|sa|ca|me|af)-[a-z]+-\d", t) or [None])[0] or "us-east-1"
            a = subprocess.run(["aws", "elasticbeanstalk", "check-dns-availability", "--region", region, "--cname-prefix", t.split(".")[0],
                                "--query", "Available", "--output", "text"], capture_output=True, text=True, env=env).stdout.strip()
            extra = f" claimable={a or '?'}"
        dangling.append(f"{r['name']:<45} -> {t:<60} {what} not found in {prov}{extra}  [{r['source']}]")
        break

print(f"{len(records)} records checked across {', '.join(sorted({r['source'] for r in records})) or 'no DNS providers'}")
print("\n".join(dangling) if dangling else "no dangling records found")
if unverified and "--all" in sys.argv:
    print("\nunverified (provider not collected):\n" + "\n".join(unverified))
elif unverified:
    print(f"({len(unverified)} records point at providers that weren't collected; rerun with --all to list them)")
