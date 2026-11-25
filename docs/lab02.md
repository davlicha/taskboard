# ЛР-2. Continuous Integration

Інструмент — **GitHub Actions**, файл `.github/workflows/ci.yml`. Реєстр — **GHCR** (`ghcr.io/davlicha/taskboard-{api,web}`).

## 1. Запуск

```yaml
on:
  push: { branches: [main], tags: ["v*"] }
  pull_request: { branches: [main] }
```

Статуси jobs автоматично показуються в PR (Checks).

## 2–3. Збірка, лінт, тести

Job `build-test` з `matrix.service: [api, web]`, `fail-fast: false` — сервіси перевіряються паралельно й незалежно.

| Крок | Команда |
|---|---|
| Кеш | `actions/setup-python` з `cache: pip` (ключ — хеш `requirements*.txt`) |
| **Lint** (блокуючий) | `ruff check --output-format=github .` + `ruff format --check .` — порушення з'являються анотаціями прямо в diff PR |
| **Build** | `python -m compileall -q app` |
| **Test** | `pytest -v --junitxml=test-results.xml` (звіт — артефакт) |

## 4. Образи

Job `image` має `needs: build-test` — запускається лише після успіху **всіх** build/test jobs.

1. `docker/build-push-action` з `load: true, push: false` — образ збирається локально на раннері (кеш шарів `type=gha`);
2. **Grype** (`anchore/scan-action`, `fail-build: true`, `severity-cutoff: critical`, `only-fixed: true`) — блокуючий крок перед публікацією.

> Trivy свідомо не використано: у 2026 р. теги `aquasecurity/trivy-action` були скомпрометовані (supply-chain атака).

## 5. Публікація

- `docker/login-action` з `secrets.GITHUB_TOKEN` (облікові дані не зберігаються в репозиторії; `permissions: packages: write`);
- крок `Push image` має `if: github.event_name == 'push'` — для PR образи не публікуються;
- теги (`docker/metadata-action`):
  - `sha-<7 символів>` і `run-<номер>` — унікальні теги збірки;
  - `latest` — лише для `main`;
  - `1.0.0` — для git-тегів `v1.0.0` (потрібні в ЛР-3…7).

Перевірка:

```bash
docker pull ghcr.io/davlicha/taskboard-api:latest
docker run --rm -p 8000:8000 ghcr.io/davlicha/taskboard-api:latest &
curl localhost:8000/version
```

> Після першої публікації в GitHub → Packages → `taskboard-api` / `taskboard-web` → Package settings → Change visibility → **Public**, щоб minikube міг тягнути образи без секрету.

## 6. Захист main

Після першого прогону CI:

```bash
./scripts/protect-main.sh davlicha/taskboard
```

Скрипт вмикає: обов'язковий PR, `enforce_admins`, required status checks
`api · lint, build, test`, `web · lint, build, test`, `api · docker image`, `web · docker image` (strict — гілка має бути актуальною).

Демонстрація заблокованого PR:

```bash
git switch -c broken-test
sed -i '' 's/assert body\["status"\] == "ok"/assert body["status"] == "broken"/' services/api/tests/test_api.py
git commit -am "break test" && git push -u origin broken-test
gh pr create --fill
# у PR: job "api · lint, build, test" червоний, "web" — зелений (fail-fast: false), Merge заблоковано
```
