#!/usr/bin/env bash
# Which regions does this AWS account actually use? Read-only.
# Prints one line per region with resource counts, for regions with anything in them.
#
# Usage: discover.sh <aws-profile>
# The profile is passed explicitly and exported, so a shell-wide AWS_PROFILE can't leak in.
set -uo pipefail
PROFILE="${1:?usage: discover.sh <aws-profile>}"
export AWS_PROFILE="$PROFILE"
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

acct=$(aws sts get-caller-identity --query Account --output text) || { echo "cannot authenticate with profile $PROFILE" >&2; exit 1; }
alias=$(aws iam list-account-aliases --query 'AccountAliases[0]' --output text 2>/dev/null)
echo "account=$acct alias=${alias:-none} profile=$PROFILE"

count() { local v; v=$("$@" --output text 2>/dev/null); [[ "$v" =~ ^[0-9]+$ ]] && echo "$v" || echo 0; }
for r in $(aws ec2 describe-regions --region us-east-1 --query 'Regions[].RegionName' --output text); do
  (
    l=$(count aws lambda list-functions --region "$r" --query 'length(Functions)')
    eb=$(count aws elasticbeanstalk describe-environments --region "$r" --query 'length(Environments[?Status!=`Terminated`])')
    q=$(count aws sqs list-queues --region "$r" --query 'length(QueueUrls || `[]`)')
    ec2=$(count aws ec2 describe-instances --region "$r" --query 'length(Reservations[].Instances[])')
    ecs=$(count aws ecs list-clusters --region "$r" --query 'length(clusterArns)')
    rds=$(count aws rds describe-db-instances --region "$r" --query 'length(DBInstances)')
    ddb=$(count aws dynamodb list-tables --region "$r" --query 'length(TableNames)')
    api=$(( $(count aws apigatewayv2 get-apis --region "$r" --query 'length(Items)') + $(count aws apigateway get-rest-apis --region "$r" --query 'length(items)') ))
    total=$((l + eb + q + ec2 + ecs + rds + ddb + api))
    [ "$total" -gt 0 ] && echo "$r lambda=$l eb=$eb sqs=$q ec2=$ec2 ecs=$ecs rds=$rds dynamodb=$ddb apigw=$api"
  ) &
done
wait
