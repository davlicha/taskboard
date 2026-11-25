#!/usr/bin/env bash
# ЛР-2 п.6: Branch protection для main — лише через PR, обов'язкові перевірки CI.
# Запуск після першого успішного прогону CI (щоб GitHub знав назви перевірок):
#   ./scripts/protect-main.sh davlicha/taskboard
set -euo pipefail
REPO=${1:?usage: $0 owner/repo}
gh api -X PUT "repos/$REPO/branches/main/protection" --input - <<JSON
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "api · lint, build, test",
      "web · lint, build, test",
      "api · docker image",
      "web · docker image"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
echo "main protected in $REPO"
