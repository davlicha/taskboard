# ЛР-7. Observability: метрики, логи, дашборди й відкат за метриками

## 1. Стек моніторингу через Argo CD (`argocd-apps/`)

| Application | Чарт | Примітки |
|---|---|---|
| `kube-prometheus-stack` | prometheus-community 93.11.0 | `ServerSideApply=true` (великі CRD); `*SelectorNilUsesHelmValues: false` — підхоплює ServiceMonitor/PrometheusRule з усіх namespace; Grafana sidecar шукає дашборди з міткою `grafana_dashboard` в усіх namespace; додано datasource Loki (`uid: loki`); пароль Grafana — із секрету `grafana-admin` (не в Git) |
| `loki` | grafana-community/loki 21.6.0 | `deploymentMode: Monolithic` (один процес), filesystem, без gateway/cache/canary |
| `alloy` | grafana/alloy 1.16.0 | Deployment ×1; `discovery.kubernetes` → `loki.source.kubernetes` (логи через API) → `loki.write`; мітки `namespace, pod, container, component, version` |

```bash
kubectl -n monitoring get pods
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80     # admin / пароль з create-secrets.sh
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090
```

## 2. Метрики застосунку

`services/api/app/main.py`, middleware `observability`:

- `http_requests_total{method, route, status}` — Counter;
- `http_request_duration_seconds{method, route}` — Histogram (бакети 5 мс … 5 с);
- **route — шаблон маршруту** (`/api/tasks/{task_id}`), а не сирий шлях; невідомі шляхи → `unmatched`; `/metrics` не рахується.
  Мала кардинальність покрита тестами `test_metrics_use_route_template`, `test_injected_failure_keeps_route_template`.

`templates/servicemonitor.yaml` (`metrics.serviceMonitor.enabled`) з `podTargetLabels: [rollouts-pod-template-hash, app.kubernetes.io/version]` —
у метриках з'являються мітки `rollouts_pod_template_hash` і `app_kubernetes_io_version`, тож stable і canary розрізняються в PromQL.

Prometheus → Status → Targets → `serviceMonitor/taskboard/taskboard-api/0` — **UP**. Запит:

```promql
sum by (route, status) (rate(http_requests_total{namespace="taskboard"}[1m]))
```

## 3. Логи

JSON у stdout (`app/logging_setup.py`): `time, level, msg, method, route, status, duration_ms, instance, version`.

LogQL у Grafana Explore → Loki:

```logql
{namespace="taskboard", container="api"} | json | status >= 500
sum by (pod) (count_over_time({namespace="taskboard", container="api"} | json | status >= 500 [1m]))
```

## 4. Дашборд

`charts/taskboard/dashboards/taskboard.json` → `templates/dashboard-configmap.yaml` (ConfigMap з міткою `grafana_dashboard: "1"`),
доставляється Argo CD разом із чартом. Панелі:

| Панель | Запит |
|---|---|
| RPS (за статусом і версією) | `sum by (status) (rate(http_requests_total{route=~"/api/.*"}[1m]))` |
| Частка 5xx (загальна і за pod-template-hash) | `sum(rate(...{status=~"5.."}[1m])) / sum(rate(...[1m]))` |
| p95 / p50 затримки | `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[1m])))` |
| CPU подів | `rate(container_cpu_usage_seconds_total{container="api"}[1m])` |
| Пам'ять подів | `container_memory_working_set_bytes{container="api"}` |
| Логи API, Помилки 5xx | Loki |

## 5. Навантаження

```bash
kubectl apply -f tools/loadgen.yaml
kubectl -n taskboard scale deploy/loadgen --replicas=5     # ~50 RPS
```

Додаткова зміна (на вибір): `api.slowMs: "300"` у `values-minikube.yaml` → commit → p95 на дашборді росте до ~0,3 с;
або видалення пода — видно падіння й відновлення RPS одного pod.

## 6. Автоматичний відкат

**a)** `templates/analysistemplate.yaml` — `AnalysisTemplate` `<release>-success-rate`:

```promql
sum(rate(http_requests_total{namespace="taskboard", service="taskboard-api",
    rollouts_pod_template_hash="{{args.canary-hash}}", route=~"/api/.*", status!~"5.."}[1m]))
/
sum(rate(http_requests_total{..., rollouts_pod_template_hash="{{args.canary-hash}}", route=~"/api/.*"}[1m]))
```

`successCondition: result[0] >= 0.95`, `interval: 30s`, `count: 4`, `failureLimit: 1`. Хеш canary передається з Rollout
(`valueFrom.podTemplateHashValue: Latest`) — аналізуються **лише поди нової версії**. Крок `analysis` стоїть одразу після `setWeight: 25`.

**b)** «Погана» поведінка — змінна `FAIL_RATE` (`api.failRate` у values): частка запитів `/api/*` отримує 500.

**c)** Сценарій:

```bash
kubectl -n taskboard scale deploy/loadgen --replicas=3
# values-minikube.yaml: api.failRate: "0.3"   (або разом із новим тегом)
git commit -am "bad release: FAIL_RATE=0.3" && git push
kubectl argo rollouts get rollout taskboard-api -n taskboard --watch
kubectl -n taskboard get analysisrun
```

Очікувано: AnalysisRun `Failed` (success rate ≈ 0,70 < 0,95) → Rollout `Aborted`, всі 4 поди — stable; на дашборді — сплеск
5xx лише для одного `rollouts_pod_template_hash`; у Loki:

```logql
{namespace="taskboard", container="api"} | json | status >= 500
```

— усі рядки з `pod=taskboard-api-<новий-hash>-...`. Завершення: `git revert --no-edit HEAD && git push`.

**d\*)** `templates/prometheusrule.yaml` — алерт `TaskboardHighErrorRate` (частка 5xx > 5% протягом 1 хв) →
Prometheus → Alerts: `Firing` під час кроку c).

## 7. Шпаргалка PromQL / LogQL для захисту

```promql
sum(rate(http_requests_total{namespace="taskboard"}[1m]))                                   # загальний RPS
sum by (app_kubernetes_io_version) (rate(http_requests_total{namespace="taskboard"}[1m]))   # RPS за версією
histogram_quantile(0.99, sum by (le, route) (rate(http_request_duration_seconds_bucket[5m])))
topk(3, sum by (route) (rate(http_requests_total[5m])))
```
```logql
{namespace="taskboard", container="api"} | json | duration_ms > 100
sum by (status) (count_over_time({namespace="taskboard", container="api"} | json [5m]))
```

## Перевірка на minikube

Перед здачею ланцюжок «ServiceMonitor → Prometheus → AnalysisTemplate → Rollout» перевірено на minikube
(контролери встановлено `helm install` тими самими версіями й values, що в `argocd-apps/`). Вивід — [`evidence/lab06-07-output.txt`](evidence/lab06-07-output.txt).

- Targets `serviceMonitor/taskboard/taskboard-api/0` — 4 × **up**; у метриках є `rollouts_pod_template_hash` і `app_kubernetes_io_version`.
- **Хороший реліз** → AnalysisRun `Successful` (вимірювання `1, 1, 1`) → ручна пауза на 25%.
- **Поганий реліз** (`api.failRate=0.3`) → вимірювання **0.714**, **0.699** < 0.95 → AnalysisRun `Failed` →
  `RolloutAborted: Metric "success-rate" assessed Failed due to failed (2) > failureLimit (1)` → 4 stable-поди.
- 5xx у Prometheus — лише з `rollouts_pod_template_hash` нової версії.
- `PrometheusRule` у цьому прогоні **не** дійшов до `Firing`: canary жила ~1 хв (abort), а загальна частка 5xx (1 з 4 подів × 30% ≈ 7,5%)
  мусить триматися `for: 1m`. Для демонстрації d\*) — запускати поганий реліз з `analysis.enabled: false` або тимчасово `for: 15s`.

Знахідки, виправлені після перевірки:
1. Перше вимірювання хорошого релізу було `[]` (новий под ще не мав хвилини даних для `rate()`), тому додано `initialDelay: 30s`.
2. `FAIL_RATE`/`SLOW_MS` перенесено з ConfigMap у `env` шаблону пода: ConfigMap спільний для версій, і після abort
   stable-под, що перезапускається, підхопив би «погане» значення.
3. `helm install --wait` не вміє чекати на CRD Rollout (статус `Unknown`) — це не стосується Argo CD, який має вбудований health-check для Rollout.
