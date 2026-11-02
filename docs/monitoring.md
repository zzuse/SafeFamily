# Monitoring and encrypted backups

What runs, how to turn it on, what each alert means, and how to back up and
restore the database. For a step-by-step setup with checks, routine tasks and
troubleshooting, follow [operations-checklist.md](operations-checklist.md);
`scripts/monitoring/preflight.sh` verifies the host first.

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
# CONTAINERD_SOCKET=/run/snap.docker/containerd/containerd.sock  # if preflight says so
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
- **<a id="cadvisor-without-container-names"></a>cadvisor without container
  names** ("App containers running" shows No data, container panels empty,
  `ContainerDown` firing although everything runs): cadvisor v0.54 asks
  containerd for container details with **any** image store, classic
  `overlay2` included, at `/run/containerd/containerd.sock` by default. If
  `docker logs safefamily_cadvisor` says `unable to create containerd client`
  (or the container panels are empty), set `CONTAINERD_SOCKET` in `.env` to the
  real socket; `scripts/monitoring/preflight.sh` finds it and prints the exact
  line (for example `CONTAINERD_SOCKET=/run/snap.docker/containerd/containerd.sock`
  for snap Docker). Then `docker compose up -d cadvisor`.
- **Snap Docker**: snap's confinement can give containers the snap's own
  small filesystem instead of the host's `/` (`preflight.sh --deep`: "containers
  see a different /"), which makes every disk number and disk alert wrong, and
  can refuse the textfile mount ("read-only file system"). Then run
  node-exporter **on the host** instead; the dashboard, alerts and backup
  metrics work unchanged:
  ```bash
  sudo apt install prometheus-node-exporter
  # /etc/default/prometheus-node-exporter: read the same dir the scripts write to
  sudo sed -i 's#^ARGS=.*#ARGS="--collector.textfile.directory=/var/lib/node_exporter/textfile"#' \
      /etc/default/prometheus-node-exporter
  sudo mkdir -p /var/lib/node_exporter/textfile
  sudo systemctl restart prometheus-node-exporter
  curl -s localhost:9100/metrics | grep -c '^node_filesystem_size_bytes'   # > 0

  # .env: append the host overlay to COMPOSE_FILE
  COMPOSE_FILE=docker-compose.yml:deploy/monitoring/docker-compose.monitoring.yml:deploy/monitoring/docker-compose.host-node-exporter.yml

  docker rm -f safefamily_node_exporter    # the old container, if it exists
  docker compose up -d
  ```
  The overlay disables the node-exporter container and points Prometheus's
  `node-exporter` name at the host. If `ufw` is active, let containers reach
  it: `sudo ufw allow from 172.16.0.0/12 to any port 9100 proto tcp` (port
  9100 needs no opening to the internet). Keep `NODE_EXPORTER_TEXTFILE_DIR` at
  its default; the `/var/snap/...` textfile dir suggested for snap does not
  apply in this mode.
- **Snap Docker, textfile dir only**: if `--deep` reports the real `/` but
  refuses the textfile mount, either use host mode above or a directory in
  snap Docker's own data area, set in **both** `.env` and
  `/etc/safefamily/backup.env`:
  `NODE_EXPORTER_TEXTFILE_DIR=/var/snap/docker/common/node_exporter_textfile`
  (create it first), then `docker compose up -d node-exporter`.

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
| DatabaseBackupMissing | no successful backup for 8 days (backups are weekly) | `journalctl -u safefamily-backup.service` |
| DatabaseBackupFailed | the last backup run failed | same |
| MetricsFileUnreadable | node-exporter cannot read a `.prom` file | `docker logs safefamily_node_exporter` |
| ScrapeTargetDown | an exporter is unreachable for 5 min | `docker compose ps` |
| HostMemoryLow / HostHighLoad | < 10% RAM available / load > 1.5× CPUs | `top`, `docker stats` |
| NetworkMountUnreachable | a Samba/NFS share stops answering for 5 min | `ls <mount>`; `sudo dmesg \| grep -iE 'cifs\|smb\|nfs' \| tail` |
| NetworkMountMissing | a share mounted in the last 7 days is gone | `sudo mount <mount>` or `sudo mount -a` |

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
`$BACKUP_DIR/weekly/`. Runs **weekly** (Sundays 03:17, or at the next boot if
the server was off). The first backup of each month is also hard-linked into
`monthly/` at no extra disk cost. Keeps the newest **8 weekly** (two months)
and **6 monthly** (half a year) backups. Files are root-only unless
`BACKUP_GROUP` names a group allowed to read them (safe: they are
encrypted), which lets you `scp` them or copy them offsite without sudo.
Change retention with `BACKUP_KEEP_WEEKLY` /
`BACKUP_KEEP_MONTHLY` in `/etc/safefamily/backup.env`. Retention counts
backups rather than days, so if backups fail for a long time the last good
ones are never pruned. Writes metrics for the backup alerts and the "Last DB
backup" panel. To change the day or time, edit `OnCalendar=` in
`/etc/systemd/system/safefamily-backup.timer` and run `sudo systemctl daemon-reload`.

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
ls -l /var/backups/safefamily/weekly/
```

The recipients file may hold several public keys (one per line), e.g. one for
you and one for a family member; any one of them can decrypt. The script
refuses to run if the file contains a private key.

Cron instead of systemd (Sundays 03:17): `17 3 * * 0 set -a; . /etc/safefamily/backup.env; /srv/SafeFamily/scripts/db_backup.sh`

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
scripts/db_restore.sh -i safefamily-backup-key.txt /var/backups/safefamily/weekly/safefamily-<stamp>.dump.age

# Or keep the key on your laptop and stream the decrypted dump:
age -d -i safefamily-backup-key.txt safefamily-<stamp>.dump.age \
    | ssh server 'cd /srv/SafeFamily && scripts/db_restore.sh -'
```

It prints the row count of every table. Drop the scratch DB afterwards with
`scripts/db_restore.sh --drop-test`.

Real disaster recovery (replaces the live data):

```bash
docker compose stop app
scripts/db_restore.sh -i safefamily-backup-key.txt --into-live safefamily-<stamp>.dump.age
#   (type the database name to confirm; when streaming over ssh use --confirm <db name>)
docker compose start app
```

On a brand-new host, bring up `db` first (`docker compose up -d db`), then
restore with `--into-live`.

## 4. Adding more monitoring sources

Pick the row that fits; none of them needs edits to the tracked config files.

| You want to watch | Do this |
|---|---|
| A disk, USB drive or **Samba/NFS share mounted on the host** | Nothing: node-exporter reports every mounted filesystem. See below. |
| Another website or URL | Add it to `targets` of the `website` job in `prometheus/prometheus.yml`, or a blackbox job in `scrape.d/` |
| Anything that has a Prometheus exporter (router, NAS, another server, a database) | Run the exporter, then add a scrape file in `deploy/monitoring/prometheus/scrape.d/` (README there) |
| A custom check (a script, a file's age, a share being writable) | Write a script that prints metrics into `/var/lib/node_exporter/textfile/<name>.prom` from a timer, like `scripts/monitoring/dir_sizes.sh` does |
| An alert on any of these | Add a rule file in `deploy/monitoring/prometheus/rules.d/` (README there) |
| A Grafana panel | Build it in Grafana (dashboard → Make editable → Save as a new dashboard), or drop a dashboard JSON into `grafana/dashboards/` |

After adding scrape or rule files: `docker compose restart prometheus`, then
check Prometheus's targets page (<http://127.0.0.1:9090/targets>) or rerun
`scripts/monitoring/preflight.sh`.

### Samba share mounted on the host

node-exporter (on the host, see "Snap Docker" above) measures the share like
any filesystem, so it already appears in **Free space by mount** and is
covered by `DiskSpaceLow`/`DiskSpaceCritical`. On top of that,
`NetworkMountUnreachable` and `NetworkMountMissing` (section 2) fire for any
`cifs`/`smb3`/`nfs` mount; nothing to configure.

Check that the share is being collected (replace `/mnt/nas`):

```bash
curl -s localhost:9100/metrics | grep 'node_filesystem_avail_bytes' | grep -E 'cifs|smb3'
```

- **No line for the share**: older node-exporter versions (e.g. Ubuntu
  22.04's 1.3.1) skip some mount points by default. See the active filter
  with `prometheus-node-exporter --help 2>&1 | grep -A1 'mount-points'`; if
  your mount point matches it, add to `ARGS` in
  `/etc/default/prometheus-node-exporter`
  (1.3.x: `--collector.filesystem.ignored-mount-points='^/(dev|proc|run|sys)($|/)'`,
  1.5+: `--collector.filesystem.mount-points-exclude='^/(dev|proc|run|sys)($|/)'`)
  and `sudo systemctl restart prometheus-node-exporter`.
- **Mount it so a dead server cannot hang the host**: in `/etc/fstab` use
  `nofail,_netdev,x-systemd.automount,x-systemd.mount-timeout=30`, and a
  `credentials=/root/.smbcredentials` file (mode 600) instead of a password
  in fstab.
- Do not add the share to `DIR_SIZES_EXTRA` for `dir_sizes.sh`: `du` over the
  network every 15 minutes is slow and loads the file server.
- To alert at a different threshold for one share, copy the example in
  `prometheus/rules.d/README.md`.

Validate rule changes, including the unit tests for the share alerts:

```bash
P='docker run --rm -v '"$PWD"'/deploy/monitoring/prometheus:/etc/prometheus:ro --entrypoint promtool prom/prometheus:v3.5.0'
$P check config /etc/prometheus/prometheus.yml
$P test rules /etc/prometheus/tests/network_mounts_test.yml
```
