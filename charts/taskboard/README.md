# Helm-чарт `taskboard`

Розгортає весь проєкт: `api` (FastAPI), `web` (Flask), PostgreSQL з PVC, опційно Ingress.
Той самий набір об'єктів, що й маніфести з `k8s/` (ЛР-3), але параметризований.

## version vs appVersion

| Поле | Значення | Що означає для цього проєкту |
|---|---|---|
| `version` | `0.4.0` | Версія **чарта** (шаблонів). Змінюється, коли змінюються шаблони/values, навіть якщо код застосунку той самий. Наприклад, додали Ingress-шаблон → `0.4.0 → 0.5.0`. |
| `appVersion` | `1.0.0` | Версія **застосунку**, яку чарт розгортає за замовчуванням. Використовується як тег образу, якщо `api.image.tag` / `web.image.tag` порожні. Новий реліз коду `1.1.0` без змін у чарті → змінюється лише `appVersion` (або тег у values). |

## Встановлення

```bash
# dev (значення за замовчуванням + values-dev.yaml)
helm install taskboard charts/taskboard -n taskboard-dev --create-namespace -f charts/taskboard/values-dev.yaml

# prod
helm install taskboard charts/taskboard -n taskboard-prod --create-namespace \
  -f charts/taskboard/values-prod.yaml --set postgres.auth.password='<пароль>'

# перевірка
helm test taskboard -n taskboard-dev --logs
```

Різниця між середовищами без встановлення:

```bash
diff <(helm template taskboard charts/taskboard -f charts/taskboard/values-dev.yaml) \
     <(helm template taskboard charts/taskboard -f charts/taskboard/values-prod.yaml)
```

## Пріоритет значень

Від найнижчого до найвищого (кожне наступне перекриває попереднє):

1. `values.yaml` у чарті (значення за замовчуванням = dev);
2. файли `-f` / `--values` — у порядку, в якому вказані (`-f a.yaml -f b.yaml` → `b` перемагає);
3. `--set`, `--set-string`, `--set-file` — найвищий пріоритет.

Під час `helm upgrade` без `--reuse-values` значення попереднього релізу **не** зберігаються — беруться лише з чарта + переданих `-f`/`--set`.

## Паролі

Пароль БД у файлах значень не зберігається (`postgres.auth.password: ""`). Варіанти:

- `--set postgres.auth.password=...`;
- `postgres.auth.existingSecret=<secret>` — секрет з ключами `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (так робить GitOps-конфігурація ЛР-5);
- нічого не задано → генерується випадковий пароль; при оновленнях він береться з існуючого секрету через `lookup`.

## Параметри

| Параметр | Опис | За замовчуванням (dev) | dev | prod |
|---|---|---|---|---|
| `api.image.repository` | Репозиторій образу API | `ghcr.io/davlicha/taskboard-api` | | |
| `api.image.tag` | Тег образу API (порожньо → `appVersion`) | `""` → `1.0.0` | `1.1.0` | `1.0.0` |
| `api.replicaCount` | Кількість реплік API | `1` | `1` | `3` |
| `api.service.type` / `.port` | Тип і порт сервісу API | `ClusterIP` / `8000` | | |
| `api.resources` | requests/limits API | `50m/96Mi` → `500m/256Mi` | `50m/96Mi` → `300m/192Mi` | `200m/192Mi` → `1/512Mi` |
| `api.config.APP_ENV` | Назва середовища (ConfigMap) | `dev` | `dev` | `prod` |
| `api.config.LOG_LEVEL` | Рівень логування | `DEBUG` | `DEBUG` | `WARNING` |
| `api.config.APP_NAME` | Ім'я застосунку | `taskboard-api` | | |
| `api.failRate` | Частка запитів `/api/*` з відповіддю 500 (ЛР-7) | `"0"` | | |
| `api.slowMs` | Штучна затримка `/api/*`, мс (ЛР-7) | `"0"` | | |
| `api.rollout.enabled` | Rollout (Argo Rollouts) замість Deployment (ЛР-6) | `false` | | |
| `api.rollout.replicas` | Репліки Rollout | `4` | | |
| `api.rollout.canary.steps` | Кроки canary (`{analysis: {}}` → AnalysisTemplate) | 25% → pause → 50% → 30s → 75% → 30s | | |
| `web.image.repository` / `.tag` | Образ веб-інтерфейсу | `ghcr.io/davlicha/taskboard-web` / `""` | `1.1.0` | `1.0.0` |
| `web.replicaCount` | Репліки web | `1` | `1` | `2` |
| `web.service.type` / `.port` / `.nodePort` | Сервіс web | `NodePort` / `80` / `null` | | `ClusterIP` |
| `web.resources` | requests/limits web | `50m/64Mi` → `300m/192Mi` | | `100m/128Mi` → `500m/256Mi` |
| `web.config.APP_TITLE` | Заголовок сторінки | `Taskboard (dev)` | | `Taskboard` |
| `web.config.API_TIMEOUT` | Таймаут звернень до API, с | `"3"` | | |
| `postgres.enabled` | Розгортати PostgreSQL | `true` | | |
| `postgres.image` | Образ БД | `postgres:16-alpine` | | |
| `postgres.auth.username` / `.database` | Користувач і БД | `taskboard` / `taskboard` | | |
| `postgres.auth.password` | Пароль (не зберігати у файлах!) | `""` (генерується) | | `--set` |
| `postgres.auth.existingSecret` | Готовий секрет з обліковими даними | `""` | | |
| `postgres.persistence.enabled` / `.size` / `.storageClass` | PVC для БД | `true` / `1Gi` / `""` | | |
| `postgres.resources` | requests/limits БД | `100m/128Mi` → `500m/512Mi` | | `250m/256Mi` → `1/1Gi` |
| `ingress.enabled` | Створювати Ingress | `false` | `false` | `true` |
| `ingress.className` / `.host` / `.annotations` | Параметри Ingress | `nginx` / `taskboard.local` / `{}` | | |
| `hooks.preUpgrade.enabled` | pre-upgrade Job: перевірка доступності БД | `true` | | |
| `metrics.serviceMonitor.enabled` | ServiceMonitor для Prometheus (ЛР-7) | `false` | | |
| `metrics.prometheusRule.enabled` | Алерт на частку 5xx > 5% (ЛР-7) | `false` | | |
| `metrics.dashboard.enabled` | ConfigMap з дашбордом Grafana (ЛР-7) | `false` | | |
| `analysis.enabled` | AnalysisTemplate (поріг `successRate`) (ЛР-7) | `false` | | |
| `analysis.successRate` | Мінімальна частка успішних запитів | `0.95` | | |
| `analysis.initialDelay` / `.interval` / `.count` / `.failureLimit` | Параметри вимірювань | `30s` / `30s` / `4` / `1` | | |
| `analysis.prometheusAddress` | Адреса Prometheus | `http://kube-prometheus-stack-prometheus.monitoring.svc:9090` | | |
| `nameOverride` / `fullnameOverride` | Перевизначення імен | `""` | | |
| `imagePullSecrets` | Секрети для приватного реєстру | `[]` | | |

## Шаблони

| Файл | Об'єкт |
|---|---|
| `_helpers.tpl` | `taskboard.fullname`, `taskboard.componentName`, `taskboard.labels`, `taskboard.selectorLabels`, `taskboard.image`, спільний шаблон пода API |
| `api-deployment.yaml` / `api-rollout.yaml` | Deployment або Rollout API |
| `api-service.yaml`, `api-configmap.yaml` | Service, ConfigMap API |
| `web-deployment.yaml`, `web-service.yaml`, `web-configmap.yaml` | web |
| `postgres-deployment.yaml`, `postgres-service.yaml`, `postgres-pvc.yaml`, `db-secret.yaml` | БД |
| `ingress.yaml` | Ingress (за прапорцем) |
| `hook-pre-upgrade.yaml` | Helm-хук `pre-upgrade` |
| `tests/test-connection.yaml` | `helm test` |
| `servicemonitor.yaml`, `prometheusrule.yaml`, `dashboard-configmap.yaml`, `analysistemplate.yaml` | ЛР-7 |
| `NOTES.txt` | Підказка після встановлення |
