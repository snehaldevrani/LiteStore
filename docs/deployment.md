# LiteStore Deployment Guide

This guide describes a lightweight, systemd-based deployment for LiteStore on a single Linux host (for example EC2 Ubuntu).

## 1) Files in this deployment bundle

- `deploy/litestore.service`: systemd unit
- `deploy/litestore.env.example`: environment config template
- `deploy/litestore.logrotate`: optional log rotation template
- `scripts/deploy_ec2.sh`: host bootstrap helper
- `scripts/install_systemd.sh`: installs and starts systemd service
- `scripts/start_prod.sh`: manual production start helper

## 2) Recommended host setup

- Ubuntu 22.04+
- Ports open only to trusted sources:
  - LiteStore TCP port (default `6379`)
  - metrics port (default `9100`)
- Separate system user (`litestore`)

## 3) Fast EC2 bootstrap

On the instance:

```bash
export REPO_URL=https://github.com/<owner>/<repo>.git
curl -fsSL <your-script-location>/deploy_ec2.sh -o deploy_ec2.sh
bash deploy_ec2.sh
```

Alternative if repository is already cloned to `/opt/litestore`:

```bash
cd /opt/litestore
bash scripts/install_systemd.sh
```

## 4) Environment configuration

Copy and edit:

```bash
sudo mkdir -p /etc/litestore
sudo cp /opt/litestore/deploy/litestore.env.example /etc/litestore/litestore.env
sudo nano /etc/litestore/litestore.env
```

Core variables:

- `LITESTORE_HOST`
- `LITESTORE_PORT`
- `LITESTORE_METRICS_HOST`
- `LITESTORE_METRICS_PORT`
- `LITESTORE_WORKERS`
- `LITESTORE_AOF_PATH`

## 5) Start and manage service

```bash
sudo systemctl daemon-reload
sudo systemctl enable litestore
sudo systemctl start litestore
sudo systemctl status litestore --no-pager
```

## 6) Validate deployment

```bash
# command port
printf 'PING\n' | nc 127.0.0.1 6379

# metrics
curl -s http://127.0.0.1:9100/metrics | head
```

## 7) Upgrade flow

```bash
cd /opt/litestore
sudo git pull --ff-only
sudo /opt/litestore/.venv/bin/pip install -r requirements.txt
sudo systemctl restart litestore
```
