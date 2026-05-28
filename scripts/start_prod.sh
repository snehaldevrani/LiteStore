#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/deploy/litestore.env.example}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file not found: ${ENV_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

exec "${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/src/main.py" \
  --host "${LITESTORE_HOST}" \
  --port "${LITESTORE_PORT}" \
  --metrics-host "${LITESTORE_METRICS_HOST}" \
  --metrics-port "${LITESTORE_METRICS_PORT}" \
  --workers "${LITESTORE_WORKERS}" \
  --aof-path "${LITESTORE_AOF_PATH}"
