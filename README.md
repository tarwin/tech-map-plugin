# tech-map

A [Claude Code](https://claude.com/claude-code) skill that builds an interactive map of a company's systems from its cloud accounts and code repos.

You get one self-contained HTML page with three tabs:

- **Maps**: swim-lane diagrams of what calls what. Users and apps on the left, then front doors, queues, workers, data stores and external services. Click any box for details and connections, or step through key flows.
- **Findings**: problems found while mapping, each linked to its box on the map. Examples: databases open to the internet, DNS records anyone could take over, credentials committed to git, unauthenticated callbacks, error storms, end-of-life runtimes, and unused resources still costing money.
- **Inventory**: the raw cloud listing with 7- or 30-day activity counts.

Useful for onboarding, cleanup and migration planning, or a security once-over of a system nobody has fully mapped.

## Install

```
/plugin marketplace add tarwin/tech-map-plugin
/plugin install tech-map@tarwin
```

Then ask Claude something like *"make a tech map of our systems"* or *"what's running in our AWS account and how does it fit together?"*.

## What it asks you

1. **Where your code repos are**: the folder holding them side by side (it suggests `..`).
2. **Which providers to include**: it scans the repos for deploy configs and suggests the ones it finds.
3. **Which identity to use for each provider**: an AWS profile, gcloud configuration and projects, Azure subscriptions, or the *name* of the environment variable holding a read-only API token.

Before collecting anything, it shows you the account it's about to read, so it never maps the wrong company. This matters if your shell has another company's `AWS_PROFILE` set.

## Providers

| Provider | Needs | Collects |
|---|---|---|
| AWS | AWS CLI v2, a named profile | Lambda, Elastic Beanstalk, ECS, SQS, SNS, EventBridge, API Gateway, RDS, DynamoDB, ElastiCache, CloudFront, S3, plus CloudWatch request, invocation and error counts |
| Google Cloud | `gcloud` | Cloud Run, Functions, App Engine, GKE, Compute, Cloud SQL, GCS, Pub/Sub, Scheduler, Memorystore, Firestore, Cloud DNS, plus Monitoring request counts |
| Azure | `az` | App Service and Functions, Container Apps, SQL, PostgreSQL, MySQL, Storage, Service Bus, DNS, and every other resource in the subscription |
| Cloudflare | read-only API token in env | Zones, DNS, Workers and routes, Pages, R2, D1, KV, Queues, plus request counts |
| Vercel | API token in env | Projects, domains, DNS |
| Netlify | API token in env | Sites, DNS |

The code survey also maps the third-party services your code talks to, such as payments, auth, email, CRM and AI APIs.

`skills/tech-map/references/providers.md` explains how to add another provider.

## Safety

- **Read-only.** It lists and describes resources and never changes them.
- **No secrets stored.** Collectors never write environment variables, app settings, connection strings or keys. Tokens are read from environment variables and never saved. Secrets found in code are reported by location only, never by value.
- **Treat the output as internal.** The generated page lists your security findings, so don't publish it anywhere public.

## Requirements

Python 3.11+ and Node 18+, plus `jq` for AWS. You also need each provider's CLI or token, as listed above.

## License

[MIT](LICENSE)
