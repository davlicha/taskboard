#!/usr/bin/env bash
# ЛР-10: CloudWatch Alarms + SNS-топік для сповіщень
set -euo pipefail
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
aws() { command aws --endpoint-url "${ENDPOINT:-http://localhost:4566}" "$@"; }
NS=Lab10/ItemsApp
DIM=Name=Service,Value=items-api

TOPIC=$(aws sns create-topic --name lab10-alerts --query TopicArn --output text)

# 1) Помилки: сума ErrorCount за 30 с > 10
aws cloudwatch put-metric-alarm --alarm-name items-api-high-errors \
  --alarm-description "Забагато 5xx у items-api" \
  --namespace "$NS" --metric-name ErrorCount --dimensions "$DIM" \
  --statistic Sum --period 30 --evaluation-periods 1 --datapoints-to-alarm 1 \
  --threshold 10 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching --alarm-actions "$TOPIC" --ok-actions "$TOPIC"

# 2) Затримка: середня Latency за 30 с > 300 мс
aws cloudwatch put-metric-alarm --alarm-name items-api-high-latency \
  --alarm-description "Середній час відповіді > 300 мс" \
  --namespace "$NS" --metric-name Latency --dimensions "$DIM" \
  --statistic Average --period 30 --evaluation-periods 1 --datapoints-to-alarm 1 \
  --threshold 300 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching --alarm-actions "$TOPIC" --ok-actions "$TOPIC"

aws cloudwatch describe-alarms --query 'MetricAlarms[].[AlarmName,StateValue,MetricName,Threshold]' --output table
