"""Shared helpers for the non-AWS collectors.

Every collector writes the same two files so inv.py and dns-check.py can treat providers alike:

  data/<provider>/resources.json  {"resources": [row, ...]}
      row = {scope, region, type, name, host, detail, vol, flags}
        scope  project / subscription / account / team the resource belongs to
        host   comma-separated public hostnames it serves (used as "live targets" by dns-check)
        vol    activity over the window (requests, executions…), or null when not collected
        flags  list of short risk notes, e.g. "authorized network 0.0.0.0/0"
  data/<provider>/dns.json        {"records": [{zone, name, type, target}, ...]}

Rules every collector follows:
  - Read-only calls only.
  - Never write environment variables, app settings, connection strings, keys or tokens.
    Pick the fields you want; never dump a whole resource description.
  - API tokens are read from the environment variable named in the config, never stored.
  - Any call that fails (no permission, API disabled) is logged and skipped, not fatal.
"""
import datetime, json, os, subprocess, sys, urllib.error, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

def config():
    return json.load(open(os.path.join(ROOT, "tech-map.config.json")))

def window():
    days = int(config().get("windowDays", 7))
    end = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    return days, end - datetime.timedelta(days=days), end

def warn(msg):
    print("  skip:", msg, file=sys.stderr)

def run_json(cmd, env=None):
    """Run a CLI that prints JSON. Returns parsed JSON, or None on failure."""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        warn(f"{' '.join(cmd[:4])}: {e}"); return None
    if res.returncode != 0:
        warn(f"{' '.join(cmd[:5])}: {(res.stderr or '').strip().splitlines()[-1:] or ['failed']}"); return None
    try:
        return json.loads(res.stdout or "null")
    except json.JSONDecodeError:
        warn(f"{' '.join(cmd[:4])}: not JSON"); return None

def token(env_name, provider):
    t = os.environ.get(env_name or "")
    if not t:
        sys.exit(f"{provider}: set the {env_name} environment variable to a read-only API token (it is never written to disk)")
    return t

def http_json(url, tok, method="GET", body=None, headers=None):
    """JSON request with a Bearer token. Returns parsed JSON, or None on failure."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        warn(f"{method} {url.split('?')[0]}: HTTP {e.code}"); return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        warn(f"{method} {url.split('?')[0]}: {e}"); return None

def row(scope, region, type_, name, host="", detail="", vol=None, flags=None):
    return {"scope": scope, "region": region or "", "type": type_, "name": name, "host": host or "",
            "detail": detail or "", "vol": vol, "flags": ", ".join(flags or [])}

def write(provider, resources, records=None):
    d = os.path.join(ROOT, "data", provider)
    os.makedirs(d, exist_ok=True)
    json.dump({"resources": resources}, open(os.path.join(d, "resources.json"), "w"), indent=1)
    json.dump({"records": records or []}, open(os.path.join(d, "dns.json"), "w"), indent=1)
    print(f"{provider}: {len(resources)} resources, {len(records or [])} DNS records -> data/{provider}/")

def host_of(url):
    return (url or "").split("://")[-1].split("/")[0]
