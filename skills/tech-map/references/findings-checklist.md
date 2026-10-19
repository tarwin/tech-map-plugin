# Findings checklist

Run these checks during mapping. They're cheap and read-only, and they find real problems. Run each command with the pinned identity: `AWS_PROFILE=<profile>` on the command (or exported in that same shell command), `--project` for gcloud, `--subscription` for az. Commands below are AWS; the other collectors flag the equivalent problems (open SQL firewalls, public buckets/blob access, queues with no consumer) in their Inventory rows.

## Exposure (usually high)

- **Dangling DNS / subdomain takeover**: `python3 -I scripts/dns-check.py --all`. It checks Route 53 plus Cloudflare, Azure, Cloud DNS, Vercel and Netlify records against every collected provider. A record pointing at a missing EB env with `claimable=True`, or at a deleted App Service, Cloud Run service, Netlify/Vercel/Pages site or S3 bucket, is high severity.
- **Public databases**: for each RDS/Aurora instance with `PubliclyAccessible: true`, inspect its security groups:
  ```sh
  aws ec2 describe-security-groups --region R --group-ids sg-a sg-b \
    | jq -c '.SecurityGroups[] | {GroupId, GroupName, ingress: [.IpPermissions[] | {FromPort, cidr: [.IpRanges[].CidrIp], sg: [.UserIdGroupPairs[].GroupId]}]}'
  ```
  Port 3306/5432/6379/27017 open to `0.0.0.0/0` is high. Pass group IDs as separate arguments; `--output text` joins them with tabs.
- **Credentials in shipped code**: mobile app configs, front-end `.env.production` files tracked in git (`git ls-files | grep -E '\.env(\.|$)'`), `AKIA[0-9A-Z]{16}` patterns, service-account JSON files, private keys. Check `git ls-files` to confirm a file is tracked before reporting it. Report the location only.
- **Public buckets**: `aws s3api get-public-access-block --bucket B`, and whether deploy scripts use `--acl public-read` on buckets holding user data.

## Correctness and auth (usually medium)

- Callback and webhook endpoints that mutate state without a secret or signature.
- Shared-secret server-to-server schemes: one secret for every caller, or signatures that don't cover the body.
- Production code pointing at `-dev`, `-staging`, `test`, ngrok or `loca.lt` hosts.
- **Error storms**: Lambdas with errors over ~5% of invocations (from metrics.tsv). Group the causes with Logs Insights:
  ```sh
  q=$(aws logs start-query --region R --log-group-name /aws/lambda/FN --start-time $(date -v-7d +%s 2>/dev/null || date -d '7 days ago' +%s) --end-time $(date +%s) \
      --query-string 'fields @message | filter @message like /ERROR|Task timed out/ | parse @message /(?<m>(Error|ERROR|Task timed out)[^\n]{0,110})/ | stats count() as n by m | sort n desc | limit 8' \
      --query queryId --output text); sleep 12; aws logs get-query-results --region R --query-id "$q" | jq -r '.results[] | map(.value) | join("  ")'
  ```
  (Logs Insights rejects function calls like `substr()` inside `stats … by`; use `parse` into a field.) A common root cause: a handler throws on "skip" cases, so async retries triple the work.
- **End-of-life runtimes**: nodejs ≤ 18, python ≤ 3.8, Tomcat 8.5, old Amazon Linux platforms.
- No consumer: queues with messages sent but no ESM or EB worker; topics with no subscriptions.
- No producer: queues and Lambdas with a trigger but zero traffic, and code that shows the send was removed.

## Hygiene (usually info)

- Leftovers: Grey or 0-instance EB envs (their load balancers still cost money), functions with zero invocations and no trigger, test functions and buckets, stale ECR repos, distributions with zero requests, personal or test stacks in the prod account.
- Region sprawl: which regions hold what, and flows that cross regions.
- Infrastructure as code: present or not; laptop deploys; IAM rights added by hand (look for AccessDenied in logs).
- Superseded repos: standalone copies of monorepo apps.
