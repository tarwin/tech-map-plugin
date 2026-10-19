# Surveying the code repos

The cloud inventory says *what exists*. The code says *who calls what*. Read code with parallel read-only agents (`Explore` type), grouped so each agent has a coherent slice. Give each agent the cloud facts you already have (resource names, hosts, buckets, queues), so it can map code to real resources instead of guessing.

## Before splitting the work

1. List repos with last-commit dates:
   ```sh
   for d in <reposDir>/*/; do printf '%-45s' "$d"; git -C "$d" log -1 --format='%cs %s' 2>/dev/null | cut -c1-60 || echo "(no git)"; done
   ```
2. **Find the live copy of each service before reading it.** Companies often have a monorepo (`*-mono`, `apps/*`, `packages/*`) plus older standalone repos with the same names. The deploy script decides which is live: match `eb deploy <env>`, `aws lambda update-function-code --function-name`, `s3 sync s3://<bucket>`, `serverless`, `sam`, `cdk`, `gcloud run deploy`, `az webapp deploy`, `wrangler deploy`, `vercel`/`netlify` project links or CI workflow targets against what exists in the cloud. Read the copy whose deploy target exists and whose last commit is recent, and mark the other as superseded. (Getting this wrong maps code that no longer runs.)
3. Split into about 3–5 agents, for example:
   - **The main API(s)**, one agent each if large.
   - **Functions and workers**: every `lambda-*`, `worker-*`, `*-service` repo.
   - **Front-ends, apps and sites**: web apps, mobile apps, marketing and docs sites.
   - **Infra and IaC** if present: terraform, cdk, pulumi, serverless.yml.

## Prompt for the API agent

> Read-only research for an architecture map of <Company>. Repo: <path> (deployed to <env/host> per the cloud inventory). Thoroughness: very thorough. Report in bullets with file paths, under ~1200 words:
> 1. Stack: framework, language, DB access and which DB/secret, auth model (which routes are public, which need what), how it's deployed (scripts, target env names; flag if they don't match `<live env names>`).
> 2. Route groups, one line each.
> 3. Every outbound integration: functions invoked (name, sync/async, region), queues/topics/state machines sent to, buckets read or written, email, and third-party APIs. Give the env var or secret *name* or code location for each.
> 4. Inbound: webhooks, callbacks from functions, scheduled endpoints, partner calls, and how each is authenticated.
> 5. Background work inside the process (pollers, intervals, crons) and realtime (websockets, Ably, Pusher).
> 6. Risks: hard-coded secrets (location only, **never the value**), unauthenticated mutating endpoints, prod pointing at dev/test hosts, test routes in prod, dead code and TODOs about migrations.
> Do not modify files.

## Prompt for the functions agent

> Read-only. Repos: <list>. Deployed functions: <name, provider, region, runtime, trigger from the inventory>. For each repo: which deployed function(s) it maps to and how you know (deploy script); trigger; inputs; outputs (buckets/prefixes, callbacks and their URLs, DB writes, third-party calls); runtime and layers. Flag deployed functions with no repo, repos with no deployed function, test/leftover functions, hard-coded secrets (location only), and EOL runtimes. Under ~1200 words. Do not modify files.

## Prompt for the front-end agent

> Read-only. Repos: <list>. Known hosting: <CloudFront / Pages / Vercel / Netlify / App Service hostnames → origins>. For each repo, 2–5 bullets: what it is, framework, where it deploys (scripts/CI/.env names), which APIs and third-party services it calls (env var names, never values), last-activity date, and live / legacy / prototype. Note brand or white-label relationships and how mobile apps upload files (presigned URLs vs embedded keys). Flag committed secrets (location only). Under ~1500 words. Do not modify files.

## After the agents report

- **Re-check claims that drive findings** yourself with a targeted grep, especially secrets, unauthenticated routes and prod→dev URLs. Agents sometimes read the stale copy of a repo.
- Anything you couldn't confirm goes in the model with `inferred: true` and in a "Not confirmed" finding.
