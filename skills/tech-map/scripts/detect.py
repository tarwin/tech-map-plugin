"""Work out which hosting providers a company uses and what's available to inspect them. Read-only.

Usage: python3 -I detect.py <repos-dir>

Prints:
  1. Provider hints found in the repos (deploy configs, SDK imports, hostnames), with example files.
  2. Which CLIs are installed and which credentials exist locally: AWS profiles, gcloud configurations,
     Azure subscriptions, and whether token env vars are set. Tokens themselves are never printed.
Use the output to ask the user which providers/profiles/projects to map."""
import json, os, re, shutil, subprocess, sys

repos = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "..")
SKIP = {"node_modules", ".git", "dist", "build", ".next", ".nuxt", ".output", ".vite", ".turbo", ".cache", "vendor", "venv", ".venv", "__pycache__", "Pods", ".dart_tool", "target", "coverage"}
LOCKFILES = {"pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lockb", "poetry.lock", "Pipfile.lock", "Gemfile.lock", "composer.lock", "pubspec.lock", "Podfile.lock", "go.sum", "Cargo.lock"}

# filename (exact) or regex on file content → provider
FILES = {
    "aws": ["serverless.yml", "serverless.yaml", "template.yaml", "samconfig.toml", "cdk.json", "buildspec.yml", "appspec.yml", "Dockerrun.aws.json", "apprunner.yaml"],
    "aws-eb": [".elasticbeanstalk", ".ebextensions"],
    "gcp": ["app.yaml", "cloudbuild.yaml", "cloudbuild.yml", ".gcloudignore", "firebase.json", ".firebaserc"],
    "azure": ["azure-pipelines.yml", "host.json", "staticwebapp.config.json", "azure.yaml", ".deployment"],
    "cloudflare": ["wrangler.toml", "wrangler.json", "wrangler.jsonc"],
    "vercel": ["vercel.json", ".vercel"],
    "netlify": ["netlify.toml", "_redirects"],
    "fly": ["fly.toml"], "heroku": ["Procfile.heroku", "app.json", "heroku.yml"], "render": ["render.yaml"], "railway": ["railway.json", "railway.toml"],
    "digitalocean": [".do"], "terraform": [], "pulumi": ["Pulumi.yaml"],
}
CONTENT = [
    ("aws", r"@aws-sdk/|aws-sdk|boto3|amazonaws\.com"), ("gcp", r"@google-cloud/|google\.cloud|storage\.googleapis\.com|\.run\.app\b|appspot\.com"),
    ("azure", r"@azure/|azure\.(storage|identity)|\.windows\.net|azurewebsites\.net"), ("cloudflare", r"workers\.dev|pages\.dev|api\.cloudflare\.com|@cloudflare/|r2\.cloudflarestorage\.com"),
    ("vercel", r"@vercel/|vercel\.app"), ("netlify", r"netlify\.app|@netlify/"), ("supabase", r"supabase\.co|@supabase/"),
    ("firebase", r"firebase(app|io)?\.com|firebase-admin|firebase/"), ("terraform", r'provider\s+"(aws|google|azurerm|cloudflare)"'),
]
TEXT_EXT = {".js", ".ts", ".tsx", ".jsx", ".mjs", ".py", ".go", ".java", ".kt", ".rb", ".php", ".cs", ".json", ".yml", ".yaml", ".toml", ".tf", ".dart", ".swift", ".env.example"}

strong, weak = {}, {}   # strong: deploy config files; weak: references in code
def hit(p, path, bucket=None):
    bucket = strong if bucket is None else bucket
    rel = os.path.relpath(path, repos); repo = rel.split(os.sep)[0]
    e = bucket.setdefault(p, {"repos": set(), "eg": []})
    e["repos"].add(repo)
    if len(e["eg"]) < 3 and rel not in e["eg"]: e["eg"].append(rel)

for d, dirs, files in os.walk(repos):
    for name in files + dirs:  # match config names before pruning, so .elasticbeanstalk / .vercel count
        for p, names in FILES.items():
            if name in names: hit(p, os.path.join(d, name))
        if name.endswith(".tf"): hit("terraform", os.path.join(d, name))
    dirs[:] = [x for x in dirs if x not in SKIP and not (x.startswith(".") and x not in (".github", ".circleci"))]
    if d.count(os.sep) - repos.count(os.sep) > 5:
        dirs[:] = []; continue
    for name in files:
        f = os.path.join(d, name)
        if name in LOCKFILES or name.endswith((".min.js", ".map")) or os.path.splitext(name)[1] not in TEXT_EXT or os.path.getsize(f) > 300_000:
            continue
        if ".env" in name and not name.endswith(".example"):
            continue  # never open real .env files
        try: txt = open(f, errors="ignore").read()
        except OSError: continue
        for p, rx in CONTENT:
            if re.search(rx, txt): hit(p, f, weak)

print(f"== deploy / infra config files in {repos} (strong evidence)")
for p in sorted(strong, key=lambda k: -len(strong[k]["repos"])):
    print(f"  {p:<13} {len(strong[p]['repos']):>3} repos  e.g. {', '.join(strong[p]['eg'])}")
print("\n== references in code (weaker: SDKs, hostnames)")
for p in sorted(weak, key=lambda k: -len(weak[k]["repos"])):
    print(f"  {p:<13} {len(weak[p]['repos']):>3} repos  e.g. {', '.join(weak[p]['eg'])}")

def out(cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired): return ""

print("\n== local tooling and credentials (no secrets printed)")
cli = lambda c: "installed" if shutil.which(c) else "not installed"
print(f"  aws CLI: {cli('aws')}")
if shutil.which("aws"):
    print("    profiles:", ", ".join(out(["aws", "configure", "list-profiles"]).split()) or "none")
    if os.environ.get("AWS_PROFILE"): print(f"    note: shell has AWS_PROFILE={os.environ['AWS_PROFILE']} set. Collectors ignore it and use the configured profile.")
print(f"  gcloud: {cli('gcloud')}")
if shutil.which("gcloud"):
    for c in json.loads(out(["gcloud", "config", "configurations", "list", "--format=json"]) or "[]"):
        print(f"    configuration {c['name']}: account={c.get('properties', {}).get('core', {}).get('account')} project={c.get('properties', {}).get('core', {}).get('project')}{' (active)' if c.get('is_active') else ''}")
print(f"  az: {cli('az')}")
if shutil.which("az"):
    for s in json.loads(out(["az", "account", "list", "--output", "json", "--only-show-errors"]) or "[]"):
        print(f"    subscription {s['id']}  {s['name']}{' (default)' if s.get('isDefault') else ''}")
for env, p in (("CLOUDFLARE_API_TOKEN", "cloudflare"), ("VERCEL_TOKEN", "vercel"), ("NETLIFY_AUTH_TOKEN", "netlify")):
    print(f"  {p} token env {env}: {'set' if os.environ.get(env) else 'not set'}")
