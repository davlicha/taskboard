#!/usr/bin/env bash
# ЛР-8: автоматизоване розгортання serverless-застосунку в LocalStack через AWS CLI.
#   DynamoDB table -> IAM role -> Lambda -> API Gateway (REST, proxy) -> stage "dev"
set -euo pipefail
cd "$(dirname "$0")"

export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-test}
export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-test}
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1}
ENDPOINT=${ENDPOINT:-http://localhost:4566}
TABLE=${TABLE:-items}
FUNC=${FUNC:-items-api}
API_NAME=${API_NAME:-items-api}
STAGE=${STAGE:-dev}
aws() { command aws --endpoint-url "$ENDPOINT" --output text "$@"; }

echo "==> 1. DynamoDB table '$TABLE'"
if ! aws dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  aws dynamodb create-table --table-name "$TABLE" \
    --attribute-definitions AttributeName=id,AttributeType=S \
    --key-schema AttributeName=id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST >/dev/null
  aws dynamodb wait table-exists --table-name "$TABLE"
fi

echo "==> 2. IAM role"
ROLE_ARN=$(aws iam get-role --role-name lambda-items-role --query Role.Arn 2>/dev/null || \
  aws iam create-role --role-name lambda-items-role --query Role.Arn \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}')

echo "==> 3. Lambda '$FUNC'"
BUILD=$(mktemp -d)
cp lambda/*.py "$BUILD"/
(cd "$BUILD" && zip -q function.zip ./*.py)
if aws lambda get-function --function-name "$FUNC" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FUNC" --zip-file "fileb://$BUILD/function.zip" >/dev/null
else
  aws lambda create-function --function-name "$FUNC" \
    --runtime python3.12 --handler handler.lambda_handler \
    --role "$ROLE_ARN" --timeout 15 --memory-size 256 \
    --environment "Variables={TABLE_NAME=$TABLE}" \
    --zip-file "fileb://$BUILD/function.zip" >/dev/null
fi
aws lambda wait function-active-v2 --function-name "$FUNC"
rm -rf "$BUILD"
FUNC_ARN=$(aws lambda get-function --function-name "$FUNC" --query Configuration.FunctionArn)

echo "==> 4. API Gateway '$API_NAME'"
for old in $(aws apigateway get-rest-apis --query "items[?name=='$API_NAME'].id"); do
  aws apigateway delete-rest-api --rest-api-id "$old"
done
API_ID=$(aws apigateway create-rest-api --name "$API_NAME" --query id)
ROOT_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --query "items[?path=='/'].id")
URI="arn:aws:apigateway:${AWS_DEFAULT_REGION}:lambda:path/2015-03-31/functions/${FUNC_ARN}/invocations"

add_proxy_method() { # $1 = resource id
  aws apigateway put-method --rest-api-id "$API_ID" --resource-id "$1" \
    --http-method ANY --authorization-type NONE >/dev/null
  aws apigateway put-integration --rest-api-id "$API_ID" --resource-id "$1" \
    --http-method ANY --type AWS_PROXY --integration-http-method POST --uri "$URI" >/dev/null
}
ITEMS_ID=$(aws apigateway create-resource --rest-api-id "$API_ID" --parent-id "$ROOT_ID" --path-part items --query id)
ITEM_ID=$(aws apigateway create-resource --rest-api-id "$API_ID" --parent-id "$ITEMS_ID" --path-part '{id}' --query id)
HEALTH_ID=$(aws apigateway create-resource --rest-api-id "$API_ID" --parent-id "$ROOT_ID" --path-part health --query id)
for r in "$ITEMS_ID" "$ITEM_ID" "$HEALTH_ID"; do add_proxy_method "$r"; done

aws lambda add-permission --function-name "$FUNC" --statement-id "apigw-$API_ID" \
  --action lambda:InvokeFunction --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:${AWS_DEFAULT_REGION}:000000000000:${API_ID}/*/*/*" >/dev/null
aws apigateway create-deployment --rest-api-id "$API_ID" --stage-name "$STAGE" >/dev/null

BASE="$ENDPOINT/restapis/$API_ID/$STAGE/_user_request_"
echo "$BASE" > .api-url
echo
echo "Готово. Базова URL API:"
echo "  $BASE"
echo "Перевірка: ./test.sh"
