"""Combine the sanitized dumps in data/aws/ into data/inv.json (Inventory tab, header stats, page metadata).

Lambda triggers come from AWS where AWS records them (event-source mappings, Scheduler, EventBridge rules,
SNS subscriptions, S3 notifications, resource policies). Direct invokes from application code aren't
recorded anywhere in AWS: list them by hand in data/direct-triggers.json as {"function-name": "who calls it"}."""
import datetime, json, os

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
full = json.load(open(os.path.join(root, "tech-map.config.json")))
cfg = full.get("providers", {}).get("aws") or {"regions": []}
base = os.path.join(root, "data", "aws")
last = lambda arn: (arn or "").split(":")[-1].split("/")[-1]

def load(*p):
    f = os.path.join(base, *p)
    return json.load(open(f)) if os.path.exists(f) else {}

met = {}
if os.path.exists(f"{base}/metrics.tsv"):
    for line in open(f"{base}/metrics.tsv"):
        kind, r, name, m, v = line.rstrip("\n").split("\t")
        met[(kind, r, name, m)] = int(v)

inv = {k: [] for k in ("eb", "ecs", "lambdas", "queues", "topics", "rules", "apis", "rds", "dynamo", "caches", "sites", "s3")}
trig = {}
add = lambda r, fn, t: trig.setdefault((r, fn), []).append(t)
buckets = load("s3.json").get("Buckets", [])
for b in buckets:
    for n in b.get("notifications", []):
        if n["type"] == "lambda":
            add(n["target"].split(":")[3], last(n["target"]), f"S3 {b['name']}/{n['prefix'] or '*'}")

for r in cfg["regions"]:
    for e in load(r, "eb.json").get("Environments", []):
        cfgs = {o["OptionName"]: o.get("Value") for o in load(r, f"ebcfg-{e['EnvironmentName']}.json").get("ConfigurationSettings", [{}])[0].get("OptionSettings", [])}
        stack, n = e["SolutionStackName"], e["EnvironmentName"]
        inv["eb"].append({"region": r, "app": e["ApplicationName"], "env": n, "tier": e["Tier"]["Name"], "health": e.get("Health"),
                          "platform": stack.split(" running ")[-1] if " running " in stack else stack,
                          "size": f"{cfgs.get('MinSize', '?')}–{cfgs.get('MaxSize', '?')} × {cfgs.get('InstanceType', '?')}",
                          "build": e.get("VersionLabel", ""), "cname": e.get("CNAME", ""), "queue": (cfgs.get("WorkerQueueURL") or "").split("/")[-1],
                          "req": met.get(("eb", r, n, "RequestCount")), "err": met.get(("eb", r, n, "HTTPCode_Target_5XX_Count"))})
    inv["ecs"] += [{"region": r, **s} for s in load(r, "ecs.json").get("Services", [])]
    for m in load(r, "esm.json").get("EventSourceMappings", []):
        kind = m["EventSourceArn"].split(":")[2].upper()
        add(r, last(m["FunctionArn"]), f"{kind} {last(m['EventSourceArn'])}" + ("" if m["State"] == "Enabled" else " (disabled)"))
    for s in load(r, "schedules.json").get("Schedules", []):
        inv["rules"].append({"region": r, "name": s["Name"], "kind": "Scheduler", "expr": "", "state": s["State"], "targets": last(s["Target"])})
        if ":function:" in s["Target"]:
            add(r, last(s["Target"]), f"Scheduler {s['Name']}")
    for x in load(r, "rules.json").get("Rules", []):
        inv["rules"].append({"region": r, "name": x["Name"], "kind": "EventBridge rule", "expr": x.get("ScheduleExpression") or (x.get("EventPattern") or "")[:120],
                             "state": x["State"], "targets": ", ".join(last(t) for t in x.get("Targets", []))})
        for t in x.get("Targets", []):
            if ":function:" in t:
                add(r, last(t), f"EventBridge {x['Name']}" + (f" {x['ScheduleExpression']}" if x.get("ScheduleExpression") else ""))
    subs = load(r, "sns-subs.json").get("Subscriptions", [])
    for t in load(r, "sns.json").get("Topics", []):
        mine = [s for s in subs if s["TopicArn"] == t]
        inv["topics"].append({"region": r, "name": last(t), "subs": ", ".join(f"{s['Protocol']}:{last(s['Endpoint'])}" if s["Endpoint"] else s["Protocol"] for s in mine),
                              "vol": met.get(("sns", r, last(t), "NumberOfMessagesPublished"))})
        for s in mine:
            if s["Protocol"] == "lambda":
                add(r, last(s["Endpoint"]), f"SNS {last(t)}")
    for p in load(r, "lambda-policies.json").get("Policies", []):
        for a in p["allow"]:
            pr = a["principal"] if isinstance(a["principal"], str) else str(a["principal"])
            if "apigateway" in pr: add(r, p["fn"], "API GW " + (a["source"].split(":")[-1].split("/")[0] if a["source"] else ""))
    for x in load(r, "apigw.json").get("Apis", []):
        inv["apis"].append({"region": r, **x})
    for d in load(r, "rds.json").get("DBInstances", []):
        inv["rds"].append({"region": r, "id": d["DBInstanceIdentifier"], "engine": f"{d['Engine']} {d.get('EngineVersion', '')}", "class": d["DBInstanceClass"],
                           "public": "yes" if d.get("PubliclyAccessible") else "no", "multiaz": "yes" if d.get("MultiAZ") else "no"})
    inv["dynamo"] += [{"region": r, "name": t} for t in load(r, "dynamo.json").get("TableNames", [])]
    inv["caches"] += [{"region": r, "id": c["CacheClusterId"], "engine": c["Engine"], "node": c["CacheNodeType"], "nodes": c.get("NumCacheNodes")}
                      for c in load(r, "elasticache.json").get("CacheClusters", [])]
    for u in load(r, "sqs.json").get("QueueUrls", []):
        q = u.split("/")[-1]
        inv["queues"].append({"region": r, "name": q, "vol": met.get(("sqs", r, q, "NumberOfMessagesSent"), 0)})

direct = {}
if os.path.exists(os.path.join(root, "data", "direct-triggers.json")):
    direct = json.load(open(os.path.join(root, "data", "direct-triggers.json")))
for r in cfg["regions"]:
    for fn in load(r, "lambdas.json").get("Functions", []):
        n = fn["FunctionName"]
        t = list(dict.fromkeys(trig.get((r, n), [])))
        if n in direct: t.append(direct[n])
        inv["lambdas"].append({"region": r, "name": n, "runtime": fn.get("Runtime") or "container", "modified": (fn.get("LastModified") or "")[:10],
                               "mem": fn.get("MemorySize"), "trigger": ", ".join(t) or "none found",
                               "inv": met.get(("lambda", r, n, "Invocations"), 0), "err": met.get(("lambda", r, n, "Errors"), 0)})

for d in load("cloudfront.json").get("Distributions", []):
    inv["sites"].append({"alias": ", ".join(d["Aliases"]) or d["DomainName"], "origin": ", ".join(d["Origins"]), "id": d["Id"],
                         "comment": d.get("Comment") or "", "req": met.get(("cloudfront", "global", d["Id"], "Requests"), 0)})
for b in buckets:
    inv["s3"].append({"name": b["name"], "region": b["region"],
                      "trigger": ", ".join(f"{n['type']} {last(n['target'])} on {n['prefix'] or '*'}" for n in b.get("notifications", [])),
                      "site": ", ".join(s["alias"] for s in inv["sites"] if any(o.split(".s3")[0] == b["name"] for o in s["origin"].split(", ")))})

inv["eb"].sort(key=lambda x: (x["region"], x["env"].lower()))
inv["lambdas"].sort(key=lambda x: (-x["inv"], x["name"].lower()))
inv["queues"].sort(key=lambda x: (-x["vol"], x["name"]))
inv["sites"].sort(key=lambda x: -x["req"])
inv["s3"].sort(key=lambda x: x["name"])
# Other providers: their collectors already wrote normalized rows (see scripts/providers/common.py).
inv["other"] = {}
for p in full.get("providers", {}):
    f = os.path.join(root, "data", p, "resources.json")
    if p != "aws" and os.path.exists(f):
        inv["other"][p] = json.load(open(f))["resources"]

PROVIDER_LABEL = {"aws": "AWS", "gcp": "Google Cloud", "azure": "Azure", "cloudflare": "Cloudflare", "vercel": "Vercel", "netlify": "Netlify"}
def scope_of(p, c):
    return {"aws": lambda: f"account {c.get('account')}" + (f" ({c['alias']})" if c.get("alias") else ""),
            "gcp": lambda: "project " + ", ".join(c.get("projects", [])), "azure": lambda: "subscription " + ", ".join(c.get("subscriptions", [])),
            "vercel": lambda: "team " + ", ".join(t for t in c.get("teams") or ["personal"])}.get(p, lambda: "account")()
inv["meta"] = {"company": full["company"], "providers": [{"id": p, "label": PROVIDER_LABEL.get(p, p), "scope": scope_of(p, c)} for p, c in full.get("providers", {}).items()],
               "account": cfg.get("account"), "alias": cfg.get("alias"), "regions": cfg.get("regions", []),
               "windowDays": int(full.get("windowDays", 7)), "reposLabel": full.get("reposLabel") or full.get("reposDir", "../"),
               "collected": datetime.date.today().strftime("%-d %b %Y")}

dest = os.path.join(root, "data", "inv.json")
json.dump(inv, open(dest, "w"), separators=(",", ":"))
print(", ".join([f"{len(v)} {k}" for k, v in inv.items() if isinstance(v, list) and v] + [f"{len(v)} {k} resources" for k, v in inv["other"].items()]), "->", os.path.relpath(dest))
