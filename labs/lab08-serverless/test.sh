#!/usr/bin/env bash
# ЛР-8: перевірка CRUD через HTTP-клієнт (curl)
set -euo pipefail
cd "$(dirname "$0")"
BASE=${BASE:-$(cat .api-url)}
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
j() { python3 -m json.tool; }

echo "--- GET /health";            curl -s "$BASE/health" | j
echo "--- POST /items";            CREATED=$(curl -s -X POST "$BASE/items" -H 'Content-Type: application/json' -d '{"title":"Lab 8","note":"serverless on LocalStack"}')
echo "$CREATED" | j
ID=$(echo "$CREATED" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
echo "--- GET /items";             curl -s "$BASE/items" | j
echo "--- GET /items/$ID";         curl -s "$BASE/items/$ID" | j
echo "--- DELETE /items/$ID";      curl -s -X DELETE "$BASE/items/$ID" | j
echo "--- GET /items/$ID (404)";   curl -s -w '\nHTTP %{http_code}\n' "$BASE/items/$ID"
echo "--- POST /items без title (400)"; curl -s -w '\nHTTP %{http_code}\n' -X POST "$BASE/items" -H 'Content-Type: application/json' -d '{}'
echo "--- DynamoDB scan";          aws --endpoint-url "${ENDPOINT:-http://localhost:4566}" dynamodb scan --table-name items --query Count
