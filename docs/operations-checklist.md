# Operations checklist: monitoring and encrypted backups

A step-by-step list to set up, verify and run the monitoring stack and the
weekly encrypted database backup on the SafeFamily server. Background and the
alert reference are in [monitoring.md](monitoring.md).

Each step has a **check** that tells you it worked. If a check fails, stop and
fix it before going on; the preflight script prints the fix for most problems.

Paths assume the checkout is at `/srv/SafeFamily`; substitute yours.

---

## Phase 0: Requirements (15 min)

Run the preflight first. It only reads, never changes anything:

```bash
cd /srv/SafeFamily && git pull
sudo scripts/monitoring/preflight.sh --deep
```

- [ ] **Summary shows 0 failures.** Warnings are fine if you understand them
      (see table). Re-run after every fix.

| Requirement | Why | If preflight complains |
|---|---|---|
| Linux host (not macOS/Windows Docker Desktop) | exporters must see the real disks and containers | run the stack on the Linux server |
| Docker Engine 24+ (tested on 29.9) | cadvisor, compose features | upgrade Docker |
| Docker Compose **v2** plugin, 2.20+ (tested on 5.6) | overlay file, `COMPOSE_FILE` | `sudo apt install docker-compose-plugin`; legacy `docker-compose` v1 is not supported |
| Snap-installed Docker | confinement may block host mounts | `--deep` tests them; fallback in monitoring.md "Host-specific notes" |
| Docker root dir not `/var/lib/docker` (snap) | cadvisor and `dir_sizes.sh` read it | set `DOCKER_ROOT_DIR=` as printed |
| containerd image store (Docker 29+ default) | cadvisor needs the containerd socket | set `CONTAINERD_SOCKET=` as printed |
| 2 GiB+ RAM, 10 GiB+ free disk | stack uses ~600 MiB RAM, Prometheus up to 5 GB | free space or `PROMETHEUS_RETENTION_SIZE=2GB` |
| Ports 3000, 9090 free on 127.0.0.1 | Grafana, Prometheus | free them or change the host port in the overlay |
| Real (not self-signed) TLS certificate | website probe verifies it | Let's Encrypt, or `insecure_skip_verify` (see monitoring.md) |
| Outbound TCP 587 to smtp.gmail.com | alert emails | open the firewall, or set `ALERT_SMTP_SMARTHOST` |
| `age` installed | backup encryption | `sudo apt install age` |
| systemd running | weekly timers | use the cron lines in monitoring.md |

The backup-related failures (recipients file, directories, timers) are
expected on the first run; Phase 2 fixes them.

---

## Phase 1: Monitoring (20 min)

1. - [ ] **Add to `.env`** (edit it yourself; values per Phase 0):
   ```bash
   GRAFANA_ADMIN_PASSWORD=<long random password>
   COMPOSE_FILE=docker-compose.yml:deploy/monitoring/docker-compose.monitoring.yml
   # only if preflight printed them:
   # DOCKER_ROOT_DIR=...
   # CONTAINERD_SOCKET=...
   # ALERT_EMAIL_TO=you@example.com    (default: MAIL_ACCOUNT)
   ```
   Check: `docker compose config --services` lists `prometheus` and `grafana`.

2. - [ ] **Create the metrics directory**:
   `sudo mkdir -p /var/lib/node_exporter/textfile`

3. - [ ] **Start everything**: `docker compose up -d`
   (also recreates `proxy` once, to load the internal `stub_status` endpoint;
   a few seconds of downtime).
   Check: `docker compose ps` shows 11 `safefamily_*` containers `Up`.

4. - [ ] **Wait 2 minutes, then re-run preflight**: `sudo scripts/monitoring/preflight.sh`
   Check: the "Running stack" section shows every scrape target `PASS`.

5. - [ ] **Open Grafana**: from your laptop, `ssh -L 3000:127.0.0.1:3000 <server>`,
   then <http://127.0.0.1:3000>, user `admin`.
   Check: Dashboards → SafeFamily → SafeFamily Overview shows Website UP,
   Database UP, App containers 3, and the disk and container graphs have lines.

6. - [ ] **Send a test alert email**:
   ```bash
   docker exec safefamily_alertmanager amtool alert add TestAlert severity=warning \
       --annotation='summary="SafeFamily alert test"' --alertmanager.url=http://localhost:9093
   ```
   Check: within about 2 minutes, an email "[SafeFamily FIRING] TestAlert"
   arrives (check spam). It auto-resolves in about 5 minutes and a "RESOLVED"
   mail follows. No mail: `docker logs safefamily_alertmanager | grep -i notify`.

---

## Phase 2: Weekly encrypted backups (20 min)

7. - [ ] **Make the key pair on your laptop, not the server**:
   ```bash
   age-keygen -o safefamily-backup-key.txt     # prints "Public key: age1..."
   ```
   Check: you saved the private key file in **two** places off the server
   (password manager + USB stick/paper). Losing it makes every backup
   unreadable.

8. - [ ] **Install the public key and config on the server**:
   ```bash
   sudo mkdir -p /etc/safefamily /var/backups/safefamily
   echo 'age1...your public key...' | sudo tee /etc/safefamily/backup-recipients.txt
   sudo cp deploy/monitoring/backup.env.example /etc/safefamily/backup.env
   sudo chmod 600 /etc/safefamily/backup.env
   sudo nano /etc/safefamily/backup.env      # SAFEFAMILY_DIR, DOCKER_ROOT_DIR if needed
   ```
   Defaults: weekly backups, keep 8 weekly + 6 monthly.

9. - [ ] **Install the timers** (fix `ExecStart=` first if the checkout is not `/srv/SafeFamily`):
   ```bash
   sudo cp deploy/systemd/safefamily-backup.* deploy/systemd/safefamily-dirsize.* /etc/systemd/system/
   sudo sed -i 's#/srv/SafeFamily#'"$PWD"'#' /etc/systemd/system/safefamily-{backup,dirsize}.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now safefamily-backup.timer safefamily-dirsize.timer
   ```
   Check: `systemctl list-timers 'safefamily-*'` shows the backup's next run on a Sunday.

10. - [ ] **Run the first backup now**: `sudo systemctl start safefamily-backup.service`
    Check: `journalctl -u safefamily-backup.service -n 10` ends with `done in Ns`,
    and `sudo ls -l /var/backups/safefamily/weekly/` shows one `.dump.age` file.
    Within a minute, Grafana's "Last DB backup" tile shows a few minutes.

11. - [ ] **Restore drill** (proves the key and the backup both work). On your laptop:
    ```bash
    scp <server>:/var/backups/safefamily/weekly/safefamily-<stamp>.dump.age .
    age -d -i safefamily-backup-key.txt safefamily-<stamp>.dump.age \
        | ssh <server> 'cd /srv/SafeFamily && scripts/db_restore.sh -'
    ```
    Check: it prints row counts for every table, matching what you expect
    (users, todo_list, notes, ...). Then clean up:
    `ssh <server> docker exec safefamily_db dropdb -U <DB_USER> safefamily_restore_test`

12. - [ ] **Offsite copy**: add `/var/backups/safefamily/` to your existing backup
    script (it is already encrypted).
    Check: the newest `.dump.age` file shows up at the destination.

13. - [ ] **Final preflight**: `sudo scripts/monitoring/preflight.sh --deep`
    Check: 0 failures.

---

## Routine operations

| When | Do | Check |
|---|---|---|
| Any alert email | follow "First thing to check" in [monitoring.md](monitoring.md#2-alerts) | a RESOLVED mail arrives |
| Weekly (2 min) | glance at the Grafana dashboard | tiles green, "Last DB backup" < 8 days |
| Monthly (5 min) | confirm the offsite copy has the latest backup; `df -h` | newest file present; disks < 85% |
| Every 3 months (15 min) | restore drill (step 11) | row counts look right |
| After upgrading Docker, snap refresh, or OS | `sudo scripts/monitoring/preflight.sh --deep` | 0 failures; container panels still have data |
| After `git pull` that touches `deploy/monitoring/` | `docker compose up -d` | preflight "Running stack" all PASS |
| Yearly | check the private key copies still open: `age -d -i <key> <recent backup> > /dev/null` | no error |
| Certificate renewal | nothing; the TLS alert warns 14 days ahead | `TLSCertificateExpiringSoon` resolves |

Useful commands:

```bash
docker compose ps                                  # everything up?
docker compose logs --tail=50 <service>            # e.g. prometheus, alertmanager, cadvisor
systemctl list-timers 'safefamily-*'               # next backup
journalctl -u safefamily-backup.service -n 30      # last backup log
sudo ls -lh /var/backups/safefamily/{weekly,monthly}
sudo systemctl start safefamily-backup.service     # extra backup now (e.g. before an upgrade)
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker compose` errors `... must be set in .env` | missing `MAIL_ACCOUNT`, `MAIL_PASSWORD` or `GRAFANA_ADMIN_PASSWORD` | add it to `.env` |
| Container panels empty, `count(...)` tile shows 0 | cadvisor cannot reach containerd / Docker data | preflight; set `CONTAINERD_SOCKET` / `DOCKER_ROOT_DIR`; `docker compose up -d cadvisor` |
| node-exporter or cadvisor won't start: mount error | snap Docker confinement | host node-exporter fallback in monitoring.md |
| Website tile DOWN but the site works | self-signed cert, or the `server_name` in blackbox.yml differs from nginx | see Phase 0 table |
| No alert emails | Gmail app password, port 587 blocked | `docker logs safefamily_alertmanager \| grep -i notify` |
| "Last DB backup" tile "No data" | backup never ran, or metrics file unreadable | step 10; `MetricsFileUnreadable` alert; `ls -l /var/lib/node_exporter/textfile` |
| Backup log: `recipients file ... contains a PRIVATE key` | private key copied to the server | replace with the public `age1...` line; delete the private key from the server |
| Backup log: `container ... is not running` | db container down | `docker compose up -d db`, then step 10 |
| Grafana password forgotten | set only on first start | `docker exec -it safefamily_grafana grafana cli admin reset-admin-password <new>` |

---

## Turning it off

Monitoring only (the app keeps running):

```bash
docker compose -f docker-compose.yml -f deploy/monitoring/docker-compose.monitoring.yml \
    rm -sf prometheus alertmanager grafana node-exporter cadvisor postgres-exporter nginx-exporter blackbox-exporter
# then remove the COMPOSE_FILE line from .env
```

Backups: `sudo systemctl disable --now safefamily-backup.timer safefamily-dirsize.timer`.
Existing backup files stay in `/var/backups/safefamily/`.
