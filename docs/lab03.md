# ЛР-3. Розгортання застосунку в Kubernetes

Повний збережений вивід усіх команд: [`evidence/lab03-output.txt`](evidence/lab03-output.txt) (виконано на minikube v1.3x, драйвер docker).

## 1. Образи

Образи `ghcr.io/davlicha/taskboard-api` і `taskboard-web` з тегами **1.0.0** та **1.1.0** публікує CI (ЛР-2) з git-тегів `v1.0.0`, `v1.1.0`.
Тег `latest` у маніфестах не використовується. Альтернатива без реєстру:

```bash
docker build -t ghcr.io/davlicha/taskboard-api:1.1.0 --build-arg APP_VERSION=1.1.0 services/api
minikube image load ghcr.io/davlicha/taskboard-api:1.1.0
```

## 2. Кластер

```bash
minikube start --driver=docker --cpus=4 --memory=6g
kubectl get nodes
kubectl -n kube-system get pods
minikube addons enable metrics-server
minikube addons enable ingress
```

## 3–4. Namespace і маніфести (`k8s/`, по одному файлу на об'єкт)

| Файл | Об'єкт | Ключове |
|---|---|---|
| `00-namespace.yaml` | Namespace `taskboard` | ім'я проєкту; `00-` — щоб створювався першим |
| `api-deployment.yaml` | Deployment API | 2 репліки, labels = selector, requests/limits, readiness `/health` (з перевіркою БД), liveness `/livez`, `maxUnavailable: 0`, `preStop: sleep 5` |
| `api-service.yaml` | Service ClusterIP :8000 | доступ усередині кластера |
| `api-configmap.yaml` | ConfigMap | `APP_ENV`, `LOG_LEVEL`, `APP_NAME` → `envFrom` |
| `api-secret.yaml` | Secret | `DATABASE_URL` (рядок підключення) |
| `web-deployment.yaml`, `web-configmap.yaml` | web | `API_URL`, `APP_TITLE`, `API_TIMEOUT` |
| `web-service.yaml` | Service **NodePort 30080** | доступ з хоста |
| `ingress.yaml` | Ingress `taskboard.local` | `/` → web, `/api`, `/version` → api |
| `db-deployment.yaml`, `db-service.yaml` | PostgreSQL | `strategy: Recreate` (RWO-том) |
| `db-secret.yaml` | Secret | `POSTGRES_USER/PASSWORD/DB` (навчальний пароль) |
| `db-pvc.yaml` | PersistentVolumeClaim 1Gi | дані БД переживають перезапуск пода |

## 5. Розгортання однією командою

```bash
kubectl apply -f k8s/
kubectl -n taskboard get pods,deploy,rs,svc,pvc,ingress
minikube service web -n taskboard          # або http://taskboard.local через minikube tunnel
```

> На щойно створеному кластері admission-webhook ingress-nginx готовий не одразу; якщо `ingress.yaml` повернув
> `connection refused` — повторити `kubectl apply -f k8s/` через 20–30 с.

ConfigMap і Secret у контейнері:

```bash
kubectl -n taskboard exec deploy/api -- printenv APP_ENV LOG_LEVEL APP_NAME
# minikube  INFO  taskboard-api
kubectl -n taskboard exec deploy/api -- python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
# {"status":"ok","db":"ok","version":"1.0.0","env":"minikube",...}
```

## 6. Життєвий цикл

**a) Самовідновлення**

```bash
kubectl -n taskboard delete pod <api-pod>
kubectl -n taskboard get pods -l app.kubernetes.io/name=api     # новий под з AGE кілька секунд
```

**b) Масштабування і розподіл трафіку**

```bash
kubectl -n taskboard scale deploy/api --replicas=4
kubectl -n taskboard run curl --rm -i --restart=Never --image=curlimages/curl:8.11.1 -- \
  sh -c 'for i in $(seq 1 20); do curl -s http://api:8000/version; echo; done' | sort | uniq -c
```
```
   5 {"version":"1.0.0","instance":"api-758cd668cf-f2wnr"}
   4 {"version":"1.0.0","instance":"api-758cd668cf-qmbng"}
   4 {"version":"1.0.0","instance":"api-758cd668cf-s2g8j"}
   3 {"version":"1.0.0","instance":"api-758cd668cf-tj9q7"}
```

**c, e) Rolling update з перевіркою доступності**

```bash
kubectl -n taskboard set image deploy/api api=ghcr.io/davlicha/taskboard-api:1.1.0
kubectl -n taskboard annotate deploy/api kubernetes.io/change-cause="api 1.1.0" --overwrite
kubectl -n taskboard rollout status deploy/api
```

Паралельно под-зонд робив запит кожні 0,25 с:
`availability during update (with preStop): ok=140 fail=0` — завдяки `maxUnavailable: 0`, readiness-пробі та `preStop`
застосунок весь час доступний. Без `preStop` спостерігали 1 невдалий запит із 120 (под ще в Endpoints, а процес уже зупиняється).

**d) Історія і відкат**

```
REVISION  CHANGE-CAUSE
1         api 1.0.0
2         api 1.1.0
$ kubectl -n taskboard rollout undo deploy/api
REVISION  CHANGE-CAUSE
2         api 1.1.0
3         api 1.0.0
```

## 7. Діагностика

```bash
kubectl -n taskboard set image deploy/api api=ghcr.io/davlicha/taskboard-api:9.9.9-missing
kubectl -n taskboard get pods             # новий под: ErrImagePull -> ImagePullBackOff, старі працюють (maxUnavailable: 0)
kubectl -n taskboard describe pod <pod>   # Events:
#  Warning  Failed   ... Error: ErrImagePull
#  Normal   BackOff  ... Back-off pulling image "ghcr.io/davlicha/taskboard-api:9.9.9-missing"
#  Warning  Failed   ... Error: ImagePullBackOff
kubectl -n taskboard get events --sort-by=.lastTimestamp
kubectl -n taskboard logs deploy/api --tail=20     # JSON-логи
kubectl -n taskboard exec -it deploy/api -- sh     # інтерактивний вхід
kubectl -n taskboard rollout undo deploy/api       # виправлення
```

## 8. Параметри ConfigMap і Secret

| Об'єкт | Ключ | Призначення |
|---|---|---|
| ConfigMap `api-config` | `APP_ENV` | назва середовища, повертається в `/health` |
| | `LOG_LEVEL` | рівень логування (`DEBUG`/`INFO`/`WARNING`) |
| | `APP_NAME` | ім'я застосунку (логи, OpenAPI) |
| ConfigMap `web-config` | `API_URL` | адреса API всередині кластера |
| | `APP_TITLE` | заголовок сторінки |
| | `API_TIMEOUT` | таймаут запитів до API, с |
| Secret `api-secret` | `DATABASE_URL` | рядок підключення до БД |
| Secret `db-credentials` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | облікові дані PostgreSQL |
