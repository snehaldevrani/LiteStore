# LiteStore Operations Notes

## Production startup instructions

Use systemd in production. For manual start (not recommended for long-term operation):

```bash
ENV_FILE=/etc/litestore/litestore.env /opt/litestore/scripts/start_prod.sh
```

## Logging recommendations

Primary recommendation:

- Keep runtime logs in `journald` (configured in `deploy/litestore.service`).
- Use `journalctl -u litestore` for operational log inspection.

Optional file-based logs:

- If redirecting to `/var/log/litestore/*.log`, enable `deploy/litestore.logrotate`.

Useful commands:

```bash
sudo journalctl -u litestore -n 200 --no-pager
sudo journalctl -u litestore -f
```

## Basic troubleshooting

### Service fails to start

1. Check service status:

```bash
sudo systemctl status litestore --no-pager
```

2. Check logs:

```bash
sudo journalctl -u litestore -n 200 --no-pager
```

3. Validate env file exists:

```bash
sudo ls -l /etc/litestore/litestore.env
```

4. Validate app path and venv:

```bash
ls -l /opt/litestore/.venv/bin/python
```

### Port already in use

```bash
sudo ss -lntp | grep -E ':6379|:9100'
```

Adjust `LITESTORE_PORT` and `LITESTORE_METRICS_PORT` in `/etc/litestore/litestore.env` and restart.

### Metrics endpoint not reachable

- Confirm service is up.
- Confirm `LITESTORE_METRICS_HOST` is bound to expected interface.
- Confirm security group/firewall allows metrics port.

### Persistence/recovery concerns

- Confirm AOF path exists and is writable by `litestore` user.
- Confirm file growth after write traffic:

```bash
sudo ls -lh /var/lib/litestore/litestore.aof
```

- Restart and verify keys still present.

## Operational checklist

- service enabled on boot
- metrics endpoint scraped
- AOF path monitored for size growth
- backups/snapshots of AOF scheduled
- alerting on service down and high error rates
