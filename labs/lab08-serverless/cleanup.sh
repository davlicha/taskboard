#!/usr/bin/env bash
set -uo pipefail
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
aws() { command aws --endpoint-url "${ENDPOINT:-http://localhost:4566}" --output text "$@"; }
for id in $(aws apigateway get-rest-apis --query "items[?name=='items-api'].id"); do aws apigateway delete-rest-api --rest-api-id "$id"; done
aws lambda delete-function --function-name items-api
aws dynamodb delete-table --table-name items >/dev/null
aws iam delete-role --role-name lambda-items-role
echo cleaned
