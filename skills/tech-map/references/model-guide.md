# Writing the model (src/model.js) and findings (src/findings.js)

## Shape

Start from `assets/model.template.js`. It defines `COLUMNS`, `MAPS`, `DOMAINS`, `KINDS`, `NODES`, `EDGES` and `FLOWS`.

- **Node**: `{ id, col, d, kind, label, provider, host, region, repo, vol, volUnit, desc, notes, status, statusLabel, inferred }`
  - `col` indexes `COLUMNS`. The default columns follow a request: users & apps → front doors → topics & queues → workers → data stores → external. Rename them if the company's shape differs, but keep left-to-right = upstream-to-downstream.
  - `d` is the domain. The domain picks the map. A node lives on exactly one map; elsewhere it appears as a faded ghost when an edge crosses.
  - `kind` must be a key of `KINDS`. Colour comes from `KIND_FAMILY` in explorer.html (caller, web, topic, queue, fn, data, ext). Add a kind to both if you need a new one.
  - `provider` ("AWS", "Google Cloud", "Cloudflare"…) shows in the details panel. Set it when more than one provider is mapped.
  - `vol` + `volUnit` (`req` | `msg` | `inv`) come from `data/aws/metrics.tsv` or the `vol` column of other providers' rows in `data/<provider>/resources.json`. Leave `vol` off when there's no metric. A missing value is better than a guessed one.
  - `status`: `legacy` (being retired or unused), `migrating`, or `orphan` (a problem such as no consumer, dangling DNS or a broken trigger). `statusLabel` overrides the pill text, for example `"dangling"` or `"no consumer"`.
  - `inferred: true` when neither code nor the cloud inventory confirms it. Drawn dotted.
  - `label` gets cut at ~30 characters on the box, so put the long name in `desc`.
  - `notes` are short factual bullets: numbers, risks, quirks, each traceable to a file or a cloud API call.
- **Edge**: `[from, to, type, label, { inferred }]`. Types: `http`, `sqs` (any queue: SQS, Pub/Sub pull, Service Bus, CF Queues), `sns` (topic or event publish: SNS, EventBridge, Pub/Sub, Event Grid), `invoke` (function or state-machine start), `s3` (storage event trigger: S3, GCS, Blob), `data` (reads/writes a store), `sched`. Point edges the way the request travels, so a callback is a separate edge back.
- **Flow**: `{ id, title, d, summary, steps }`. Every step `[from, to, text]` must match an existing edge (the validator checks). A flow appears on its domain's map. Aim for 5–10 flows covering what someone onboarding asks first, such as "what happens when a user signs up / uploads / pays".

## Choosing maps and domains

- Choose 3–6 maps, each a page someone would open on its own: the core product, each distinct product line, media/data pipelines, marketing sites, and a **Leftovers** map for unused or test resources (it makes cleanup planning easy).
- Choose 2–5 domains per map. Domains are horizontal bands, so group by business purpose, not by cloud service.
- External services that only one domain uses go in that domain. Shared ones (email, CRM, geocoding) go in a "Third-party services" domain.
- A map with 40+ boxes is hard to read. Split it.

## Volumes

For AWS, read `data/aws/metrics.tsv` (kind, region, name, metric, value). Use `RequestCount` for EB web envs, `Requests` for CloudFront, `NumberOfMessagesSent` for SQS, `NumberOfMessagesPublished` for SNS, and `Invocations` for Lambdas. Sum across regions for multi-region components and say so in a note. Record Lambda error counts in notes when they're notable (over ~5% of runs). Other providers put their activity count in the `vol` column of `data/<provider>/resources.json`.

## Findings (src/findings.js)

`src/findings.js` holds one array literal assigned to `FINDINGS`:

```js
const FINDINGS = [
  { sev: "high", title: "One-line statement of the problem",
    body: "What and where, with evidence. HTML allowed (use <code>).",
    list: ["optional bullets"], cols: [["Heading", ["bullets"]]],   // optional
    fix: "What to do about it.", node: "node-id-to-jump-to" },
];
```

- `sev` is `high`, `medium`, `info` or `decided`. **High** means exploitable now or data at risk: public DB ports, claimable DNS, live credentials in shipped code. **Medium** means it will hurt or is risky but not open: weak callback auth, prod pointing at dev, error storms, EOL runtimes. **Info** covers context and cleanup.
- Order: high first, then medium, then info.
- Every finding should say how it was checked (cloud API call, file:line, log query) and what to do.
- **Never write a secret's value** into findings, notes or chat. Give the file path, line and kind of secret only. If a value scrolls past in tool output, don't repeat it.
