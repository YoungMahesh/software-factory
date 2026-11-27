#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker is required." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] 'docker compose' (V2) plugin is required." >&2
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "[ERROR] Missing ${SCRIPT_DIR}/.env (SANDBOX_CONTROL_PLANE_URL, WEB_UI_USERNAME, WEB_UI_PASSWORD)." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

CONTAINER_NAME="${DASHBOARD_CONTAINER_NAME:-sandbox-dashboard-web}"
COMPOSE_PROJECT="${DASHBOARD_COMPOSE_PROJECT:-sandbox-dashboard}"

if ! docker network inspect dbhost-network >/dev/null 2>&1; then
  docker network create dbhost-network >/dev/null 2>&1 || true
fi

docker compose -p "${COMPOSE_PROJECT}" -f docker-compose.prod.yml up -d --build

for _ in $(seq 1 45); do
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
  if [ "${status}" = "healthy" ]; then
    echo "${CONTAINER_NAME} is healthy."
    exit 0
  fi
  sleep 1
done

docker compose -p "${COMPOSE_PROJECT}" -f docker-compose.prod.yml logs --tail=40 web >&2 || true
echo "[ERROR] ${CONTAINER_NAME} failed health check." >&2
exit 1
