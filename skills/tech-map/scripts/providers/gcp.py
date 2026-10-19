"""Google Cloud inventory via gcloud (read-only). Config: providers.gcp = {configuration?, projects: [...], regions?: [...]}.

Collects Cloud Run, Cloud Functions, App Engine, GKE, Compute, Cloud SQL (with authorized networks),
GCS buckets (public IAM), Pub/Sub, Cloud Scheduler, Memorystore, Firestore and Cloud DNS records.
Request / execution counts come from the Cloud Monitoring API. Env vars and secrets are never written."""
import os, subprocess, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir; common.py lives here
from common import config, window, run_json, http_json, row, write, host_of, warn

cfg = config()["providers"]["gcp"]
env = dict(os.environ)
if cfg.get("configuration"):
    env["CLOUDSDK_ACTIVE_CONFIG_NAME"] = cfg["configuration"]  # pin like the AWS profile: never the shell's active config

def g(project, *args):
    return run_json(["gcloud", *args, "--project", project, "--format=json", "--quiet"], env) or []

days, start, end = window()
# Short-lived token for the Monitoring API, from the same pinned gcloud configuration. Kept in memory only.
_t = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, env=env)
tok = _t.stdout.strip() if _t.returncode == 0 else ""
if not tok:
    warn("no gcloud access token; request counts will be empty")

def monitoring_sum(project, metric, label):
    """Sum a DELTA metric over the window, grouped by a resource label. {label_value: total}"""
    if not tok:
        return {}
    q = {"filter": f'metric.type="{metric}"', "interval.startTime": start.isoformat().replace("+00:00", "Z"),
         "interval.endTime": end.isoformat().replace("+00:00", "Z"), "aggregation.alignmentPeriod": f"{days * 86400}s",
         "aggregation.perSeriesAligner": "ALIGN_SUM", "aggregation.crossSeriesReducer": "REDUCE_SUM",
         "aggregation.groupByFields": f"resource.label.{label}"}
    d = http_json(f"https://monitoring.googleapis.com/v3/projects/{project}/timeSeries?" + urllib.parse.urlencode(q), tok) or {}
    out = {}
    for ts in d.get("timeSeries", []):
        k = ts.get("resource", {}).get("labels", {}).get(label)
        out[k] = out.get(k, 0) + sum(int(p["value"].get("int64Value", 0)) for p in ts.get("points", []))
    return out

res, dns = [], []
for p in cfg["projects"]:
    print("== gcp", p)
    runreq = monitoring_sum(p, "run.googleapis.com/request_count", "service_name")
    regions = set(cfg.get("regions", []))
    for s in g(p, "run", "services", "list", "--platform", "managed"):
        md = s.get("metadata", {}); ann = md.get("annotations", {})
        region = md.get("labels", {}).get("cloud.googleapis.com/location", "")
        regions.add(region)
        flags = ["ingress all" ] if ann.get("run.googleapis.com/ingress", "all") == "all" else []
        image = ((s.get("spec", {}).get("template", {}).get("spec", {}).get("containers") or [{}])[0].get("image", "")).split("@")[0]
        res.append(row(p, region, "Cloud Run", md.get("name"), host_of(s.get("status", {}).get("url")), image, runreq.get(md.get("name")), flags))
    fnexec = monitoring_sum(p, "cloudfunctions.googleapis.com/function/execution_count", "function_name")
    for f in g(p, "functions", "list"):
        name = f.get("name", "").split("/")[-1]
        region = f.get("name", "").split("/")[3] if f.get("name", "").count("/") >= 3 else ""
        trig = f.get("eventTrigger", {})
        url = f.get("url") or f.get("serviceConfig", {}).get("uri") or f.get("httpsTrigger", {}).get("url", "")
        detail = f"{f.get('runtime') or f.get('buildConfig', {}).get('runtime', '')} · " + (trig.get("eventType", "") + " " + (trig.get("pubsubTopic") or trig.get("resource") or "").split("/")[-1] if trig else "HTTP")
        res.append(row(p, region, "Cloud Function", name, host_of(url), detail, fnexec.get(name) or runreq.get(name)))
    for s in g(p, "app", "services", "list"):
        res.append(row(p, "", "App Engine service", s.get("id"), f"{s.get('id')}-dot-{p}.appspot.com" if s.get("id") != "default" else f"{p}.appspot.com"))
    for c in g(p, "container", "clusters", "list"):
        res.append(row(p, c.get("location"), "GKE cluster", c.get("name"), "", f"{c.get('currentNodeCount')} nodes · {c.get('currentMasterVersion')}",
                       flags=["public endpoint"] if not c.get("privateClusterConfig", {}).get("enablePrivateEndpoint") else []))
    for i in g(p, "compute", "instances", "list"):
        nat = [ac.get("natIP") for ni in i.get("networkInterfaces", []) for ac in ni.get("accessConfigs", []) if ac.get("natIP")]
        res.append(row(p, i.get("zone", "").split("/")[-1], "Compute instance", i.get("name"), ",".join(nat), f"{i.get('machineType', '').split('/')[-1]} · {i.get('status')}"))
    for d in g(p, "sql", "instances", "list"):
        ipc = d.get("settings", {}).get("ipConfiguration", {})
        nets = [n.get("value") for n in ipc.get("authorizedNetworks", [])]
        flags = [f"authorized network {n}" for n in nets if n in ("0.0.0.0/0", "::/0")] + (["public IP"] if ipc.get("ipv4Enabled") else [])
        res.append(row(p, d.get("region"), "Cloud SQL", d.get("name"), "", f"{d.get('databaseVersion')} · {d.get('settings', {}).get('tier')}", flags=flags))
    for b in g(p, "storage", "buckets", "list"):
        name = b.get("name") or b.get("id")
        pol = g(p, "storage", "buckets", "get-iam-policy", f"gs://{name}") or {}
        public = any(m in ("allUsers", "allAuthenticatedUsers") for bd in pol.get("bindings", []) for m in bd.get("members", []))
        res.append(row(p, b.get("location", ""), "GCS bucket", name, f"storage.googleapis.com/{name}", b.get("storage_class") or b.get("default_storage_class", ""),
                       flags=["public (allUsers)"] if public else []))
    subs = g(p, "pubsub", "subscriptions", "list")
    for t in g(p, "pubsub", "topics", "list"):
        tn = t.get("name", "").split("/")[-1]
        mine = [s for s in subs if s.get("topic", "").split("/")[-1] == tn]
        detail = ", ".join(("push→" + host_of(s.get("pushConfig", {}).get("pushEndpoint"))) if s.get("pushConfig", {}).get("pushEndpoint") else "pull:" + s.get("name", "").split("/")[-1] for s in mine)
        res.append(row(p, "", "Pub/Sub topic", tn, "", detail, flags=[] if mine else ["no subscriptions"]))
    for r in sorted(x for x in regions if x):
        for j in g(p, "scheduler", "jobs", "list", "--location", r):
            tgt = host_of(j.get("httpTarget", {}).get("uri")) or (j.get("pubsubTarget", {}).get("topicName", "").split("/")[-1])
            res.append(row(p, r, "Cloud Scheduler", j.get("name", "").split("/")[-1], "", f"{j.get('schedule')} → {tgt} · {j.get('state')}"))
        for m in g(p, "redis", "instances", "list", "--region", r):
            res.append(row(p, r, "Memorystore", m.get("name", "").split("/")[-1], "", f"{m.get('tier')} · {m.get('memorySizeGb')} GB"))
    for d in g(p, "firestore", "databases", "list"):
        res.append(row(p, d.get("locationId"), "Firestore", d.get("name", "").split("/")[-1], "", d.get("type", "")))
    for z in g(p, "dns", "managed-zones", "list"):
        for rr in g(p, "dns", "record-sets", "list", "--zone", z.get("name")):
            if rr.get("type") in ("CNAME", "A", "AAAA", "ALIAS"):
                for t in rr.get("rrdatas", []):
                    dns.append({"zone": z.get("dnsName"), "name": rr.get("name"), "type": rr.get("type"), "target": t})
write("gcp", res, dns)
