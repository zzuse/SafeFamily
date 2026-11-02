# Extra alert rules

Every `*.yml` file here is loaded as a Prometheus rule file (same format as
`../alerts.yml`). Alerts go out through the same Alertmanager email. Check and
reload:

```bash
docker run --rm -v "$PWD/deploy/monitoring/prometheus:/etc/prometheus:ro" \
    --entrypoint promtool prom/prometheus:v3.5.0 check rules /etc/prometheus/rules.d/my-rules.yml
docker compose restart prometheus
```

Example, `rules.d/samba.yml`: alert when a specific share is under 10% free
(general network-share alerts are already in `../alerts.yml`):

```yaml
groups:
  - name: my-samba
    rules:
      - alert: NasShareAlmostFull
        expr: node_filesystem_avail_bytes{mountpoint="/mnt/nas"} / node_filesystem_size_bytes{mountpoint="/mnt/nas"} < 0.10
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "NAS share /mnt/nas has {{ $value | humanizePercentage }} free"
```
