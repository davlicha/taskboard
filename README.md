# Taskboard — лабораторні роботи з дисципліни «Технології DevOps»

Навчальний мікросервісний проєкт, на якому виконано всі 10 лабораторних робіт.

```
            ┌──────────┐   HTTP    ┌──────────┐   SQL   ┌────────────┐
browser ──▶ │   web    │ ────────▶ │   api    │ ──────▶ │ PostgreSQL │
            │ (Flask)  │           │(FastAPI) │         │            │
            └──────────┘           └──────────┘         └────────────┘
                                   /health /version /metrics, JSON-логи
```

| Сервіс | Стек | Тести | Порт |
|---|---|---|---|
| `services/api` | Python 3.12, FastAPI, SQLAlchemy, prometheus-client | pytest (7 тестів: CRUD, health, metrics, FAIL_RATE) | 8000 |
| `services/web` | Python 3.12, Flask, gunicorn | pytest (4 тести з моком API) | 8080 |
| PostgreSQL | postgres:16-alpine | — | 5432 |

## Структура репозиторію

| Шлях | Лабораторна | Що там |
|---|---|---|
| `services/*/Dockerfile`, `docker-compose.yml` | №1 | Multi-stage образи, весь проєкт однією командою |
| `.github/workflows/ci.yml`, `scripts/protect-main.sh` | №2 | CI: lint → build → test (matrix), образи, Grype, GHCR, захист гілки |
| `k8s/` | №3 | Маніфести Kubernetes, по одному файлу на об'єкт |
| `charts/taskboard/` | №4 | Helm-чарт, `values-dev.yaml`, `values-prod.yaml`, хук і `helm test` |
| `bootstrap/`, `argocd-apps/`, `charts/taskboard/values-minikube.yaml` | №5 | GitOps з Argo CD (App of Apps) |
| `charts/taskboard/templates/api-rollout.yaml`, `argocd-apps/argo-rollouts.yaml` | №6 | Canary через Argo Rollouts |
| `argocd-apps/{kube-prometheus-stack,loki,alloy}.yaml`, `templates/{servicemonitor,analysistemplate,prometheusrule,dashboard-configmap}.yaml` | №7 | Метрики, логи, дашборд, автоматичний відкат |
| `labs/lab08-serverless/` | №8 | Lambda + DynamoDB + API Gateway у LocalStack |
| `labs/lab09-load-balancing/` | №9 | 3 екземпляри + nginx |
| `labs/lab10-cloudwatch/` | №10 | CloudWatch метрики, alarms, графіки |
| `docs/` | всі | Звіти до кожної лабораторної, `docs/evidence/` — збережений вивід команд |

## Швидкий старт

```bash
cp .env.example .env
docker compose up --build
```

- UI: http://localhost:8080
- API: http://localhost:8000/docs, http://localhost:8000/health

## Звіти

- [ЛР-1. Віртуалізація та контейнеризація](docs/lab01.md)
- [ЛР-2. Continuous Integration](docs/lab02.md)
- [ЛР-3. Розгортання в Kubernetes](docs/lab03.md)
- [ЛР-4. Helm-чарт](docs/lab04.md) · [README чарта](charts/taskboard/README.md)
- [ЛР-5. GitOps з Argo CD](docs/lab05.md)
- [ЛР-6. Progressive delivery (canary)](docs/lab06.md)
- [ЛР-7. Observability і відкат за метриками](docs/lab07.md)
- [ЛР-8. Serverless у LocalStack](docs/lab08.md)
- [ЛР-9. Балансування навантаження](docs/lab09.md)
- [ЛР-10. Моніторинг у CloudWatch](docs/lab10.md)

## Необхідні інструменти

Docker Desktop, `kubectl`, `minikube`, `helm`, `argocd`, `kubectl-argo-rollouts`, `aws` (AWS CLI), Python 3.12.

```bash
brew install minikube helm argocd awscli argoproj/tap/kubectl-argo-rollouts
```
