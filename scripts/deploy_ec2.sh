#!/usr/bin/env bash
set -euo pipefail

# Lightweight EC2 bootstrap for LiteStore (Ubuntu)
REPO_URL="${REPO_URL:?Set REPO_URL, e.g. https://github.com/user/litestore.git}"
APP_DIR="${APP_DIR:-/opt/litestore}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

sudo apt update
sudo apt install -y git python3 python3-venv

if [[ ! -d "${APP_DIR}" ]]; then
  sudo git clone "${REPO_URL}" "${APP_DIR}"
else
  sudo git -C "${APP_DIR}" pull --ff-only
fi

sudo ${PYTHON_BIN} -m venv "${APP_DIR}/.venv"
sudo "${APP_DIR}/.venv/bin/pip" install -U pip
sudo "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
sudo "${APP_DIR}/.venv/bin/pip" install pytest pytest-asyncio

sudo bash "${APP_DIR}/scripts/install_systemd.sh"
