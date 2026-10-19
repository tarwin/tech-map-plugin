#!/usr/bin/env bash
# Pull the AWS inventory behind the map into data/aws/. Read-only AWS calls.
# Settings come from tech-map.config.json → providers.aws (profile, account, regions). The profile is pinned from
# that file on purpose: a shell-wide AWS_PROFILE for another company must never leak in, and the
# account ID check stops the run if the profile points somewhere else.
#
# Environment variables of Lambdas, EB envs and ECS tasks are never written: they can hold secrets.
#
# Usage: scripts/providers/aws.sh   (normally run by scripts/collect.py)
set -euo pipefail
cd "$(dirname "$0")/../.."
CFG=tech-map.config.json
export AWS_PROFILE; AWS_PROFILE=$(jq -r .providers.aws.profile "$CFG")
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
ACCOUNT=$(jq -r .providers.aws.account "$CFG")
REGIONS=$(jq -r '.providers.aws.regions | join(" ")' "$CFG")
actual=$(aws sts get-caller-identity --query Account --output text)
[ "$actual" = "$ACCOUNT" ] || { echo "Profile $AWS_PROFILE is account $actual, expected $ACCOUNT. Stopping." >&2; exit 1; }

OUT=data/aws
mkdir -p "$OUT"
# Run an AWS call; on any error (no permission, service not in region) or empty output
# (e.g. sqs list-queues with no queues prints nothing) emit an empty object instead.
j() { local o; o=$("$@" --output json 2>/dev/null) || o=''; [ -n "$o" ] && printf '%s\n' "$o" || echo '{}'; }

for r in $REGIONS; do
  echo "== $r"
  mkdir -p "$OUT/$r"
  rm -f "${OUT:?}/${r:?}"/ebcfg-*.json
  j aws lambda list-functions --region "$r" \
    | jq '{Functions: [.Functions[]? | {FunctionName, Runtime, PackageType, LastModified, MemorySize, Timeout}]}' > "$OUT/$r/lambdas.json"
  j aws lambda list-event-source-mappings --region "$r" \
    | jq '{EventSourceMappings: [.EventSourceMappings[]? | {EventSourceArn, FunctionArn, State}]}' > "$OUT/$r/esm.json"
  # Who may invoke each function (S3, API Gateway, SNS, EventBridge…): principal + source ARN only.
  jq -r '.Functions[].FunctionName' "$OUT/$r/lambdas.json" | while read -r fn; do
    p=$(aws lambda get-policy --region "$r" --function-name "$fn" --query Policy --output text 2>/dev/null || true)
    if [ -n "$p" ]; then  # an if, not &&: a trailing false would fail the pipeline under set -e/pipefail
      echo "$p" | jq -c --arg fn "$fn" '{fn: $fn, allow: [.Statement[] | {principal: (.Principal.Service // .Principal.AWS // "?"), source: (.Condition.ArnLike."AWS:SourceArn" // .Condition.ArnEquals."AWS:SourceArn" // "")}]}'
    fi
  done | jq -s '{Policies: .}' > "$OUT/$r/lambda-policies.json"
  j aws scheduler list-schedules --region "$r" \
    | jq '{Schedules: [.Schedules[]? | {Name, State, Target: .Target.Arn}]}' > "$OUT/$r/schedules.json"
  j aws events list-rules --region "$r" | jq -c '.Rules[]? | {Name, State, ScheduleExpression, EventPattern}' | while read -r rule; do
    name=$(echo "$rule" | jq -r .Name)
    t=$(j aws events list-targets-by-rule --region "$r" --rule "$name" | jq -c '[.Targets[]?.Arn]')
    echo "$rule" | jq -c --argjson t "$t" '. + {Targets: $t}'
  done | jq -s '{Rules: .}' > "$OUT/$r/rules.json"
  j aws elasticbeanstalk describe-environments --region "$r" \
    | jq '{Environments: [.Environments[]? | select(.Status != "Terminated") | {ApplicationName, EnvironmentName, Tier, Health, CNAME, SolutionStackName, VersionLabel, DateUpdated}]}' > "$OUT/$r/eb.json"
  # Only sizing and worker-queue settings from each EB env, never application env vars.
  jq -r '.Environments[] | [.ApplicationName, .EnvironmentName] | @tsv' "$OUT/$r/eb.json" | while IFS=$'\t' read -r app env; do
    j aws elasticbeanstalk describe-configuration-settings --region "$r" --application-name "$app" --environment-name "$env" \
      | jq '{ConfigurationSettings: [{OptionSettings: [.ConfigurationSettings[0].OptionSettings[]?
          | select(.Namespace == "aws:elasticbeanstalk:sqsd" or .Namespace == "aws:autoscaling:asg"
                   or .Namespace == "aws:autoscaling:launchconfiguration" or .Namespace == "aws:elasticbeanstalk:environment")
          | select(.OptionName | IN("WorkerQueueURL", "HttpPath", "MinSize", "MaxSize", "InstanceType", "LoadBalancerType"))]}]}' \
      > "$OUT/$r/ebcfg-$env.json" &
  done
  wait
  j aws sqs list-queues --region "$r" | jq '{QueueUrls: (.QueueUrls // [])}' > "$OUT/$r/sqs.json"
  j aws sns list-topics --region "$r" | jq '{Topics: [.Topics[]?.TopicArn]}' > "$OUT/$r/sns.json"
  # Subscription endpoints only for AWS targets; email/SMS/HTTP endpoints can be personal data.
  j aws sns list-subscriptions --region "$r" \
    | jq '{Subscriptions: [.Subscriptions[]? | {TopicArn, Protocol, Endpoint: (if (.Protocol | IN("lambda", "sqs", "firehose")) then .Endpoint else null end)}]}' > "$OUT/$r/sns-subs.json"
  # ECS: services per cluster (no task-definition env vars).
  for c in $(j aws ecs list-clusters --region "$r" | jq -r '.clusterArns[]?'); do
    for chunk in $(j aws ecs list-services --region "$r" --cluster "$c" | jq -r '.serviceArns | _nwise(10) | join(",")' 2>/dev/null); do
      j aws ecs describe-services --region "$r" --cluster "$c" --services $(echo "$chunk" | tr ',' ' ') \
        | jq -c '.services[]? | {cluster: (.clusterArn | split("/")[-1]), service: .serviceName, launch: (.launchType // "capacity provider"), desired: .desiredCount, running: .runningCount, taskdef: (.taskDefinition | split("/")[-1])}'
    done
  done | jq -s '{Services: .}' > "$OUT/$r/ecs.json"
  j aws rds describe-db-instances --region "$r" \
    | jq '{DBInstances: [.DBInstances[]? | {DBInstanceIdentifier, DBClusterIdentifier, Engine, EngineVersion, DBInstanceClass, MultiAZ, PubliclyAccessible, SecurityGroups: [.VpcSecurityGroups[]?.VpcSecurityGroupId]}]}' > "$OUT/$r/rds.json"
  j aws dynamodb list-tables --region "$r" | jq '{TableNames: (.TableNames // [])}' > "$OUT/$r/dynamo.json"
  j aws elasticache describe-cache-clusters --region "$r" \
    | jq '{CacheClusters: [.CacheClusters[]? | {CacheClusterId, Engine, CacheNodeType, NumCacheNodes}]}' > "$OUT/$r/elasticache.json"
  { j aws apigatewayv2 get-apis --region "$r" | jq -c '.Items[]? | {name: .Name, type: .ProtocolType, endpoint: .ApiEndpoint}'
    j aws apigateway get-rest-apis --region "$r" | jq -c --arg r "$r" '.items[]? | {name: .name, type: "REST", endpoint: "https://\(.id).execute-api.\($r).amazonaws.com"}'
  } | jq -s '{Apis: .}' > "$OUT/$r/apigw.json"
done

echo "== global"
j aws cloudfront list-distributions --region us-east-1 \
  | jq '{Distributions: [.DistributionList.Items[]? | {Id, Aliases: (.Aliases.Items // []), DomainName, Origins: [.Origins.Items[].DomainName], Comment, Enabled}]}' > "$OUT/cloudfront.json"
# Buckets with region and event notifications (S3 → Lambda / SQS / SNS triggers).
j aws s3api list-buckets | jq -r '.Buckets[]?.Name' | while read -r b; do
  reg=$(aws s3api get-bucket-location --bucket "$b" --query LocationConstraint --output text 2>/dev/null || echo "?")
  [ "$reg" = "None" ] && reg=us-east-1
  n=$(j aws s3api get-bucket-notification-configuration --bucket "$b" | jq -c '
      def pfx: [.Filter.Key.FilterRules[]? | select(.Name == "Prefix") | .Value] | first;
      [(.LambdaFunctionConfigurations[]? | {type: "lambda", target: .LambdaFunctionArn, prefix: pfx}),
       (.QueueConfigurations[]? | {type: "sqs", target: .QueueArn, prefix: pfx}),
       (.TopicConfigurations[]? | {type: "sns", target: .TopicArn, prefix: pfx})]')
  jq -nc --arg b "$b" --arg r "$reg" --argjson n "${n:-[]}" '{name: $b, region: $r, notifications: $n}'
done | jq -s '{Buckets: .}' > "$OUT/s3.json"

echo "== metrics"; python3 -I scripts/providers/aws_metrics.py
