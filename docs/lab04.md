# ЛР-4. Пакування застосунку в Helm-чарт

Чарт: [`charts/taskboard`](../charts/taskboard) · опис параметрів: [README чарта](../charts/taskboard/README.md) ·
повний вивід: [`evidence/lab04-output.txt`](evidence/lab04-output.txt).

## 1. Середовище

```bash
brew install helm && helm version --short        # v3.x/v4.x
minikube start --driver=docker
kubectl apply -f k8s/ && kubectl -n taskboard get pods   # ЛР-3 працює
kubectl delete -f k8s/                                    # прибираємо, щоб не було конфлікту імен
```

## 2–5. Структура чарта

```
charts/taskboard/
├── Chart.yaml            # name, description, version 0.4.0, appVersion 1.0.0
├── values.yaml           # dev за замовчуванням
├── values-dev.yaml
├── values-prod.yaml
├── values-minikube.yaml  # для Argo CD (ЛР-5…7)
├── dashboards/taskboard.json
└── templates/
    ├── _helpers.tpl      # fullname, componentName, labels, selectorLabels, image, pod template API
    ├── NOTES.txt
    ├── api-{deployment,service,configmap}.yaml
    ├── web-{deployment,service,configmap}.yaml
    ├── postgres-{deployment,service,pvc}.yaml, db-secret.yaml
    ├── ingress.yaml                          # ingress.enabled
    ├── hook-pre-upgrade.yaml                 # п.9b
    └── tests/test-connection.yaml            # п.9b
```

- **Імена** — `{{ include "taskboard.componentName" (dict "root" . "component" "api") }}` → `<release>-taskboard-api`
  (або `<release>-api`, якщо ім'я релізу вже містить `taskboard`). Перевірено: релізи `taskboard` і `second` одночасно в одному namespace.
- **Мітки** — `include "taskboard.labels"` / `"taskboard.selectorLabels"` в усіх маніфестах.
- **Secret** — значення з `.Values.postgres.auth.*`; пароль не зберігається у файлах значень (`--set`, `existingSecret` або автогенерація з `lookup`).
- **Прапорці** — `ingress.enabled`, `postgres.persistence.enabled`.
- **checksum/config** — анотація з хешем ConfigMap: зміна конфігурації перезапускає поди.

## 6. Два середовища

| | dev | prod |
|---|---|---|
| `api.replicaCount` / `web.replicaCount` | 1 / 1 | 3 / 2 |
| `api.image.tag` | 1.1.0 | 1.0.0 |
| `api.resources` | 50m/96Mi → 300m/192Mi | 200m/192Mi → 1/512Mi |
| `ingress.enabled` | false | true |
| `LOG_LEVEL` | DEBUG | WARNING |

Різниця без встановлення:

```bash
diff <(helm template taskboard charts/taskboard -f charts/taskboard/values-dev.yaml) \
     <(helm template taskboard charts/taskboard -f charts/taskboard/values-prod.yaml)
```

**Пріоритет**: `values.yaml` < `-f` файли (останній перемагає) < `--set`. Детально — у README чарта.

## 7. Перевірка й встановлення

```bash
helm lint charts/taskboard -f charts/taskboard/values-prod.yaml      # 0 chart(s) failed
helm template taskboard charts/taskboard | kubeconform -strict -summary   # Valid: 12, Invalid: 0
helm install taskboard charts/taskboard -n taskboard-lab4 --create-namespace --wait
helm list -n taskboard-lab4
helm status taskboard -n taskboard-lab4
helm get values taskboard -n taskboard-lab4 --all
```

Порівняння з ЛР-3: ті самі Deployment (api, web, postgres), Service ×3, ConfigMap ×2, Secret, PVC, Ingress; відмінності —
імена з префіксом релізу, стандартні мітки `app.kubernetes.io/*`, секрет БД один замість двох (DATABASE_URL збирається з його ключів).

**Де Helm зберігає стан релізу** — у Secret типу `helm.sh/release.v1` у namespace релізу, по одному на ревізію:

```
$ kubectl -n taskboard-lab4 get secrets -l owner=helm
sh.helm.release.v1.taskboard.v1   helm.sh/release.v1   ... name=taskboard,owner=helm,status=deployed,version=1
```

Усередині — gzip+base64 маніфест релізу, values і метадані.

## 8. Життєвий цикл

```bash
helm upgrade taskboard charts/taskboard -n taskboard-lab4 --reuse-values --set api.image.tag=1.1.0 --wait   # rev 2
helm upgrade taskboard charts/taskboard -n taskboard-lab4 -f charts/taskboard/values-prod.yaml --wait       # rev 3
helm history taskboard -n taskboard-lab4
helm rollback taskboard 2 -n taskboard-lab4 --wait                                                         # rev 4
helm history taskboard -n taskboard-lab4
helm uninstall taskboard -n taskboard-lab4
kubectl -n taskboard-lab4 get all,pvc,secret,configmap,ingress   # лише kube-root-ca.crt
```

```
REVISION  STATUS      DESCRIPTION
1         superseded  Install complete          # dev, api 1.0.0
2         superseded  Upgrade complete          # --set api.image.tag=1.1.0
3         superseded  Upgrade complete          # values-prod: 3/2 репліки, ресурси, Ingress, тег 1.0.0
4         deployed    Rollback to 2             # знову 1 репліка, api 1.1.0
```

Відкат не «стирає» історію — створюється нова ревізія 4 з конфігурацією ревізії 2.

> Знахідка під час виконання: перша версія `values-prod.yaml` збільшувала PVC до 5Gi — upgrade падав
> (`only dynamically provisioned pvc can be resized`), ревізія отримувала статус `failed`. Розмір PVC тепер однаковий для середовищ.

## 9. Варіант b — хук і тест

- `hook-pre-upgrade.yaml` — Job з анотацією `helm.sh/hook: pre-upgrade`: перед кожним upgrade перевіряє `pg_isready` до БД; якщо БД недоступна — upgrade скасовується.
  `hook-delete-policy: before-hook-creation,hook-succeeded`.
- `tests/test-connection.yaml` — под з `helm.sh/hook: test`, перевіряє `/health` API і головну сторінку web.

```
$ helm test taskboard -n taskboard-lab4 --logs
TEST SUITE:     taskboard-test
Phase:          Succeeded
POD LOGS: taskboard-test (curl)
{"status":"ok","db":"ok","version":"1.0.0","env":"prod","instance":"taskboard-api-5765b796c-kqlm4"}
web: 200
```
