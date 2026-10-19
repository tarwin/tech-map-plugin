// __COMPANY__ system map: hand-curated model.
// Sources: __PROVIDERS__ (collected __DATE__) + code in __REPOS__.
// vol = __WINDOW__-day volume; volUnit: "req" (HTTP requests), "msg" (queue/topic messages), "inv" (function invocations).
// Edge types: http, sqs (queue), sns (topic/event), invoke, s3 (storage event trigger), data, sched.
// "inferred: true" = not confirmed in code or the cloud inventory.

const COLUMNS = ["Users & apps", "Front doors", "Topics & queues", "Workers", "Data stores", "External"];

// Each map is its own page. Nodes belong to a map through their domain; neighbours from other maps
// show as faded "ghost" boxes that link across. The first map is the default.
const MAPS = {
  core: { label: "Core platform", desc: "The main API and what it talks to." },
};

const DOMAINS = {
  api: { label: "API & data", map: "core" },
};

// kind → short badge. The colour comes from KIND_FAMILY in explorer.html (unknown kinds render as "web").
const KINDS = {
  caller: "caller", app: "mobile app", site: "S3 + CloudFront", ebweb: "EB web", ebworker: "EB worker", ecs: "ECS service", apigw: "API GW",
  lambda: "Lambda", clambda: "Lambda (container)", sqs: "SQS", sns: "SNS", eventbus: "EventBridge", sfn: "Step Functions", sched: "schedule",
  rds: "RDS", aurora: "Aurora", redis: "Redis/Valkey", dynamo: "DynamoDB", s3: "S3", secrets: "Secrets", ecr: "ECR",
  // Google Cloud
  run: "Cloud Run", gcf: "Cloud Function", gae: "App Engine", gke: "GKE", gce: "Compute Engine", cloudsql: "Cloud SQL", gcs: "GCS",
  firestore: "Firestore", memorystore: "Memorystore", pubsub: "Pub/Sub", gsched: "Cloud Scheduler", ctasks: "Cloud Tasks",
  // Azure
  appsvc: "App Service", azfunc: "Azure Function", aca: "Container App", azsql: "Azure SQL", azstorage: "Azure Storage", cosmos: "Cosmos DB",
  servicebus: "Service Bus", eventgrid: "Event Grid", frontdoor: "Front Door",
  // Cloudflare, Vercel, Netlify
  cfzone: "Cloudflare zone", worker: "Worker", pages: "CF Pages", r2: "R2", d1: "D1", kv: "Workers KV", cfqueue: "CF Queue",
  vercel: "Vercel", vercelfn: "Vercel function", netlify: "Netlify", netlifyfn: "Netlify function",
  gcp: "Google Cloud", aws: "AWS service", ext: "external",
};

const NODES = [
  // { id, col, d, kind, label, provider, host, region, repo, vol, volUnit, desc, notes: [], status: "legacy"|"migrating"|"orphan", statusLabel, inferred }
  // provider: "AWS" | "Google Cloud" | "Azure" | "Cloudflare" | "Vercel" | "Netlify" | … (shown in the details panel; set it when more than one is mapped)
  { id: "api", col: 1, d: "api", kind: "ebweb", label: "api", host: "api.example.com", region: "us-east-1 · 2–4 × t3.medium",
    repo: "api", vol: 0, volUnit: "req", desc: "What it is, in one or two sentences.", notes: ["Facts worth knowing, each with where it was confirmed."] },
];

const EDGES = [
  // [from, to, type, label, { inferred: true }?]
];

const FLOWS = [
  // { id, title, d, summary, steps: [[from, to, "what happens"], ...] }  (each step must match an edge)
];
