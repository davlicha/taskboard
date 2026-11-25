# ЛР-5. GitOps: розгортання через Argo CD

## 1. Репозиторій конфігурації — варіант b (каталоги в репозиторії застосунку)

```
bootstrap/
├── install.sh          # minikube + addons + Argo CD + секрети + root app
├── create-secrets.sh   # секрети БД і Grafana створюються поза Git
└── root-app.yaml       # кореневий Application (App of Apps) — єдиний, що застосовується вручну
argocd-apps/
├── taskboard.yaml      # чарт charts/taskboard + values-minikube.yaml
├── argo-rollouts.yaml  # ЛР-6
├── kube-prometheus-stack.yaml, loki.yaml, alloy.yaml   # ЛР-7
charts/taskboard/       # чарт з ЛР-4
└── values-minikube.yaml
```

Паролі не в Git: `values-minikube.yaml` посилається на `postgres.auth.existingSecret: taskboard-db`, а сам секрет
створює `bootstrap/create-secrets.sh` (випадковий пароль). Helm-хук `pre-upgrade` для Argo CD вимкнено:
Argo CD трактує його як `PreSync`, і на першій синхронізації БД ще не існує.

## 2. Образ і версія

CI (ЛР-2) публікує `ghcr.io/davlicha/taskboard-api:<версія>` з git-тегів:

```bash
git tag v1.0.0 && git push origin v1.0.0     # -> образи :1.0.0
```

Пакети в GHCR зробити **Public** — тоді minikube тягне їх без `minikube image load`.
Версію показують: `GET /version`, поле `version` у `/health`, рядок «web X · api Y» на сторінці.

## 3. Argo CD

```bash
./bootstrap/install.sh            # або покроково:
kubectl create namespace argocd
kubectl apply -n argocd --server-side -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
kubectl -n argocd port-forward svc/argocd-server 8443:443
argocd login localhost:8443 --username admin --insecure
argocd account update-password
```

Якщо репозиторій приватний: `argocd repo add https://github.com/davlicha/taskboard.git --username davlicha --password <PAT>`.

## 4. App of Apps

```bash
./bootstrap/create-secrets.sh
kubectl apply -n argocd -f bootstrap/root-app.yaml
argocd app list
argocd app get taskboard
```

`root` синхронізує каталог `argocd-apps/` → створює Application `taskboard` (і контролери з ЛР-6/7) →
кожен Application синхронізує свій чарт. В UI: дерево Rollout → ReplicaSet → Pod, Service, PVC, Ingress… у стані **Synced / Healthy**.
`sync-wave` гарантує, що контролери (`0`) і Alloy (`1`) встановлюються раніше за застосунок (`10`).

## 5. Оновлення через Git

```bash
sed -i '' 's/tag: "1.0.0"/tag: "1.1.0"/' charts/taskboard/values-minikube.yaml   # api.image.tag
git commit -am "release api 1.1.0" && git push
argocd app get taskboard --refresh     # або чекати polling (3 хв)
kubectl -n taskboard run v --rm -i --restart=Never --image=curlimages/curl:8.11.1 -- curl -s taskboard-api:8000/version
# {"version":"1.1.0",...}
```

> Якщо `api.rollout.enabled: true` (ЛР-6), реліз зупиниться на ручній паузі canary — для чистої демонстрації ЛР-5
> можна тимчасово поставити `rollout.enabled: false` (тоді працює звичайний Deployment).

## 6. Дрейф, Health, відкат

**a) selfHeal**

```bash
# 1) у argocd-apps/taskboard.yaml: selfHeal: false -> commit/push
kubectl -n taskboard scale deploy/taskboard-web --replicas=3
argocd app get taskboard            # Sync Status: OutOfSync (replicas 3 ≠ 1 у Git)
argocd app diff taskboard
# 2) повертаємо selfHeal: true -> commit/push
kubectl -n taskboard scale deploy/taskboard-web --replicas=3
kubectl -n taskboard get deploy taskboard-web -w     # Argo CD за кілька секунд повертає 1
```

**b) Synced + Degraded**

```bash
sed -i '' 's/tag: "1.1.0"/tag: "9.9.9"/' charts/taskboard/values-minikube.yaml
git commit -am "broken tag" && git push
argocd app get taskboard   # Sync: Synced (кластер = Git), Health: Degraded (под у ImagePullBackOff)
```

`Synced` означає «кластер відповідає Git», `Healthy/Degraded` — «чи працюють об'єкти». Неправильний стан у Git синхронізується «успішно», але застосунок не здоровий.

**c) git revert**

```bash
git revert --no-edit HEAD && git push
git log --oneline -5
argocd app history taskboard
```
