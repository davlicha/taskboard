#!/usr/bin/env bash
# ЛР-10: повний експеримент. Потрібен запущений стек ЛР-9 з METRICS_ENABLED=true:
#   (cd ../lab09-load-balancing && METRICS_ENABLED=true docker compose up -d --build)
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-python3}
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
mkdir -p out
echo "[]" > out/events.json
mark() { $PY - "$1" <<'PYEOF'
import json, sys
from datetime import datetime, UTC
ev = json.load(open("out/events.json")); ev.append({"name": sys.argv[1], "start": datetime.now(UTC).isoformat()})
json.dump(ev, open("out/events.json", "w"))
PYEOF
}
state() { aws --endpoint-url http://localhost:4566 cloudwatch describe-alarms \
  --query 'MetricAlarms[].[AlarmName,StateValue]' --output text | tr '\n' ' '; echo; }

./setup_alarms.sh

# фоновий запис станів alarm кожні 5 с -> out/alarm_states.csv
echo "time,alarm,state" > out/alarm_states.csv
( while true; do
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    aws --endpoint-url http://localhost:4566 cloudwatch describe-alarms \
      --query 'MetricAlarms[].[AlarmName,StateValue]' --output text 2>/dev/null |
      while read -r name st; do echo "$ts,$name,$st"; done >> out/alarm_states.csv
    sleep 5
  done ) &
POLLER=$!
trap 'kill $POLLER 2>/dev/null' EXIT
echo "== 1. Нормальне навантаження";      mark normal; $PY load.py normal --duration 90 --rps 20;  state
echo "== 2. Підвищене навантаження";      mark "high load"; $PY load.py normal --duration 60 --rps 60; state
echo "== 3. Помилки (40% запитів 5xx)";   mark errors; $PY load.py errors --duration 90 --rps 20; sleep 20; state
echo "== 4. Затримки (50% запитів +600мс)"; mark slow; $PY load.py slow --duration 90 --rps 6 --fraction 0.5; sleep 20; state
echo "== 5. Відновлення";                 mark recovery; $PY load.py normal --duration 90 --rps 20; sleep 20; state
sleep 15
if [ -n "${ANALYZE_IN_DOCKER:-}" ]; then   # якщо локально немає Python 3.12 з matplotlib
  docker run --rm -v "$PWD":/w -w /w -e AWS_ENDPOINT_URL=http://host.docker.internal:4566 python:3.12-slim \
    sh -c "pip install -q --root-user-action=ignore -r requirements.txt >/dev/null 2>&1 && python analyze.py --minutes 11 --period 30"
else
  $PY analyze.py --minutes 11 --period 30
fi
