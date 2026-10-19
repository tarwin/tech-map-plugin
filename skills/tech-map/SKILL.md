---
name: tech-map
description: Build an interactive, single-file system map of a company's infrastructure and code, showing which services call which, queues and triggers, data stores, external APIs and request volumes, plus a findings report (security risks, dangling DNS, public databases, secrets in source, leftovers) and a raw inventory. Collects read-only from AWS, Google Cloud, Azure, Cloudflare, Vercel and Netlify and reads the local code repos. Use whenever the user asks for a tech map, system map, architecture map or diagram, infrastructure inventory, "what's running in our AWS/GCP/Azure account", onboarding overview of a codebase plus cloud, cleanup or migration planning across services, or wants to "make one of these for <company>" — even if they don't say "map".
---

# Tech map

Produces a project folder (by default the current directory) containing `<company>-system-map.html`. It's one self-contained page with three tabs:

- **Maps**: swim-lane diagrams. Columns run upstream → downstream, bands are business domains. Click a box to see its details and connections. Flows step through key paths.
- **Findings**: risks and problems, each linked to the component on the map.
- **Inventory**: the raw cloud listing with activity counts.

Under it sit the hand-written model (`src/model.js`, `src/findings.js`) and generated data (`data/`), which are rebuilt by `pnpm build` / `pnpm collect`.

The skill directory has everything to copy in: `assets/` (page template, build script, model skeleton), `scripts/` (collectors, inventory merge, DNS check, validator), and `references/` (read when you reach each step).

The work is about 30% collection and 70% understanding. The collectors list what exists; the value comes from reading code to learn who calls what, and checking the risky bits by hand.

## 1. Ask the user where things are

Ask these with AskUserQuestion, and run the detector first so the options are concrete. Don't make the user type paths and profile names you can find yourself:

```sh
python3 -I <skill>/scripts/detect.py <repos-dir-guess>      # provider hints from repos + local CLIs/profiles/tokens
```

1. **Where are the code repos?** The folder that holds all the company's repos side by side. Offer `..` (the parent of the current directory) when it contains several git repos, plus any other likely folder. Everything under it gets surveyed.
2. **Which providers to include.** Pre-select those with deploy-config evidence from `detect.py` (strong evidence). Mention code-only references as possibilities, and drop anything the user says isn't theirs.
3. **Which identity per provider.** Ask only where there's a real choice:
   - AWS: the profile. List `aws configure list-profiles`, put the profile whose name matches the company first, and ask even if the shell has `AWS_PROFILE` set: that variable is often another company's. Skip the question if there's exactly one profile.
   - GCP: the gcloud configuration and the projects. Azure: the subscriptions.
   - Cloudflare / Vercel / Netlify: the env var holding a read-only token. If it isn't set, tell them how to create one (see `references/providers.md`) and continue with the other providers. Never ask them to paste a token into chat.
4. **Output folder** (default: current directory) and **company name** (default: guess from the folder or account alias).

Then confirm each identity before collecting anything. Run `discover.sh` for AWS (it prints account ID, alias and active regions), and the equivalent for others: `gcloud projects describe`, `az account show --subscription`, the token's `/accounts` or team. Show the user the account names, because a wrong account produces a convincing map of the wrong company.

```sh
bash <skill>/scripts/discover.sh <aws-profile>     # account, alias, regions with resources
```

## 2. Set up the project

```sh
mkdir -p <out>/src <out>/scripts/providers <out>/data
cp <skill>/assets/explorer.html <out>/src/   &&  cp <skill>/assets/build.py <out>/
cp <skill>/assets/model.template.js <out>/src/model.js
cp <skill>/scripts/{collect.py,inv.py,dns-check.py,validate.js} <out>/scripts/
cp <skill>/scripts/providers/{common.py,aws.sh,aws_metrics.py} <out>/scripts/providers/   # plus each other provider's .py you need
echo 'const FINDINGS = [];' > <out>/src/findings.js
```

Write `<out>/tech-map.config.json`. Include only the providers in use:

```json
{
  "company": "Acme",
  "reposDir": "..",
  "reposLabel": "acme/",
  "windowDays": 7,
  "providers": {
    "aws": { "profile": "acme", "account": "123456789012", "alias": "acme-prod", "regions": ["us-east-1", "eu-west-1"] },
    "gcp": { "configuration": "acme", "projects": ["acme-prod"] },
    "cloudflare": { "tokenEnv": "CLOUDFLARE_API_TOKEN" }
  }
}
```

`reposLabel` is just the folder name shown in the page header. Use `windowDays` 7 for busy systems. Use 30 when traffic is low or bursty, otherwise much of the map shows zero.

Add a `package.json` with these scripts:
- `build`: `python3 build.py && node scripts/validate.js <slug>-system-map.html`
- `open`: `pnpm build && open <slug>-system-map.html` (`xdg-open` on Linux)
- `collect`: `python3 -I scripts/collect.py && pnpm build`
- `dns-check`: `python3 -I scripts/dns-check.py`

If the folder isn't a git repo, don't init one unless asked.

## 3. Collect

```sh
python3 -I scripts/collect.py            # all configured providers; or: collect.py aws gcp
```

It's read-only and takes about 1–3 minutes per provider. Check the summary line counts against what `discover.sh` showed. If a provider fails (expired login, missing CLI), report it and carry on with the rest.

## 4. Read the code

Follow `references/code-survey.md`:
- List repos with last-commit dates.
- **Work out which copy of each service is live** by matching deploy scripts against what exists in the cloud. Monorepos often sit next to stale standalone repos.
- Fan out 3–5 read-only Explore agents (API, functions/workers, front-ends/sites, infra), giving each the cloud facts so they map code to real resources.

While they run, start on the cloud-only checks in `references/findings-checklist.md`: dangling DNS, public databases, error storms, EOL runtimes, leftovers. Then re-check any agent claim that will become a finding with your own grep.

## 5. Write the model and findings

Read `references/model-guide.md`, then fill `src/model.js` (maps, domains, nodes, edges, flows) and `src/findings.js`:
- Take volumes from `data/aws/metrics.tsv` and the `vol` field of other providers' rows.
- Mark anything unconfirmed `inferred: true`.
- Set `provider` on nodes when more than one provider is mapped.
- Add a **Leftovers** map for unused or test resources.
- List direct invokes from code in `data/direct-triggers.json` (`{"function": "who calls it"}`), so the Inventory shows triggers AWS doesn't record.

## 6. Build, validate, look at it

```sh
python3 build.py && node scripts/validate.js <slug>-system-map.html
```

Fix every PROBLEM line, such as unknown node ids or flow steps without edges. Then view it. Browser automation usually can't open `file://`, so serve the folder with `python3 -m http.server 8765 --bind 127.0.0.1` (in the background), open `http://127.0.0.1:8765/<slug>-system-map.html`, and check:
- every map renders
- the console is clean
- Findings and Inventory are populated

Stop the server and close the tab afterwards.

## 7. Write README.md and TODO.md, then report

- **README**: what it is, quick start, requirements (including which profile, configuration or token each provider uses), commands, how to edit the model, how to refresh, and how it was made (which accounts and repos).
- **TODO**: security fixes first, then decisions needed, fixes, open questions and map improvements.
- **Final message**: where the page is, what's on it, the top findings in plain words, what couldn't be checked, and anything that went wrong during collection.

## Ground rules

- **Read-only.** Never change cloud resources, DNS, repos or git state while mapping. Offering fixes is fine; doing them needs an explicit ask.
- **Secrets**: record where a secret is (file:line, which kind), never its value, not even partly. If a value scrolls past in tool output, don't repeat it anywhere.
- **Pinned identity**: always pass the configured profile, configuration or subscription explicitly. Never rely on the shell's defaults.
- **`rm` in scripts** uses `"${VAR:?}/…"` so an empty variable can't expand to `/`. Avoid ad-hoc deletes of collected data: rerunning a collector overwrites its files.
- The page lists security findings, so treat it as internal and don't publish it anywhere public without asking.
