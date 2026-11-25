# ЛР-6. Progressive delivery: canary з Argo Rollouts

## 1. Контролер через Argo CD

`argocd-apps/argo-rollouts.yaml` — Application для Helm-чарту `argo-rollouts` (2.43.12) з `argoproj.github.io/argo-helm`,
з увімкненим dashboard. Підхоплюється кореневим Application автоматично.

```bash
brew install argoproj/tap/kubectl-argo-rollouts
kubectl argo rollouts version
```

## 2. Rollout у чарті

`charts/taskboard/templates/api-rollout.yaml` рендериться, коли `api.rollout.enabled: true`; тоді `api-deployment.yaml`
не рендериться. Шаблон пода спільний (`taskboard.api.podTemplate` у `_helpers.tpl`). Репліки — `api.rollout.replicas: 4`.

## 3. Стратегія — canary

```yaml
# values-minikube.yaml
steps:
  - setWeight: 25        # 1 з 4 подів — нова версія
  - analysis: {}         # ЛР-7: перевірка Prometheus
  - pause: {}            # ручна пауза -> promote
  - setWeight: 50
  - pause: { duration: 30s }
  - setWeight: 75
  - pause: { duration: 30s }
```

**Чому canary**: API — stateless-сервіс за одним Service; canary без traffic-router-а розподіляє трафік пропорційно
кількості подів, тому частина реальних запитів одразу йде на нову версію — це дає метрики для автоматичного аналізу (ЛР-7).
Blue-green потребував би подвоєння ресурсів (8 подів у minikube) і перевіряє preview без реального трафіку.
Схема БД між версіями сумісна, тож одночасна робота двох версій безпечна.

## 4. Реліз через Git

```bash
kubectl apply -f tools/loadgen.yaml            # цикл запитів усередині кластера, друкує версію
sed -i '' 's/tag: "1.0.0"/tag: "1.1.0"/' charts/taskboard/values-minikube.yaml
git commit -am "canary api 1.1.0" && git push
kubectl argo rollouts get rollout taskboard-api -n taskboard --watch
```

Проміжний стан (крок 3/7, пауза):

```
Status:  ॥ Paused   Message: CanaryPauseStep
Step:    3/7        SetWeight: 25   ActualWeight: 25
├──# revision:2  canary  1 pod   1.1.0
└──# revision:1  stable  3 pods  1.0.0
```

Відповіді обох версій:

```bash
kubectl -n taskboard logs deploy/loadgen --tail=40 | awk '{print $3}' | sort | uniq -c
#   30 version=1.0.0
#   10 version=1.1.0
kubectl argo rollouts promote taskboard-api -n taskboard
```

Перевірено на minikube (див. [ЛР-7, «Перевірка»](lab07.md#перевірка-на-minikube)): хороший реліз зупиняється на ручній паузі з 1 canary і 3 stable подами.

Також видно в UI Argo CD (Rollout → ReplicaSets) і в дашборді: `kubectl argo rollouts dashboard` → http://localhost:3100.

## 5. Скасування

```bash
sed -i '' 's/tag: "1.1.0"/tag: "1.2.0"/' charts/taskboard/values-minikube.yaml && git commit -am "release 1.2.0" && git push
# на паузі:
kubectl argo rollouts abort taskboard-api -n taskboard
kubectl argo rollouts get rollout taskboard-api -n taskboard   # Status: ✖ Degraded, усі 4 поди — stable
argocd app get taskboard                                       # Synced / Degraded
```

**Чому Synced + Degraded**: у Git — тег 1.2.0, у Rollout spec — теж 1.2.0 → Argo CD бачить відповідність (*Synced*).
Але контролер Rollouts скасував реліз і тримає stable-ReplicaSet; health-check Argo CD для Rollout повертає *Degraded*
(«RolloutAborted»), бо бажаний стан не досягнуто.

Завершення відкату — через Git (джерело правди):

```bash
git revert --no-edit HEAD && git push    # тег знову 1.1.0 == stable -> Rollout Healthy без нового розгортання
```

## 6. Захист — чек-лист

1. Commit з новим тегом → Argo CD синхронізує → Rollout крок 25%.
2. `kubectl argo rollouts get rollout ... --watch` + loadgen показує обидві версії.
3. `promote` → 50% → 75% → 100%.
4. Новий реліз → `abort` → Synced/Degraded → `git revert`.
