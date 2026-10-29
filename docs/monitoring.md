# Monitoring and encrypted backups

What runs, how to turn it on, what each alert means, and how to back up and
restore the database.

```
            ┌──────────── host ─────────────┐
 systemd    │ db_backup.sh  ─┐  dir_sizes.sh│──► /var/lib/node_exporter/textfile/*.prom
 timers     └────────────────┼──────────────┘                │
                             ▼                               ▼
   safefamily_db ◄── postgres-exporter ──┐            node-exporter (disk, CPU, RAM)
   safefamily_proxy ◄── nginx-exporter ──┤            cadvisor (per-container)
   safefamily_proxy ◄── blackbox (HTTPS)─┤                   │
                                         ▼                   ▼
                                   Prometheus ──► Alertmanager ──► email (Gmail SMTP)
                                         │
                                         ▼
                                     Grafana (127.0.0.1:3000)
```

| Question | Answered by |
|---|---|
| Is a disk filling up? (repo dir, logs, Docker volumes incl. Postgres) | node-exporter filesystems + `dir_sizes.sh` |
| How big is the database, how many connections, is it up? | postgres-exporter |
| Are the app, db and proxy containers running, how much CPU/RAM? | cadvisor |
| Does the website load, how fast, when does the TLS cert expire? | blackbox-exporter |
| How many requests/connections is nginx handling? | nginx-exporter (`stub_status`) |
| Did last night's encrypted backup succeed? | `db_backup.sh` metrics |

Postgres has no "free space" of its own: it grows until the filesystem under
the Docker volume is full. So "database free space" means the free space of
the filesystem holding Docker's data dir (usually `/`), plus the database size
trend and the `DiskWillFillIn24h` prediction.

## 1. Turn on the monitoring stack

Add to `.env` (the alert mails reuse the app's `MAIL_ACCOUNT` / `MAIL_PASSWORD`
Gmail app password):

```bash
GRAFANA_ADMIN_PASSWORD=<a long random password>
# Optional:
# ALERT_EMAIL_TO=you@example.com            # default: MAIL_ACCOUNT
# GRAFANA_BIND=0.0.0.0                      # default: 127.0.0.1 (localhost only)
# DOCKER_ROOT_DIR=/var/snap/docker/common/var-lib-docker   # snap-installed Docker
# Make plain `docker compose ...` include the monitoring services:
COMPOSE_FILE=docker-compose.yml:deploy/monitoring/docker-compose.monitoring.yml
```

Then:

```bash
sudo mkdir -p /var/lib/node_exporter/textfile
docker compose up -d                 # starts the new services, recreates proxy for stub_status
docker compose ps                    # all safefamily_* should be "Up"
```

Open Grafana at <http://127.0.0.1:3000> (from another machine:
`ssh -L 3000:127.0.0.1:3000 server`), log in as `admin`, and open
**Dashboards → SafeFamily → SafeFamily Overview**. (`GRAFANA_ADMIN_PASSWORD`
only sets the password on Grafana's first start; change it later in the UI.) Prometheus itself is at
<http://127.0.0.1:9090> (`/alerts` shows every rule and its state).

For deeper views, import community dashboards in Grafana (Dashboards → New →
Import → ID): **1860** Node Exporter Full, **14282** cAdvisor, **9628**
PostgreSQL, **12708** NGINX exporter.

### Host-specific notes

- **Self-signed TLS certificate**: the website probe verifies the certificate,
  so it reports DOWN with a self-signed one. Either use a real certificate
  (Let's Encrypt works with duckdns), or add `insecure_skip_verify: true` under
  `tls_config` in `deploy/monitoring/blackbox/blackbox.yml`.
- **Docker 29+ / containerd image store**: cadvisor talks to containerd at
  `/run/containerd/containerd.sock`. If `docker logs safefamily_cadvisor` says
  `unable to create containerd client`, find the socket
  (`sudo find /run -name containerd.sock`) and mount it there, e.g. for snap
  Docker add under `cadvisor.volumes`:
  `- /run/snap.docker/containerd/containerd.sock:/run/containerd/containerd.sock:ro`
- **Snap Docker** may refuse bind mounts outside `$HOME`. If node-exporter or
  cadvisor fail to start with a mount error, install node-exporter on the host
  instead (`sudo apt install prometheus-node-exporter`, set
  `ARGS="--collector.textfile.directory=/var/lib/node_exporter/textfile"` in
  `/etc/default/prometheus-node-exporter`), remove the `node-exporter` service,
  and point the `node` job in `prometheus/prometheus.yml` at
  `host.docker.internal:9100` with `extra_hosts: ["host.docker.internal:host-gateway"]`
  on the prometheus service.

## 2. Alerts

Rules live in `deploy/monitoring/prometheus/alerts.yml`; emails are sent by
Alertmanager (critical alerts repeat every 3h, warnings every 12h, and a
"resolved" mail follows each).

| Alert | Fires when | First thing to check |
|---|---|---|
| DiskSpaceLow / DiskSpaceCritical | a filesystem is under 15% / 5% free | "Directory sizes" panel; prune per README "Prune Cache" |
| DiskWillFillIn24h | the 6h trend reaches 0 within a day | same, plus `PostgresDatabaseGrowingFast` |
| ContainerDown | app, db or proxy not running for 2 min | `docker compose ps`, `docker compose logs --tail=100 <svc>` |
| ContainerHighMemory | a container uses > 2 GiB for 15 min | `docker stats` |
| PostgresDown | the exporter cannot query Postgres | `docker compose logs db` |
| PostgresTooManyConnections | > 80% of `max_connections` | Gunicorn workers × pool size |
| PostgresDatabaseGrowingFast | > 1 GiB growth in 24h | usually `logs` or `media` tables |
| WebsiteDown | HTTPS check of `/auth/login-ui` fails for 3 min | `docker compose logs proxy app` |
| WebsiteSlow | page load > 3s for 10 min | "Page load phases" panel |
| TLSCertificateExpiringSoon | cert expires in < 14 days | renew the certificate |
| DatabaseBackupMissing | no successful backup for 26h | `journalctl -u safefamily-backup.service` |
| DatabaseBackupFailed | the last backup run failed | same |
| MetricsFileUnreadable | node-exporter cannot read a `.prom` file | `docker logs safefamily_node_exporter` |
| ScrapeTargetDown | an exporter is unreachable for 5 min | `docker compose ps` |
| HostMemoryLow / HostHighLoad | < 10% RAM available / load > 1.5× CPUs | `top`, `docker stats` |

Test the mail path once after setup:

```bash
docker exec safefamily_alertmanager amtool alert add TestAlert severity=warning \
    --annotation='summary="SafeFamily alert test"' --alertmanager.url=http://localhost:9093
```

## 3. Encrypted database backups

`scripts/db_backup.sh` makes a **full** dump (every table, including logs and
media; `scripts/db_export.py` is the sanitized, schema-oriented export) and
encrypts it with [age](https://age-encryption.org) (X25519 +
ChaCha20-Poly1305). It encrypts to a **public key**: the server can create
backups but cannot read them. Only the private key, kept off the server, can
decrypt, so a stolen server, disk, or offsite copy reveals nothing.

Each run: `pg_dump --format=custom` inside the db container → `pg_restore
--list` to prove the dump is readable → `age` encrypt → atomic rename into
`$BACKUP_DIR/daily/`. The first backup of each month is also hard-linked into
`monthly/`. Keeps 14 daily and 12 monthly by default. Writes metrics for the
backup alerts and the "Last DB backup" panel.

### One-time setup

On **your laptop or another machine that is not the server**:

```bash
sudo apt install age            # macOS: brew install age
age-keygen -o safefamily-backup-key.txt
# prints: Public key: age1...
# Optional: passphrase-protect the private key file too
age -p -o safefamily-backup-key.txt.age safefamily-backup-key.txt && shred -u safefamily-backup-key.txt
```

Store the private key in a password manager **and** on paper or a USB stick.
Without it the backups are unrecoverable; that is the point.

On the **server**:

```bash
sudo apt install age
sudo mkdir -p /etc/safefamily /var/backups/safefamily /var/lib/node_exporter/textfile
echo 'age1...your public key...' | sudo tee /etc/safefamily/backup-recipients.txt
sudo cp deploy/monitoring/backup.env.example /etc/safefamily/backup.env
sudo chmod 600 /etc/safefamily/backup.env       # edit paths if needed

# Edit ExecStart in both .service files if the checkout is not /srv/SafeFamily
sudo cp deploy/systemd/safefamily-backup.* deploy/systemd/safefamily-dirsize.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now safefamily-backup.timer safefamily-dirsize.timer

sudo systemctl start safefamily-backup.service   # first backup now
journalctl -u safefamily-backup.service -n 20
ls -l /var/backups/safefamily/daily/
```

The recipients file may hold several public keys (one per line), e.g. one for
you and one for a family member; any one of them can decrypt. The script
refuses to run if the file contains a private key.

Cron instead of systemd: `17 3 * * * set -a; . /etc/safefamily/backup.env; /srv/SafeFamily/scripts/db_backup.sh`

### Offsite copies

Point your existing backup scripts at `/var/backups/safefamily/` (it is already
encrypted, so any cloud drive or USB disk is fine). For example:
`rclone copy /var/backups/safefamily remote:safefamily-backups`, or
`rsync -a /var/backups/safefamily/ nas:/backups/safefamily/`.

### Restore

Practise once now, and again every few months. A restore drill goes into a
scratch database (`safefamily_restore_test`) and never touches live data:

```bash
# On the server, with the key temporarily copied over:
scripts/db_restore.sh -i safefamily-backup-key.txt /var/backups/safefamily/daily/safefamily-<stamp>.dump.age

# Or keep the key on your laptop and stream the decrypted dump:
age -d -i safefamily-backup-key.txt safefamily-<stamp>.dump.age \
    | ssh server 'cd /srv/SafeFamily && scripts/db_restore.sh -'
```

It prints the row count of every table. Drop the scratch DB afterwards with
`docker exec safefamily_db dropdb -U "$DB_USER" safefamily_restore_test`.

Real disaster recovery (replaces the live data):

```bash
docker compose stop app
scripts/db_restore.sh -i safefamily-backup-key.txt --into-live safefamily-<stamp>.dump.age
#   (type the database name to confirm; when streaming over ssh use --confirm <db name>)
docker compose start app
```

On a brand-new host, bring up `db` first (`docker compose up -d db`), then
restore with `--into-live`.
