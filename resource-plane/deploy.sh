#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# DB Host Control Plane - Production Single-Command Deployment
# ==============================================================================

BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

echo -e "\n${BOLD}${CYAN}======================================================${NC}"
echo -e "${BOLD}${CYAN}   DB Host Control Plane - Production Deployment      ${NC}"
echo -e "${BOLD}${CYAN}======================================================${NC}\n"

# 1. Verify Docker Engine & Compose availability
if ! command -v docker >/dev/null 2>&1; then
  echo -e "${RED}[ERROR] Docker is not installed or not in PATH.${NC}" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo -e "${RED}[ERROR] 'docker compose' (V2) plugin is required but not found.${NC}" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo -e "${RED}[ERROR] Cannot connect to Docker daemon.${NC}" >&2
  echo -e "${YELLOW}Please ensure Docker is running and your current user has permission to /var/run/docker.sock.${NC}" >&2
  echo -e "Hint: ${BOLD}sudo usermod -aG docker \$USER${NC} (then reload your shell)\n" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

ENV_FILE=".env"
FIRST_RUN=false

# Helper for secure random hex strings
generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  else
    head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# 2. Check and generate .env if missing
if [ ! -f "${ENV_FILE}" ]; then
  FIRST_RUN=true
  echo -e "${CYAN}==> First-time setup detected. Generating secure production secrets in .env...${NC}"

  GEN_POSTGRES_PW="$(generate_secret 24)"
  GEN_CP_PW="$(generate_secret 24)"
  GEN_ADMIN_TOKEN="$(generate_secret 32)"
  GEN_S3_KEY="admin_$(generate_secret 8)"
  GEN_S3_SECRET="$(generate_secret 24)"

  cat <<EOF > "${ENV_FILE}"
# ==============================================================================
# DB HOST CONTROL PLANE - PRODUCTION CONFIGURATION
# Auto-generated on $(date -u)
# ==============================================================================

NODE_ENV=production
HOST_BIND_IP=0.0.0.0
WEB_PORT=3000
POSTGRES_PORT=5432
S3_PORT=8333

# Public Host / Domain for TLS and Client Connection Strings
PUBLIC_POSTGRES_HOST=localhost

# Control Plane Dashboard Authentication (HTTP Basic Auth)
CONTROL_PLANE_USERNAME=admin
CONTROL_PLANE_PASSWORD=${GEN_CP_PW}

# MCP Server Authentication (Bearer Token)
ADMIN_TOKEN=${GEN_ADMIN_TOKEN}

# PostgreSQL Master Superuser Credentials
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${GEN_POSTGRES_PW}

# SeaweedFS S3 Superuser Admin Credentials
SEAWEEDFS_ADMIN_ACCESS_KEY=${GEN_S3_KEY}
SEAWEEDFS_ADMIN_SECRET_KEY=${GEN_S3_SECRET}
EOF

  chmod 600 "${ENV_FILE}"
  echo -e "${GREEN}==> Created ${ENV_FILE} with strict 0600 permissions.${NC}"
else
  echo -e "${CYAN}==> Existing ${ENV_FILE} found. Reusing existing credentials.${NC}"
fi

# Load variables from .env
set -a
# shellcheck disable=SC1091
source "${ENV_FILE}"
set +a

# 3. Clean up any unmanaged standalone containers from local dev
for cname in neon-postgres neon-seaweedfs db-host-web; do
  if docker ps -a --format '{{.Names}}' | grep -Eq "^${cname}\$"; then
    IS_COMPOSE=$(docker inspect "${cname}" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)
    if [ -z "${IS_COMPOSE}" ]; then
      echo -e "${YELLOW}==> Migrating existing standalone container '${cname}' into Docker Compose...${NC}"
      docker rm -f "${cname}" >/dev/null 2>&1 || true
    fi
  fi
done

# 4. Pre-flight initialization (directories, TLS certificates, s3 config)
echo -e "${CYAN}==> Running pre-flight setup (TLS certificates & directories)...${NC}"
./scripts/init-setup.sh

# Ensure external bridge network exists for docker compose
if ! docker network inspect dbhost-network >/dev/null 2>&1; then
  echo -e "${CYAN}==> Creating external Docker network 'dbhost-network'...${NC}"
  docker network create dbhost-network >/dev/null 2>&1 || true
fi

# 5. Build and start containers via Docker Compose
echo -e "${CYAN}==> Orchestrating containers with Docker Compose...${NC}"
docker compose -f docker-compose.prod.yml up -d --build

# 6. Healthcheck polling
WEB_PORT="${WEB_PORT:-3000}"
HEALTH_URL="http://127.0.0.1:${WEB_PORT}/api/health"
echo -e "${CYAN}==> Waiting for control plane to become healthy at ${HEALTH_URL}...${NC}"

MAX_RETRIES=45
RETRY_COUNT=0
HEALTHY=false

while [ "${RETRY_COUNT}" -lt "${MAX_RETRIES}" ]; do
  if command -v curl >/dev/null 2>&1; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${HEALTH_URL}" 2>/dev/null || true)
    if [ "${HTTP_CODE}" = "200" ]; then
      HEALTHY=true
      break
    fi
  fi
  RETRY_COUNT=$((RETRY_COUNT + 1))
  sleep 1
  echo -n "."
done
echo ""

if [ "${HEALTHY}" != true ]; then
  echo -e "${YELLOW}[WARNING] Health check timed out after ${MAX_RETRIES}s.${NC}"
  echo -e "Containers may still be completing migrations. Check container logs with:"
  echo -e "  ${BOLD}docker compose -f docker-compose.prod.yml logs -f web${NC}\n"
else
  echo -e "${GREEN}==> All services are healthy and running!${NC}\n"
fi

# Detect display host IP/name
HOST_DISPLAY="${PUBLIC_POSTGRES_HOST:-localhost}"
if [ "${HOST_DISPLAY}" = "localhost" ] || [ "${HOST_DISPLAY}" = "127.0.0.1" ]; then
  # Try to detect external public IP if available
  DETECTED_IP=$(curl -s --max-time 2 https://api.ipify.org 2>/dev/null || true)
  if [ -n "${DETECTED_IP}" ]; then
    HOST_DISPLAY="${DETECTED_IP}"
  fi
fi

# 7. Output Access & Credentials Banner
echo -e "${BOLD}${GREEN}======================================================================${NC}"
echo -e "${BOLD}${GREEN}           DB Host Control Plane is Live & Ready!                     ${NC}"
echo -e "${BOLD}${GREEN}======================================================================${NC}"
echo -e ""
echo -e "  ${BOLD}Dashboard URL:${NC}         http://${HOST_DISPLAY}:${WEB_PORT}"
echo -e "  ${BOLD}Username:${NC}              ${CONTROL_PLANE_USERNAME:-admin}"
echo -e "  ${BOLD}Password:${NC}              ${CONTROL_PLANE_PASSWORD}"
echo -e ""
echo -e "  ${BOLD}PostgreSQL Host:${NC}       ${HOST_DISPLAY}:${POSTGRES_PORT:-5432} ${CYAN}(TLS enforced)${NC}"
echo -e "  ${BOLD}Postgres Superuser:${NC}    ${POSTGRES_USER:-postgres}"
echo -e "  ${BOLD}Postgres Password:${NC}     ${POSTGRES_PASSWORD}"
echo -e "  ${BOLD}CA Certificate:${NC}        http://${HOST_DISPLAY}:${WEB_PORT}/api/ca.crt"
echo -e ""
echo -e "  ${BOLD}SeaweedFS S3 Endpoint:${NC} http://${HOST_DISPLAY}:${S3_PORT:-8333}"
echo -e "  ${BOLD}S3 Admin Access Key:${NC}   ${SEAWEEDFS_ADMIN_ACCESS_KEY}"
echo -e "  ${BOLD}S3 Admin Secret Key:${NC}   ${SEAWEEDFS_ADMIN_SECRET_KEY}"
echo -e ""
echo -e "  ${BOLD}MCP HTTP Endpoint:${NC}     http://${HOST_DISPLAY}:${WEB_PORT}/api/mcp"
echo -e "  ${BOLD}MCP Bearer Token:${NC}      ${ADMIN_TOKEN}"
echo -e "${BOLD}${GREEN}======================================================================${NC}"

if [ "${FIRST_RUN}" = true ]; then
  echo -e "${YELLOW}IMPORTANT: Save the credentials above securely! They are stored in ${BOLD}.env${NC}\n"
fi

echo -e "Helpful commands:"
echo -e "  View running services: ${BOLD}docker compose -f docker-compose.prod.yml ps${NC}"
echo -e "  View application logs: ${BOLD}docker compose -f docker-compose.prod.yml logs -f web${NC}"
echo -e "  Stop stack:            ${BOLD}docker compose -f docker-compose.prod.yml down${NC}"
echo -e "  Update & redeploy:     ${BOLD}git pull && ./deploy.sh${NC}\n"
