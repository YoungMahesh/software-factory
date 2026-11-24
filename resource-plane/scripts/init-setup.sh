#!/usr/bin/env bash
set -euo pipefail

# DB Host Pre-Flight Initialization Script
# Ensures required directories, TLS certificates, and SeaweedFS configs exist.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_DIR="${ROOT_DIR}/.data"
CERTS_DIR="${DATA_DIR}/certs"
POSTGRES_DATA_DIR="${DATA_DIR}/postgres"
SEAWEEDFS_DATA_DIR="${DATA_DIR}/seaweedfs"

mkdir -p "${POSTGRES_DATA_DIR}" "${SEAWEEDFS_DATA_DIR}" "${CERTS_DIR}"
chmod 755 "${CERTS_DIR}"

# 1. Initialize SeaweedFS S3 config if missing
S3_CONFIG="${SEAWEEDFS_DATA_DIR}/s3.json"
if [ ! -f "${S3_CONFIG}" ]; then
  ACCESS_KEY="${SEAWEEDFS_ADMIN_ACCESS_KEY:-admin_access_key}"
  SECRET_KEY="${SEAWEEDFS_ADMIN_SECRET_KEY:-admin_secret_key}"
  cat <<EOF > "${S3_CONFIG}"
{
  "identities": [
    {
      "name": "admin",
      "credentials": [
        {
          "accessKey": "${ACCESS_KEY}",
          "secretKey": "${SECRET_KEY}"
        }
      ],
      "actions": ["Admin", "Read", "List", "Tagging", "Write"]
    }
  ]
}
EOF
  chmod 644 "${S3_CONFIG}"
fi

# 2. Initialize Root CA and TLS Server Certificates
CA_KEY="${CERTS_DIR}/ca.key"
CA_CERT="${CERTS_DIR}/ca.crt"
SERVER_KEY="${CERTS_DIR}/server.key"
SERVER_CERT="${CERTS_DIR}/server.crt"
CERT_HOST_META="${CERTS_DIR}/.cert-host"
PUBLIC_HOST="${PUBLIC_POSTGRES_HOST:-${PUBLIC_HOST:-localhost}}"

# Function to execute openssl (host or fallback container)
run_openssl() {
  if command -v openssl >/dev/null 2>&1; then
    openssl "$@"
  else
    docker run --rm -v "${CERTS_DIR}:/certs" -w /certs alpine/openssl "$@"
  fi
}

# Generate Root CA if missing
if [ ! -f "${CA_KEY}" ] || [ ! -f "${CA_CERT}" ]; then
  run_openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
    -keyout "${CA_KEY}" \
    -out "${CA_CERT}" \
    -subj "/CN=Neon Local Root CA" >/dev/null 2>&1
  chmod 600 "${CA_KEY}"
  chmod 644 "${CA_CERT}"
fi

# Check if server cert needs generation
NEEDS_CERT=false
if [ ! -f "${SERVER_KEY}" ] || [ ! -f "${SERVER_CERT}" ]; then
  NEEDS_CERT=true
elif [ -f "${CERT_HOST_META}" ]; then
  RECORDED_HOST="$(cat "${CERT_HOST_META}")"
  if [ "${RECORDED_HOST}" != "${PUBLIC_HOST}" ]; then
    NEEDS_CERT=true
  fi
else
  NEEDS_CERT=true
fi

if [ "${NEEDS_CERT}" = true ]; then
  TEMP_CSR="${CERTS_DIR}/server-$$.csr"
  TEMP_EXT="${CERTS_DIR}/server-$$.ext"

  run_openssl req -newkey rsa:2048 -nodes \
    -keyout "${SERVER_KEY}" \
    -out "${TEMP_CSR}" \
    -subj "/CN=${PUBLIC_HOST}" >/dev/null 2>&1

  # Construct Subject Alternative Names (SAN)
  SAN_ENTRIES=""
  if [[ "${PUBLIC_HOST}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    SAN_ENTRIES="IP:${PUBLIC_HOST}"
  else
    SAN_ENTRIES="DNS:${PUBLIC_HOST}"
  fi
  SAN_ENTRIES="${SAN_ENTRIES}, DNS:localhost, IP:127.0.0.1, IP:::1, DNS:postgres, DNS:neon-postgres"

  cat <<EOF > "${TEMP_EXT}"
subjectAltName = ${SAN_ENTRIES}
EOF

  run_openssl x509 -req \
    -in "${TEMP_CSR}" \
    -CA "${CA_CERT}" \
    -CAkey "${CA_KEY}" \
    -CAcreateserial \
    -out "${SERVER_CERT}" \
    -days 365 \
    -sha256 \
    -extfile "${TEMP_EXT}" >/dev/null 2>&1

  chmod 600 "${SERVER_KEY}"
  chmod 644 "${SERVER_CERT}"
  echo "${PUBLIC_HOST}" > "${CERT_HOST_META}"

  rm -f "${TEMP_CSR}" "${TEMP_EXT}" "${CERTS_DIR}/ca.srl" 2>/dev/null || true
fi

# Ensure PostgreSQL container user (UID 70) can read the certificates
if command -v docker >/dev/null 2>&1; then
  docker run --rm -v "${CERTS_DIR}:/certs" alpine chown -R 70:70 /certs 2>/dev/null || true
fi

exit 0
