# Extra scrape targets

Every `*.yml` file here is loaded by Prometheus as a list of scrape configs
(`scrape_config_files` in `../prometheus.yml`). Add a file, then reload:

```bash
docker compose restart prometheus
docker run --rm -v "$PWD/deploy/monitoring/prometheus:/etc/prometheus:ro" \
    --entrypoint promtool prom/prometheus:v3.5.0 check config /etc/prometheus/prometheus.yml
```

Example, `scrape.d/router.yml` for an exporter on another machine:

```yaml
scrape_configs:
  - job_name: router
    static_configs:
      - targets: ["10.0.0.1:9100"]
```

An exporter on this host but outside Docker is reachable as
`host.docker.internal:<port>` when the prometheus service has
`extra_hosts: ["host.docker.internal:host-gateway"]`.
