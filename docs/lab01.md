# ЛР-1. Віртуалізація та контейнеризація

## 1. Проєкт

**Taskboard** — менеджер задач із двох сервісів і бази даних:

| Вимога | Як виконано |
|---|---|
| a. Будь-яка мова | Python 3.12 |
| b. Веб-застосунок з БД | `web` (Flask, HTML) → `api` (FastAPI, REST) → PostgreSQL |
| c. Тести | `services/api/tests` (pytest + TestClient, SQLite), `services/web/tests` (pytest, мок API) |
| d. Кілька частин | 2 сервіси, кожен зі своїм Dockerfile, CI-job, Deployment |

API: `GET/POST /api/tasks`, `GET/PUT/DELETE /api/tasks/{id}`, `/health`, `/livez`, `/version`, `/metrics`.

## 2. Dockerfile

`services/api/Dockerfile`, `services/web/Dockerfile`:

- **multi-stage**: на стадії `build` залежності ставляться у venv, у фінальний образ копіюється лише venv + код;
- `python:3.12-slim`, запуск від непривілейованого користувача (`USER 10001`);
- `ARG APP_VERSION` → `ENV APP_VERSION` — версія вшивається в образ і повертається з `/version`;
- `HEALTHCHECK`, `.dockerignore` (тести й кеші не потрапляють в образ).

```bash
docker build -t taskboard-api:1.0.0 --build-arg APP_VERSION=1.0.0 services/api
docker build -t taskboard-web:1.0.0 --build-arg APP_VERSION=1.0.0 services/web
```

## 3. docker-compose

`docker-compose.yml` піднімає `db` → `api` → `web`. Порядок старту гарантується `depends_on: condition: service_healthy`
(healthcheck `pg_isready` у БД, HEALTHCHECK в образі API). Дані БД — у томі `pgdata`. Облікові дані — з `.env`
(шаблон `.env.example`, сам `.env` у `.gitignore`).

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
curl localhost:8000/health
curl -X POST localhost:8000/api/tasks -H 'content-type: application/json' -d '{"title":"Lab1 works"}'
open http://localhost:8080
```

Результат перевірки:

```
{"status":"ok","db":"ok","version":"1.0.0","env":"compose","instance":"65600a79f065"}
{"title":"Lab1 works","done":false,"id":1}
api Up (healthy) · db Up (healthy) · web Up (healthy)
```

Тести (в контейнері з тим самим Python, що в образі):

```
api: 7 passed      web: 4 passed      ruff: All checks passed!
```

## 4. GitHub

```bash
git remote add origin https://github.com/davlicha/taskboard.git
git push -u origin main
```
