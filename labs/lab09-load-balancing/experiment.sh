#!/usr/bin/env bash
# ЛР-9: повний сценарій дослідження. Результати -> results/
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results
N=${N:-300}; C=${C:-10}
LB=http://localhost:8080/items
DIRECT=http://localhost:8001/items
lt() { python3 loadtest.py --url "$1" -n "$N" -c "$C"; }

{
echo "### 0. Стан контейнерів"; docker compose ps --format 'table {{.Service}}\t{{.Status}}'
echo; echo "### 1. Кожен екземпляр повертає свій ідентифікатор (5 запитів через nginx)"
for i in 1 2 3 4 5 6; do curl -s localhost:8080/ ; echo; done
echo; echo "### 2. /health через балансувальник"; curl -s localhost:8080/health; echo
echo; echo "### 3. Розподіл $N запитів через балансувальник (3 екземпляри)"; lt $LB
echo; echo "### 4. Виводимо app2 з роботи: docker compose stop app2"; docker compose stop app2 2>&1 | tail -1
lt $LB
echo; echo "### 5. Повертаємо app2: docker compose start app2"; docker compose start app2 2>&1 | tail -1
sleep 12   # fail_timeout=10s — після нього nginx знову пробує app2
lt $LB
echo; echo "### 6. Порівняння: без балансування (лише app1 напряму) vs з балансуванням"
echo "-- без балансування:"; lt $DIRECT
echo "-- з балансуванням:";  lt $LB
echo; echo "### 7. Відмова екземпляра без балансування: docker compose stop app1"
docker compose stop app1 2>&1 | tail -1
echo "-- напряму в app1:"; python3 loadtest.py --url $DIRECT -n 50 -c 5
echo "-- через nginx:";   python3 loadtest.py --url $LB -n 50 -c 5
docker compose start app1 2>&1 | tail -1
echo; echo "### 8. Журнал nginx (останні 10 рядків)"; docker compose logs nginx --no-log-prefix 2>/dev/null | grep upstream= | tail -10
} 2>&1 | tee results/experiment-output.txt
