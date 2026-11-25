#!/usr/bin/env bash
# Повне розгортання з нуля: minikube -> Argo CD -> root Application.
set -euo pipefail
cd "$(dirname "$0")/.."

minikube status >/dev/null 2>&1 || minikube start --driver=docker --cpus=4 --memory=8g
minikube addons enable ingress
minikube addons enable metrics-server

kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server --timeout=300s

./bootstrap/create-secrets.sh
kubectl apply -n argocd -f bootstrap/root-app.yaml

echo
echo "Початковий пароль admin:"
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
echo "UI: kubectl -n argocd port-forward svc/argocd-server 8443:443  ->  https://localhost:8443"
