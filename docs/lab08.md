# ЛР-8. Serverless-застосунок у LocalStack (Lambda + API Gateway + DynamoDB)

Код: [`labs/lab08-serverless`](../labs/lab08-serverless) · вивід перевірки: [`results/test-output.txt`](../labs/lab08-serverless/results/test-output.txt)

## Архітектура

```
curl ──HTTP──▶ API Gateway (REST, stage dev)
                 /items        ANY ─┐
                 /items/{id}   ANY ─┼─ AWS_PROXY ──▶ Lambda items-api (python3.12)
                 /health       ANY ─┘                  handler.py ─▶ core.py ──boto3──▶ DynamoDB table "items"
                                                                                       (PK: id, PAY_PER_REQUEST)
```

- `lambda/handler.py` — адаптер події API Gateway (proxy): `httpMethod`, `path`, `body` (+ base64) → `core.route()` → `{statusCode, headers, body}`.
- `lambda/core.py` — бізнес-логіка, незалежна від середовища (ця сама логіка використовується в контейнері ЛР-9/10).

| Метод | Шлях | Дія | Код |
|---|---|---|---|
| POST | `/items` | створити (`title` обов'язковий, `note`) | 201 / 400 |
| GET | `/items` | список | 200 |
| GET | `/items/{id}` | отримати | 200 / 404 |
| DELETE | `/items/{id}` | видалити | 200 / 404 |
| GET | `/health` | перевірка | 200 |

## 1. Встановлення

```bash
brew install awscli
cd labs/lab08-serverless
docker compose up -d          # LocalStack 4.14.0 + docker.sock (Lambda запускається в окремому контейнері)
curl localhost:4566/_localstack/health
```

> Новіші образи `localstack/localstack` (2026.x) вимагають `LOCALSTACK_AUTH_TOKEN`; 4.14.0 — остання версія,
> що працює без нього. Якщо токен є — `export LOCALSTACK_AUTH_TOKEN=...` перед `docker compose up`.

Облікові дані — фіктивні (`test`/`test`, регіон `us-east-1`), задаються в скриптах.

## 2–5, 7. Автоматизоване розгортання — `deploy.sh`

1. `dynamodb create-table` (якщо нема) + `wait table-exists`;
2. IAM-роль для Lambda;
3. zip з `handler.py` + `core.py` → `lambda create-function` / `update-function-code` → `wait function-active-v2`;
4. REST API: ресурси `/items`, `/items/{id}`, `/health`, метод `ANY`, інтеграція `AWS_PROXY`;
5. `lambda add-permission` для `apigateway.amazonaws.com`, `create-deployment --stage-name dev`.

Скрипт ідемпотентний (повторний запуск оновлює код і перестворює API).

```bash
./deploy.sh
# Базова URL API: http://localhost:4566/restapis/<id>/dev/_user_request_
```

## 6. Перевірка HTTP-клієнтом — `test.sh`

```
--- POST /items
{ "id": "219b3f50-...", "title": "Lab 8", "note": "serverless on LocalStack", "created_at": "2026-11-25T22:55:42+00:00" }
--- GET /items                 { "items": [ ... ], "count": 1 }
--- GET /items/219b3f50-...    { ... }
--- DELETE /items/219b3f50-... { "deleted": "219b3f50-..." }
--- GET /items/219b3f50-... (404)   {"error": "item not found"}  HTTP 404
--- POST /items без title (400)     {"error": "field 'title' is required"}  HTTP 400
--- DynamoDB scan                   0
```

Прибирання: `./cleanup.sh`, `docker compose down`.
