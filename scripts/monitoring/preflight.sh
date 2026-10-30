#!/usr/bin/env bash
# Check that this host can run the SafeFamily monitoring stack and encrypted
# backups, and print the fix for anything that is missing. Read-only: it
# changes nothing. Run from the repository root on the server:
#
#   scripts/monitoring/preflight.sh            # quick checks
#   scripts/monitoring/preflight.sh --deep     # also test the container mounts
#                                              # cadvisor/node-exporter need
#                                              # (pulls two small images)
#
# Some checks read root-only paths; run with sudo for the complete picture.
# Exit status is 1 if any check FAILs. See docs/operations-checklist.md.

set -uo pipefail

deep=0
[[ "${1:-}" == "--deep" ]] && deep=1

repo="$(cd "$(dirname "$0")/../.." && pwd)"
overlay="deploy/monitoring/docker-compose.monitoring.yml"
backup_env="/etc/safefamily/backup.env"
fails=0
warns=0

if [[ -t 1 ]]; then
    G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' B=$'\e[1m' N=$'\e[0m'
else
    G="" Y="" R="" B="" N=""
fi
pass() { printf '  %sPASS%s  %s\n' "$G" "$N" "$1"; }
warn() { printf '  %sWARN%s  %s\n' "$Y" "$N" "$1"; [[ -n "${2:-}" ]] && printf '        fix: %s\n' "$2"; warns=$((warns + 1)); }
fail() { printf '  %sFAIL%s  %s\n' "$R" "$N" "$1"; [[ -n "${2:-}" ]] && printf '        fix: %s\n' "$2"; fails=$((fails + 1)); }
info() { printf '  info  %s\n' "$1"; }
section() { printf '\n%s%s%s\n' "$B" "$1" "$N"; }
# version_ge A B: true when version A >= B
version_ge() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]; }

# Settings from the backup env file, if readable, else defaults.
BACKUP_DIR=/var/backups/safefamily
BACKUP_AGE_RECIPIENTS=/etc/safefamily/backup-recipients.txt
NODE_EXPORTER_TEXTFILE_DIR=/var/lib/node_exporter/textfile
if [[ -r "$backup_env" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$backup_env"
    set +a
fi

cd "$repo" || exit 1

section "Host"
if [[ "$(uname -s)" == "Linux" ]]; then
    pass "Linux $(uname -r)"
else
    fail "$(uname -s) host: node-exporter and cadvisor need Linux to see the real disks and containers" \
         "run the stack on the Linux server; Docker Desktop only shows its VM"
fi
if [[ -d /run/systemd/system ]]; then
    pass "systemd is running (backup timers)"
else
    warn "no systemd: the backup timers cannot be installed" "use the cron line in docs/monitoring.md"
fi
mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
if (( mem_kb >= 2 * 1024 * 1024 )); then
    pass "RAM $((mem_kb / 1024)) MiB (stack needs ~600 MiB)"
else
    warn "RAM $((mem_kb / 1024)) MiB: monitoring adds ~600 MiB" "lower PROMETHEUS_RETENTION or skip cadvisor"
fi

section "Docker"
if ! command -v docker >/dev/null; then
    fail "docker CLI not found" "install Docker Engine: https://docs.docker.com/engine/install/"
else
    if ! docker info >/dev/null 2>&1; then
        fail "cannot talk to the Docker daemon as $(id -un)" \
             "run with sudo, or: sudo usermod -aG docker $(id -un) && log out and back in"
    else
        server="$(docker version -f '{{.Server.Version}}' 2>/dev/null)"
        if version_ge "$server" "24.0"; then
            pass "Docker Engine $server"
        else
            warn "Docker Engine $server is old (tested on 29.x)" "upgrade Docker; if you stay, watch cadvisor logs"
        fi

        root_dir="$(docker info -f '{{.DockerRootDir}}' 2>/dev/null)"
        if [[ "$root_dir" == /var/snap/* ]] || { command -v snap >/dev/null && snap list docker >/dev/null 2>&1; }; then
            if (( deep )); then
                info "Docker is installed from snap; the --deep mount tests below show whether its confinement allows the exporters"
            else
                warn "Docker is installed from snap, whose confinement can block the exporters' host mounts" \
                     "rerun with --deep to test them"
            fi
        fi
        if [[ "$root_dir" == "/var/lib/docker" ]]; then
            pass "Docker root dir /var/lib/docker (default, no DOCKER_ROOT_DIR needed)"
        else
            warn "Docker root dir is $root_dir" "add to .env: DOCKER_ROOT_DIR=$root_dir"
        fi

        driver="$(docker info -f '{{.Driver}}' 2>/dev/null)"
        if docker info 2>/dev/null | grep -q "io.containerd.snapshotter"; then
            info "image store: containerd snapshotter ($driver) -> cadvisor must reach containerd"
            sock=""
            for candidate in /run/containerd/containerd.sock /run/snap.docker/containerd/containerd.sock \
                             /run/docker/containerd/containerd.sock /var/snap/docker/common/run/containerd/containerd.sock; do
                [[ -S "$candidate" ]] && { sock="$candidate"; break; }
            done
            if [[ "$sock" == "/run/containerd/containerd.sock" ]]; then
                pass "containerd socket at /run/containerd/containerd.sock (cadvisor finds it)"
            elif [[ -n "$sock" && ( "$sock" == /run/* || "$sock" == /var/run/* ) ]]; then
                if [[ "${CONTAINERD_SOCKET:-}" == "$sock" ]] \
                    || docker compose config 2>/dev/null | grep -q -- "--containerd=$sock"; then
                    pass "containerd socket at $sock, and CONTAINERD_SOCKET points cadvisor to it"
                else
                    warn "containerd socket is at $sock, not where cadvisor looks" "add to .env: CONTAINERD_SOCKET=$sock"
                fi
            elif [[ -n "$sock" ]]; then
                warn "containerd socket is at $sock, outside /run, so cadvisor cannot see it" \
                     "add under cadvisor.volumes in $overlay: - $(dirname "$sock"):/run/host-containerd:ro and to .env: CONTAINERD_SOCKET=/run/host-containerd/containerd.sock"
            else
                warn "containerd socket not found (run with sudo to search root-only paths)" \
                     "sudo find /run /var/snap -name containerd.sock"
            fi
        else
            pass "image store: classic $driver (cadvisor reads layer metadata directly)"
        fi
        info "cgroup v$(docker info -f '{{.CgroupVersion}}' 2>/dev/null), driver $(docker info -f '{{.CgroupDriver}}' 2>/dev/null)"
    fi
fi

section "Docker Compose"
if docker compose version >/dev/null 2>&1; then
    cv="$(docker compose version --short 2>/dev/null | sed 's/^v//')"
    if version_ge "$cv" "2.20"; then
        pass "Compose v$cv"
    else
        warn "Compose v$cv is old (tested on 5.x)" "upgrade the docker-compose-plugin package"
    fi
    if docker compose -f docker-compose.yml -f "$overlay" config --quiet 2>/tmp/preflight-compose.$$; then
        pass "docker-compose.yml + monitoring overlay parse with your .env"
    else
        fail "compose files do not parse with your .env:"
        sed 's/^/          /' /tmp/preflight-compose.$$
        printf '        fix: set the variables named above in .env (see .env.example)\n'
    fi
    rm -f /tmp/preflight-compose.$$
    if docker compose config --services 2>/dev/null | grep -qx prometheus; then
        pass "COMPOSE_FILE includes the monitoring overlay (plain 'docker compose' manages it)"
    else
        warn "plain 'docker compose' does not include monitoring" \
             "add to .env: COMPOSE_FILE=docker-compose.yml:$overlay"
    fi
else
    if command -v docker-compose >/dev/null; then
        fail "only legacy docker-compose v1 found" "install the Compose v2 plugin: sudo apt install docker-compose-plugin"
    else
        fail "Docker Compose not found" "sudo apt install docker-compose-plugin"
    fi
fi

section "Ports and disk"
listening() { ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$1\$"; }
for port in 3000 9090; do
    owner=""
    command -v docker >/dev/null && owner="$(docker ps --filter "publish=$port" --format '{{.Names}}' 2>/dev/null)"
    if [[ -n "$owner" ]]; then
        pass "port $port is used by $owner"
    elif listening "$port"; then
        fail "port $port is already taken by another program" "free it, or change the host port in $overlay"
    else
        pass "port $port is free"
    fi
done
for dir in "${root_dir:-/var/lib/docker}" "$(dirname "$BACKUP_DIR")"; do
    [[ -d "$dir" ]] || continue
    avail_kb="$(df -Pk "$dir" 2>/dev/null | awk 'NR==2 {print $4}')"
    pct="$(df -P "$dir" 2>/dev/null | awk 'NR==2 {gsub("%", "", $5); print 100 - $5}')"
    if (( avail_kb >= 10 * 1024 * 1024 )) && (( pct >= 15 )); then
        pass "$dir: $((avail_kb / 1024 / 1024)) GiB free (${pct}%)"
    else
        warn "$dir: only $((avail_kb / 1024 / 1024)) GiB (${pct}%) free; Prometheus keeps up to 5 GB" \
             "free space (README 'Prune Cache') or set PROMETHEUS_RETENTION_SIZE=2GB in .env"
    fi
done

section "TLS certificate and outbound mail"
cert=/etc/ssl/certs/safefamily.crt
if [[ -r "$cert" ]] && command -v openssl >/dev/null; then
    end="$(openssl x509 -in "$cert" -noout -enddate 2>/dev/null | cut -d= -f2)"
    if openssl x509 -in "$cert" -noout -checkend $((14 * 86400)) >/dev/null 2>&1; then
        pass "certificate valid until $end"
    else
        warn "certificate expires within 14 days ($end)" "renew it before enabling the TLS alert"
    fi
    subject="$(openssl x509 -in "$cert" -noout -subject 2>/dev/null | sed 's/^subject=//')"
    issuer="$(openssl x509 -in "$cert" -noout -issuer 2>/dev/null | sed 's/^issuer=//')"
    if [[ "$subject" == "$issuer" ]]; then
        warn "certificate is self-signed: the website probe will report DOWN" \
             "use Let's Encrypt, or set insecure_skip_verify: true in deploy/monitoring/blackbox/blackbox.yml"
    else
        pass "certificate issued by ${issuer}"
    fi
else
    warn "cannot read $cert (run with sudo)"
fi
if timeout 5 bash -c 'exec 3<>/dev/tcp/smtp.gmail.com/587' 2>/dev/null; then
    pass "can reach smtp.gmail.com:587 for alert mail"
else
    warn "cannot reach smtp.gmail.com:587: alert emails will not arrive" \
         "check the firewall/ISP; set ALERT_SMTP_SMARTHOST in .env for another mail server"
fi

section "Encrypted backups"
if command -v age >/dev/null; then
    pass "age $(age --version 2>/dev/null)"
else
    fail "age not installed" "sudo apt install age"
fi
if [[ -r "$BACKUP_AGE_RECIPIENTS" ]]; then
    if grep -q "AGE-SECRET-KEY" "$BACKUP_AGE_RECIPIENTS"; then
        fail "$BACKUP_AGE_RECIPIENTS contains a PRIVATE key" \
             "replace it with only the public key (age1...) and move the private key off this server"
    elif grep -q "^age1" "$BACKUP_AGE_RECIPIENTS"; then
        pass "$BACKUP_AGE_RECIPIENTS has $(grep -c '^age1' "$BACKUP_AGE_RECIPIENTS") public key(s)"
    else
        fail "$BACKUP_AGE_RECIPIENTS has no age1... public key" "see 'One-time setup' in docs/monitoring.md"
    fi
elif [[ -e "$BACKUP_AGE_RECIPIENTS" ]]; then
    warn "$BACKUP_AGE_RECIPIENTS exists but is not readable (run with sudo)"
else
    fail "$BACKUP_AGE_RECIPIENTS missing" "create it with your age public key (docs/monitoring.md)"
fi
if [[ -r "$backup_env" ]]; then
    pass "$backup_env present"
else
    warn "$backup_env not found or not readable (defaults apply)" "sudo cp deploy/monitoring/backup.env.example $backup_env"
fi
for dir in "$BACKUP_DIR" "$NODE_EXPORTER_TEXTFILE_DIR"; do
    if [[ -d "$dir" ]]; then pass "$dir exists"; else fail "$dir missing" "sudo mkdir -p $dir"; fi
done
if [[ -d /run/systemd/system ]]; then
    for unit in safefamily-backup.timer safefamily-dirsize.timer; do
        if [[ "$(systemctl is-enabled "$unit" 2>/dev/null)" == "enabled" ]]; then
            next="$(systemctl show "$unit" -p NextElapseUSecRealtime --value 2>/dev/null)"
            pass "$unit enabled${next:+ (next run: $next)}"
        else
            fail "$unit not enabled" "sudo systemctl enable --now $unit (after copying deploy/systemd/${unit%.timer}.*)"
        fi
        svc="/etc/systemd/system/${unit%.timer}.service"
        if [[ -r "$svc" ]]; then
            exe="$(sed -n 's/^ExecStart=//p' "$svc" | awk '{print $1}')"
            if [[ -x "$exe" ]]; then
                pass "$(basename "$svc") runs $exe"
            else
                fail "$(basename "$svc") runs $exe, which does not exist" \
                     "edit ExecStart to $repo/scripts/..., then sudo systemctl daemon-reload"
            fi
        fi
    done
fi
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx safefamily_db; then
    pass "safefamily_db is running (backups can dump it)"
else
    warn "safefamily_db is not running: backups will fail until it is" "docker compose up -d db"
fi

if (( deep )); then
    section "Container mounts (--deep)"
    try_mount() { # $1 description, rest: docker run args
        local what="$1"; shift
        if out="$(docker run --rm "$@" 2>&1)"; then
            pass "$what"
        else
            fail "$what: ${out##*$'\n'}" "see 'Host-specific notes' in docs/monitoring.md"
        fi
    }
    try_mount "node-exporter can mount / read-only" \
        -v /:/host:ro --entrypoint /bin/ls prom/node-exporter:v1.9.1 /host/etc/hostname
    try_mount "node-exporter can read the textfile dir" \
        -v "$NODE_EXPORTER_TEXTFILE_DIR:/textfile:ro" --entrypoint /bin/ls prom/node-exporter:v1.9.1 /textfile
    try_mount "cadvisor can mount /sys, /var/run and the Docker root" \
        --privileged -v /sys:/sys:ro -v /var/run:/var/run:ro -v "${root_dir:-/var/lib/docker}:/var/lib/docker:ro" \
        --entrypoint /bin/ls gcr.io/cadvisor/cadvisor:v0.54.1 /var/lib/docker
fi

section "Running stack (skipped when monitoring is not up yet)"
if curl -fsS --max-time 3 http://127.0.0.1:9090/-/ready >/dev/null 2>&1; then
    if targets="$(curl -fsS --max-time 5 http://127.0.0.1:9090/api/v1/targets | python3 -c '
import json, sys
for t in json.load(sys.stdin)["data"]["activeTargets"]:
    state = "PASS" if t["health"] == "up" else "FAIL"
    print("  %s  scrape %s: %s %s" % (state, t["labels"]["job"], t["health"], t["lastError"][:120]))
')"; then
        echo "$targets"
        if grep -q "FAIL" <<< "$targets"; then fails=$((fails + 1)); fi
    else
        fail "could not read scrape targets from Prometheus"
    fi
    if ! firing="$(curl -fsS --max-time 5 http://127.0.0.1:9090/api/v1/alerts | python3 -c '
import json, sys
alerts = json.load(sys.stdin)["data"]["alerts"]
print(", ".join(sorted({a["labels"]["alertname"] for a in alerts if a["state"] == "firing"})))
')"; then
        fail "could not read alerts from Prometheus"
    elif [[ -z "$firing" ]]; then
        pass "no alerts firing"
    else
        warn "alerts firing: $firing" "see the alert table in docs/monitoring.md"
    fi
else
    info "Prometheus is not reachable on 127.0.0.1:9090; rerun after 'docker compose up -d'"
fi

printf '\n%sSummary:%s %d failure(s), %d warning(s)\n' "$B" "$N" "$fails" "$warns"
(( fails == 0 ))
