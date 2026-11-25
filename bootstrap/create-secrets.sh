#!/usr/bin/env bash
# Створює секрет БД поза Git (ЛР-5: паролі відкритим текстом у Git не зберігаються).
set -euo pipefail
NS=${NS:-taskboard}
PASSWORD=${DB_PASSWORD:-$(openssl rand -hex 12)}
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NS" create secret generic taskboard-db \
  --from-literal=POSTGRES_USER=taskboard \
  --from-literal=POSTGRES_PASSWORD="$PASSWORD" \
  --from-literal=POSTGRES_DB=taskboard \
  --dry-run=client -o yaml | kubectl apply -f -
echo "secret $NS/taskboard-db is ready"

# ЛР-7: пароль адміністратора Grafana
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
GRAFANA_PASSWORD=${GRAFANA_PASSWORD:-$(openssl rand -hex 8)}
kubectl -n monitoring create secret generic grafana-admin \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$GRAFANA_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "Grafana: admin / $GRAFANA_PASSWORD"
