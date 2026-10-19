# Providers: setup, config and what gets collected

All collectors are read-only. They never write env vars, app settings, connection strings, keys or tokens. Each provider's settings live under `providers.<id>` in `tech-map.config.json`. API tokens are referenced by **environment-variable name** only. They never go in the config, the data files or chat.

| id | Auth | Config block | Collected |
|---|---|---|---|
| `aws` | named AWS CLI profile | `{profile, account, alias, regions: []}` | Lambda (+ triggers, resource policies), EB (+ sizing, worker queues), ECS services, SQS, SNS (+ subscriptions), EventBridge rules + Scheduler, API Gateway, RDS (public flag, SGs), DynamoDB, ElastiCache, CloudFront, S3 (+ event notifications). Metrics: Lambda runs/errors, SQS sent, SNS published, ALB requests/5XX, CloudFront requests |
| `gcp` | `gcloud` login; pin a named configuration | `{configuration, projects: [], regions: []}` | Cloud Run, Cloud Functions, App Engine, GKE, Compute, Cloud SQL (+ authorized networks), GCS (+ public IAM), Pub/Sub (+ push endpoints), Cloud Scheduler, Memorystore, Firestore, Cloud DNS. Metrics: Cloud Run requests, function executions (Monitoring API) |
| `azure` | `az login` | `{subscriptions: []}` | App Service / Function apps (+ requests/executions), Container Apps, Azure SQL / PostgreSQL / MySQL (+ firewall rules), storage accounts (public blob access, static sites), Service Bus queues/topics, Azure DNS, plus every other resource from `az resource list` |
| `cloudflare` | API token in env | `{tokenEnv: "CLOUDFLARE_API_TOKEN", accounts?: []}` | Zones (+ requests), DNS records, Workers (+ invocations/errors) and routes, Pages projects, R2, D1, KV, Queues |
| `vercel` | API token in env | `{tokenEnv: "VERCEL_TOKEN", teams?: ["team_…"]}` | Projects (framework, repo, production domains, last prod deploy), domains + DNS records |
| `netlify` | API token in env | `{tokenEnv: "NETLIFY_AUTH_TOKEN"}` | Sites (domains, repo, last publish), DNS zones + records |

## Pinning the identity (why it matters)

People often have several companies' credentials on one machine, and shells often export `AWS_PROFILE`, an active gcloud configuration, or a default Azure subscription for another company. Reading the wrong account produces a convincing map of the wrong company. So:

- **AWS**: collectors drop every `AWS_*` variable and set `AWS_PROFILE` from the config, and `aws.sh` stops if `sts get-caller-identity` doesn't return the configured account.
- **GCP**: set `configuration` (a named gcloud configuration). The collector exports `CLOUDSDK_ACTIVE_CONFIG_NAME` so the shell's active configuration is ignored, and passes `--project` on every call. If the user has only one configuration, it can be omitted.
- **Azure**: every call passes `--subscription`. The default subscription is never used.
- **Token providers**: each token is scoped to one account or team by whoever creates it. Confirm the account name the API returns with the user.

## Getting tokens (tell the user; never ask them to paste a token into chat)

Have them `export VAR=…` in the shell they start Claude Code from, or run collection themselves with `! VAR=… python3 -I scripts/collect.py cloudflare`.

- **Cloudflare**: dash → My Profile → API Tokens → Create Token → custom, read-only: Account Settings, Zone, DNS, Workers Scripts, Workers Routes, Cloudflare Pages, Workers R2 Storage, D1, Workers KV Storage, Queues, Account Analytics, Zone Analytics (all *Read*).
- **Vercel**: Account Settings → Tokens, scoped to the team. (Vercel tokens can't be made read-only. Say so.)
- **Netlify**: User settings → Applications → Personal access tokens. (Also not scope-limited.)
- **GCP**: `gcloud auth login` plus Viewer (or Security Reviewer + Monitoring Viewer) on each project. Enable the Monitoring API for request counts.
- **Azure**: `az login`, Reader on each subscription. Install the `containerapp` extension for Container Apps (optional).

## Adding another provider (Fly, Render, Heroku, DigitalOcean, Supabase, Firebase Hosting…)

1. Write `scripts/providers/<id>.py`, starting with the path line and `from common import …` like the others.
2. Use `row(scope, region, type, name, host, detail, vol, flags)` for each resource and `write("<id>", rows, dns_records)` at the end. Put every public hostname a resource serves in `host`, so `dns-check.py` treats it as live.
3. Add it to `RUNNERS` in `scripts/collect.py`, a label in `PROVIDER_LABEL` in `scripts/inv.py`, its hostname suffix to `PRONE` in `scripts/dns-check.py`, and kinds to `KIND_FAMILY` (explorer.html) and `KINDS` (model.js).
4. Pick fields explicitly. Never dump whole objects, because that's how env vars and secrets leak into data files.

If no API is available, you can still draw the provider: add nodes by hand with `provider` set, mark them `inferred` where needed, and say in a finding that it wasn't inventoried.

## Not collectors, but worth mapping from code

SaaS the code talks to (Stripe, Auth0/Clerk, Supabase, Firebase Auth, HubSpot, SendGrid/Postmark, Twilio, OpenAI/Anthropic, PostHog/Segment, Sentry) goes in as `ext` nodes from the code survey. Group minor ones into a single node per purpose, such as "Email (SES + Postmark)".
