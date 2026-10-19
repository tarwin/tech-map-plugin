"""CloudWatch sums over the configured window -> data/aws/metrics.tsv (kind, region, name, metric, value).

Lambda Invocations/Errors, SQS NumberOfMessagesSent, SNS NumberOfMessagesPublished,
ALB RequestCount/5XX per EB web env, CloudFront Requests. Settings from tech-map.config.json."""
import datetime, glob, json, os, subprocess

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
full = json.load(open(os.path.join(root, "tech-map.config.json")))
cfg = full["providers"]["aws"]
base = os.path.join(root, "data", "aws")
env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
env["AWS_PROFILE"] = cfg["profile"]
days = int(full.get("windowDays", 7))
end = datetime.datetime.now(datetime.UTC)
start = end - datetime.timedelta(days=days)
PERIOD = days * 86400

def aws(*a):
    res = subprocess.run(["aws", *a, "--output", "json"], capture_output=True, text=True, env=env)
    return json.loads(res.stdout or "{}")

def sums(region, specs):
    """specs: [(label, namespace, metric, dimensions)] -> {label: sum}"""
    out = {}
    for i in range(0, len(specs), 400):  # get-metric-data takes up to 500 queries
        chunk = specs[i:i + 400]
        q = [{"Id": f"m{j}", "Label": lbl, "MetricStat": {"Metric": {"Namespace": ns, "MetricName": m, "Dimensions": dims},
              "Period": PERIOD, "Stat": "Sum"}} for j, (lbl, ns, m, dims) in enumerate(chunk)]
        d = aws("cloudwatch", "get-metric-data", "--region", region, "--metric-data-queries", json.dumps(q),
                "--start-time", start.isoformat(), "--end-time", end.isoformat())
        for r in d.get("MetricDataResults", []):
            out[r["Label"]] = int(sum(r["Values"]))
    return out

rows = []
for r in cfg["regions"]:
    d = f"{base}/{r}"
    load = lambda f: json.load(open(f"{d}/{f}")) if os.path.exists(f"{d}/{f}") else {}
    fns = [x["FunctionName"] for x in load("lambdas.json").get("Functions", [])]
    for k, v in sums(r, [(f"{fn}|{m}", "AWS/Lambda", m, [{"Name": "FunctionName", "Value": fn}]) for fn in fns for m in ("Invocations", "Errors")]).items():
        fn, m = k.split("|"); rows.append(("lambda", r, fn, m, v))
    qs = [u.split("/")[-1] for u in load("sqs.json").get("QueueUrls", [])]
    for k, v in sums(r, [(q, "AWS/SQS", "NumberOfMessagesSent", [{"Name": "QueueName", "Value": q}]) for q in qs]).items():
        rows.append(("sqs", r, k, "NumberOfMessagesSent", v))
    ts = [t.split(":")[-1] for t in load("sns.json").get("Topics", [])]
    for k, v in sums(r, [(t, "AWS/SNS", "NumberOfMessagesPublished", [{"Name": "TopicName", "Value": t}]) for t in ts]).items():
        rows.append(("sns", r, k, "NumberOfMessagesPublished", v))
    for e in load("eb.json").get("Environments", []):
        if e["Tier"]["Name"] != "WebServer":
            continue
        lbs = aws("elasticbeanstalk", "describe-environment-resources", "--region", r, "--environment-name", e["EnvironmentName"]) \
            .get("EnvironmentResources", {}).get("LoadBalancers", [])
        if not lbs or ":loadbalancer/app/" not in lbs[0]["Name"]:
            continue
        dim = [{"Name": "LoadBalancer", "Value": lbs[0]["Name"].split(":loadbalancer/")[-1]}]
        for k, v in sums(r, [(m, "AWS/ApplicationELB", m, dim) for m in ("RequestCount", "HTTPCode_Target_5XX_Count")]).items():
            rows.append(("eb", r, e["EnvironmentName"], k, v))

cf = json.load(open(f"{base}/cloudfront.json")).get("Distributions", []) if os.path.exists(f"{base}/cloudfront.json") else []
specs = [(x["Id"], "AWS/CloudFront", "Requests", [{"Name": "DistributionId", "Value": x["Id"]}, {"Name": "Region", "Value": "Global"}]) for x in cf]
for k, v in sums("us-east-1", specs).items():
    rows.append(("cloudfront", "global", k, "Requests", v))

with open(f"{base}/metrics.tsv", "w") as out:
    for row in rows:
        out.write("\t".join(map(str, row)) + "\n")
print(f"{len(rows)} metric rows over {days} days -> data/aws/metrics.tsv")
