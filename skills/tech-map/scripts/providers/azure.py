"""Azure inventory via the az CLI (read-only). Config: providers.azure = {subscriptions: ["<id or name>", ...]}.

Collects every resource (az resource list) plus detail for App Service / Function apps (with 30-day request
counts), Container Apps, SQL / PostgreSQL / MySQL servers (with firewall rules), storage accounts (public
blob access, static websites), Service Bus, Front Door/CDN endpoints and Azure DNS records.
App settings, connection strings and keys are never requested."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir; common.py lives here
from common import config, window, run_json, row, write, host_of

cfg = config()["providers"]["azure"]
days, start, end = window()

def az(sub, *args):
    return run_json(["az", *args, "--subscription", sub, "--output", "json", "--only-show-errors"]) or []

def total(sub, rid, metric):
    d = run_json(["az", "monitor", "metrics", "list", "--resource", rid, "--metrics", metric, "--subscription", sub,
                  "--start-time", start.isoformat(), "--end-time", end.isoformat(), "--interval", "P1D",
                  "--aggregation", "Total", "--output", "json", "--only-show-errors"]) or {}
    return int(sum(p.get("total") or 0 for v in d.get("value", []) for ts in v.get("timeseries", []) for p in ts.get("data", []))) or None

DETAILED = {"microsoft.web/sites", "microsoft.app/containerapps", "microsoft.sql/servers", "microsoft.dbforpostgresql/flexibleservers",
            "microsoft.dbformysql/flexibleservers", "microsoft.storage/storageaccounts", "microsoft.servicebus/namespaces", "microsoft.network/dnszones"}
res, dns = [], []
for sub in cfg["subscriptions"]:
    print("== azure", sub)
    for s in az(sub, "webapp", "list"):
        kind = "Function app" if "functionapp" in (s.get("kind") or "") else "App Service"
        vol = total(sub, s["id"], "FunctionExecutionCount" if kind == "Function app" else "Requests")
        res.append(row(sub, s.get("location"), kind, s.get("name"), ",".join(s.get("hostNames") or [s.get("defaultHostName", "")]),
                       f"{s.get('resourceGroup')} · {s.get('state')} · {(s.get('siteConfig') or {}).get('linuxFxVersion') or s.get('kind')}", vol,
                       ["HTTPS not enforced"] if not s.get("httpsOnly") else []))
    for c in az(sub, "containerapp", "list"):
        ing = (c.get("properties", {}).get("configuration") or {}).get("ingress") or {}
        res.append(row(sub, c.get("location"), "Container App", c.get("name"), ing.get("fqdn", ""), c.get("resourceGroup"),
                       flags=["external ingress"] if ing.get("external") else []))
    for kind, cmd in (("Azure SQL server", ["sql", "server"]), ("PostgreSQL flexible", ["postgres", "flexible-server"]), ("MySQL flexible", ["mysql", "flexible-server"])):
        for srv in az(sub, *cmd, "list"):
            fw_args = ["--server", srv["name"]] if cmd[0] == "sql" else ["--name", srv["name"]]
            rules = az(sub, *cmd, "firewall-rule", "list", "--resource-group", srv["resourceGroup"], *fw_args)
            flags = []
            for r in rules:
                a, b = r.get("startIpAddress"), r.get("endIpAddress")
                if a == "0.0.0.0" and b == "255.255.255.255": flags.append(f"firewall {r.get('name')}: whole internet")
                elif a == b == "0.0.0.0": flags.append("allows all Azure services (any tenant)")
            if (srv.get("publicNetworkAccess") or srv.get("network", {}).get("publicNetworkAccess")) == "Enabled": flags.append("public network access")
            res.append(row(sub, srv.get("location"), kind, srv["name"], srv.get("fullyQualifiedDomainName", ""), srv.get("resourceGroup"), flags=flags))
    for st in az(sub, "storage", "account", "list"):
        web = host_of((st.get("primaryEndpoints") or {}).get("web"))
        res.append(row(sub, st.get("location"), "Storage account", st["name"], ",".join(h for h in [host_of((st.get("primaryEndpoints") or {}).get("blob")), web] if h),
                       f"{st.get('kind')} · {st.get('sku', {}).get('name')}", flags=["blob public access allowed"] if st.get("allowBlobPublicAccess") else []))
    for ns in az(sub, "servicebus", "namespace", "list"):
        qs = az(sub, "servicebus", "queue", "list", "--resource-group", ns["resourceGroup"], "--namespace-name", ns["name"])
        ts = az(sub, "servicebus", "topic", "list", "--resource-group", ns["resourceGroup"], "--namespace-name", ns["name"])
        for q in qs:
            res.append(row(sub, ns.get("location"), "Service Bus queue", f"{ns['name']}/{q['name']}", "", f"{q.get('messageCount', 0)} waiting · {q.get('deadLetterMessageCount') or (q.get('countDetails') or {}).get('deadLetterMessageCount', 0)} dead-lettered"))
        for t in ts:
            res.append(row(sub, ns.get("location"), "Service Bus topic", f"{ns['name']}/{t['name']}", "", f"{t.get('subscriptionCount', 0)} subscriptions",
                           flags=[] if t.get("subscriptionCount") else ["no subscriptions"]))
    for z in az(sub, "network", "dns", "zone", "list"):
        for rs in az(sub, "network", "dns", "record-set", "list", "--resource-group", z["resourceGroup"], "--zone-name", z["name"]):
            t = rs.get("type", "").split("/")[-1]
            fq = rs.get("fqdn") or f"{rs.get('name')}.{z['name']}."
            if t == "CNAME" and rs.get("CNAMERecord"):
                dns.append({"zone": z["name"], "name": fq, "type": "CNAME", "target": rs["CNAMERecord"].get("cname")})
            if rs.get("targetResource", {}).get("id"):
                dns.append({"zone": z["name"], "name": fq, "type": "ALIAS", "target": rs["targetResource"]["id"]})
    for r in az(sub, "resource", "list"):
        if (r.get("type") or "").lower() in DETAILED:
            continue
        res.append(row(sub, r.get("location"), r.get("type", "").split("/", 1)[-1], r.get("name"), "", r.get("resourceGroup")))
write("azure", res, dns)
