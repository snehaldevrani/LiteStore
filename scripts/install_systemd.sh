#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/litestore}"
SERVICE_FILE="${APP_DIR}/deploy/litestore.service"
ENV_SOURCE_FILE="${APP_DIR}/deploy/litestore.env.example"
ENV_TARGET_DIR="/etc/litestore"
ENV_TARGET_FILE="${ENV_TARGET_DIR}/litestore.env"
SYSTEMD_TARGET="/etc/systemd/system/litestore.service"
SERVICE_USER="litestore"

if [[ ! -f "${SERVICE_FILE}" ]]; then
  echo "Missing service file: ${SERVICE_FILE}" >&2
  exit 1
fi

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  sudo useradd --system --home "${APP_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

sudo mkdir -p "${ENV_TARGET_DIR}" /var/lib/litestore
sudo cp "${ENV_SOURCE_FILE}" "${ENV_TARGET_FILE}"
sudo chown -R "${SERVICE_USER}:${SERVICE_USER}" /var/lib/litestore
sudo chmod 640 "${ENV_TARGET_FILE}"

sudo cp "${SERVICE_FILE}" "${SYSTEMD_TARGET}"
sudo systemctl daemon-reload
sudo systemctl enable litestore
sudo systemctl restart litestore
sudo systemctl status litestore --no-pager
