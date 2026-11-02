#!/usr/bin/env bash
# Check that this host can run the SafeFamily monitoring stack and encrypted
# backups, and print the fix for anything that is missing. Read-only: it
# changes nothing. Run from the repository root on the server:
#
#   sudo scripts/monitoring/preflight.sh           # quick checks
#   sudo scripts/monitoring/preflight.sh --deep    # also test the container
#                                                  # mounts cadvisor and
#                                                  # node-exporter need (pulls
#                                                  # their images if missing)
#
# sudo is optional but some files it checks are root-only. Exit status is 1
# if any check FAILs. See docs/operations-checklist.md.

set -uo pipefail

deep=0
case "${1:-}" in
    "") ;;
    --deep|-d) deep=1 ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (use --deep or --help)" >&2; exit 2 ;;
esac

repo="$(cd "$(dirname "$0")/../.." && pwd)"
overlay="deploy/monitoring/docker-compose.monitoring.yml"
host_ne_overlay="deploy/monitoring/docker-compose.host-node-exporter.yml"
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
    # Read only the settings used here, in a subshell, so nothing else from
    # the file leaks into this script's environment (and into the docker
    # compose calls, where it would hide a missing .env setting).
    eval "$(
        # shellcheck disable=SC1090
        . "$backup_env" >/dev/null 2>&1
        for v in BACKUP_DIR BACKUP_AGE_RECIPIENTS NODE_EXPORTER_TEXTFILE_DIR WATCH_MOUNTS; do
            [[ -n "${!v:-}" ]] && printf '%s=%q\n' "$v" "${!v}"
        done
    )"
fi

cd "$repo" || exit 1

if (( EUID != 0 )); then
    printf 'Note: not running as root, so root-only files may be reported missing.\n'
    printf '      For the full picture: sudo %s%s\n' "$0" "$([[ $deep == 1 ]] && echo ' --deep')"
fi

# The merged compose config (main file + monitoring overlay, with .env
# applied), parsed once and queried by later checks. Holds secrets: only ever
# piped, never printed or written to disk.
cfg_json=""
cfg_err=""
compose_ok=0
load_compose_config() {
    local err_file
    err_file="$(mktemp)"
    # Use the user's COMPOSE_FILE when it includes monitoring (it may also add
    # the host node-exporter overlay); otherwise main file + monitoring overlay.
    if cfg_json="$(docker compose config --format json 2>/dev/null)" \
        && python3 -c 'import json,sys; sys.exit("prometheus" not in json.load(sys.stdin)["services"])' <<< "$cfg_json"; then
        compose_ok=1
    elif cfg_json="$(docker compose -f docker-compose.yml -f "$overlay" config --format json 2>"$err_file")"; then
        compose_ok=1
    fi
    # Drop compose's harmless "variable is not set" warnings for optional vars.
    cfg_err="$(grep -v 'level=warning' "$err_file")"
    rm -f "$err_file"
}
# cfg_value SERVICE KEY PREFIX: value of a "--flag=value" command argument
# (KEY=command) or the source of the volume mounted at PREFIX (KEY=volume).
cfg_value() {
    python3 -c '
import json, sys
svc, key, want = sys.argv[1:4]
s = json.load(sys.stdin)["services"].get(svc, {})
if key == "command":
    print(next((a.split("=", 1)[1] for a in s.get("command") or [] if a.startswith(want + "=")), ""))
else:
    print(next((v.get("source", "") for v in s.get("volumes") or [] if v.get("target") == want), ""))
' "$@" <<< "$cfg_json"
}
# host_ne: 1 when node-exporter runs on the host (host overlay in use).
host_ne=0
detect_host_ne() {
    (( compose_ok )) && python3 -c 'import json,sys; sys.exit("node-exporter" in json.load(sys.stdin)["services"])' <<< "$cfg_json" \
        && host_ne=1
}
# env_has NAME: .env defines NAME (checks the name only, never reads values).
env_has() { [[ -r .env ]] && grep -Eq "^[[:space:]]*(export[[:space:]]+)?$1=" .env; }

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

        docker compose version >/dev/null 2>&1 && load_compose_config && detect_host_ne
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
        elif (( compose_ok )); then
            mounted="$(cfg_value cadvisor volume /var/lib/docker)"
            if [[ "$mounted" == "$root_dir" ]]; then
                pass "Docker root dir $root_dir, and DOCKER_ROOT_DIR points cadvisor to it"
            else
                warn "Docker root dir is $root_dir but cadvisor would mount ${mounted:-nothing}" \
                     "add to .env: DOCKER_ROOT_DIR=$root_dir"
            fi
        elif env_has DOCKER_ROOT_DIR; then
            info "Docker root dir $root_dir; DOCKER_ROOT_DIR is in .env (verified once the compose error below is fixed)"
        else
            warn "Docker root dir is $root_dir" "add to .env: DOCKER_ROOT_DIR=$root_dir"
        fi

        driver="$(docker info -f '{{.Driver}}' 2>/dev/null)"
        if docker info 2>/dev/null | grep -q "io.containerd.snapshotter"; then
            info "image store: containerd snapshotter ($driver)"
        else
            info "image store: classic $driver"
        fi
        # cadvisor v0.54's Docker support always talks to containerd, whatever
        # the image store; without it containers have no names in Grafana.
        candidates=(/run/containerd/containerd.sock /run/docker/containerd/containerd.sock)
        # Snap Docker runs its own containerd; prefer it over a system one.
        if [[ "$root_dir" == /var/snap/* ]]; then
            candidates=(/run/snap.docker/containerd/containerd.sock
                        /var/snap/docker/common/run/containerd/containerd.sock "${candidates[@]}")
        fi
        sock=""
        for candidate in "${candidates[@]}"; do
            [[ -S "$candidate" ]] && { sock="$candidate"; break; }
        done
        if [[ "$sock" == "/run/containerd/containerd.sock" ]]; then
            pass "containerd socket at /run/containerd/containerd.sock (cadvisor finds it)"
        elif [[ -n "$sock" && ( "$sock" == /run/* || "$sock" == /var/run/* ) ]]; then
            if (( compose_ok )) && [[ "$(cfg_value cadvisor command --containerd)" == "$sock" ]]; then
                pass "containerd socket at $sock, and CONTAINERD_SOCKET points cadvisor to it"
            elif (( compose_ok )); then
                # Say why a CONTAINERD_SOCKET the user believes is set has no effect.
                why=""
                if env_has CONTAINERD_SOCKET; then
                    why=" (.env sets CONTAINERD_SOCKET, but a CONTAINERD_SOCKET variable in this shell overrides it: unset CONTAINERD_SOCKET)"
                elif [[ -r .env ]] && grep -Eq '^[[:space:]]*#.*CONTAINERD_SOCKET' .env; then
                    why=" (the CONTAINERD_SOCKET line in .env is commented out)"
                elif [[ -r "$backup_env" ]] && grep -q CONTAINERD_SOCKET "$backup_env"; then
                    why=" (CONTAINERD_SOCKET is in $backup_env, but Docker Compose only reads $repo/.env)"
                else
                    why=" ($repo/.env has no CONTAINERD_SOCKET line)"
                fi
                warn "containerd socket is at $sock, but cadvisor is set to $(cfg_value cadvisor command --containerd)$why" \
                     "put CONTAINERD_SOCKET=$sock in $repo/.env, then docker compose up -d cadvisor"
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
    if (( compose_ok )); then
        pass "docker-compose.yml + monitoring overlay parse with your .env"
    else
        fail "compose files do not parse with your .env:"
        while IFS= read -r line; do printf '          %s\n' "$line"; done <<< "$cfg_err"
        hint="set the variables named above in .env (see .env.example)"
        # Grafana's own variable names go in the compose file, not in .env.
        if grep -q GRAFANA_ADMIN_PASSWORD <<< "$cfg_err" && env_has GF_SECURITY_ADMIN_PASSWORD; then
            hint="your .env has GF_SECURITY_ADMIN_PASSWORD; rename it to GRAFANA_ADMIN_PASSWORD (the compose file maps it)"
        fi
        printf '        fix: %s\n' "$hint"
    fi
    if (( ! compose_ok )); then
        info "COMPOSE_FILE check skipped until the compose files parse"
    elif docker compose config --services 2>/dev/null | grep -qx prometheus; then
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

section "Monitoring prerequisites"
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
if [[ -d "$NODE_EXPORTER_TEXTFILE_DIR" ]]; then
    pass "$NODE_EXPORTER_TEXTFILE_DIR exists (node-exporter reads backup/dir-size metrics there)"
else
    fail "$NODE_EXPORTER_TEXTFILE_DIR missing (checklist Phase 1 step 2)" "sudo mkdir -p $NODE_EXPORTER_TEXTFILE_DIR"
fi
if (( host_ne )); then
    info "node-exporter runs on the host ($host_ne_overlay)"
    if curl -fsS --max-time 3 http://127.0.0.1:9100/metrics >/dev/null 2>&1; then
        pass "host node-exporter answers on :9100"
        # Which textfile dir it reads: its --collector.textfile.directory flag.
        # Match the process name only (the kernel truncates it to 15 chars:
        # "prometheus-node"), never other command lines that mention it.
        ne_args="$(pgrep -a '^(node_exporter|prometheus-node)' | head -1)"
        ne_dir="$(sed -n 's/.*--collector\.textfile\.directory[= ]\([^ ]*\).*/\1/p' <<< "$ne_args")"
        if [[ "$ne_dir" == "$NODE_EXPORTER_TEXTFILE_DIR" ]]; then
            pass "host node-exporter reads the textfile dir $ne_dir"
        else
            fail "host node-exporter reads textfile dir '${ne_dir:-its package default}', scripts write to $NODE_EXPORTER_TEXTFILE_DIR" \
                 "set ARGS=\"--collector.textfile.directory=$NODE_EXPORTER_TEXTFILE_DIR\" in /etc/default/prometheus-node-exporter, then: sudo systemctl restart prometheus-node-exporter"
        fi
    else
        fail "no node-exporter on the host at :9100" \
             "sudo apt install prometheus-node-exporter (see 'Snap Docker' in docs/monitoring.md)"
    fi
elif (( compose_ok )); then
    mounted_textfile="$(cfg_value node-exporter volume /textfile)"
    if [[ "$mounted_textfile" != "$NODE_EXPORTER_TEXTFILE_DIR" ]]; then
        fail "scripts write metrics to $NODE_EXPORTER_TEXTFILE_DIR but node-exporter reads $mounted_textfile" \
             "set the same NODE_EXPORTER_TEXTFILE_DIR in .env and in $backup_env"
    fi
fi
# Prometheus's volume lives under the Docker root dir and grows to its
# retention size, so check free space as it will be once that is used up.
# DiskSpaceLow fires below 15% free.
retention="5GB"
(( compose_ok )) && retention="$(cfg_value prometheus command --storage.tsdb.retention.size)"
retention_kb="$(python3 -c '
import re, sys
m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMGT]?)i?B?", sys.argv[1].strip(), re.I)
n, u = (float(m.group(1)), m.group(2).upper()) if m else (5.0, "G")
print(int(n * {"": 1 / 1024, "K": 1, "M": 1024, "G": 1024**2, "T": 1024**3}[u]))
' "${retention:-5GB}")"
for dir in "${root_dir:-/var/lib/docker}" "$(dirname "$BACKUP_DIR")"; do
    [[ -d "$dir" ]] || continue
    read -r size_kb avail_kb < <(df -Pk "$dir" 2>/dev/null | awk 'NR==2 {print $2, $4}')
    pct=$((avail_kb * 100 / size_kb))
    reserve_kb=0
    [[ "$dir" == "${root_dir:-/var/lib/docker}" ]] && reserve_kb=$retention_kb
    after_pct=$(((avail_kb - reserve_kb) * 100 / size_kb))
    msg="$dir: $((avail_kb / 1024 / 1024)) GiB free (${pct}%)"
    if (( reserve_kb == 0 )) || (( after_pct >= 15 )); then
        (( reserve_kb )) && msg+=", ${after_pct}% after Prometheus uses its ${retention}"
        if (( pct >= 15 )); then
            pass "$msg"
        else
            warn "$msg: DiskSpaceLow (<15%) will fire" "free space (README 'Prune Cache')"
        fi
    else
        # Largest retention that still leaves 15% free, in whole GB.
        fit_gb=$(((avail_kb - size_kb * 15 / 100) / 1024 / 1024))
        if (( fit_gb >= 1 )); then
            fix="add to .env: PROMETHEUS_RETENTION_SIZE=${fit_gb}GB (or free space: README 'Prune Cache')"
        else
            fix="free space first (README 'Prune Cache'); then set PROMETHEUS_RETENTION_SIZE=1GB in .env"
        fi
        warn "$msg, but only ${after_pct}% once Prometheus uses its ${retention}: DiskSpaceLow (<15%) would fire" "$fix"
    fi
done

if [[ -n "${WATCH_MOUNTS:-}" ]]; then
    section "Watched mounts (WATCH_MOUNTS)"
    # Where node-exporter's metrics can be read: the host exporter directly,
    # otherwise the container through Prometheus.
    ne_metrics=""
    if (( host_ne )); then
        ne_metrics="$(curl -fsS --max-time 10 http://127.0.0.1:9100/metrics 2>/dev/null)"
        ne_version="$(sed -n 's/^node_exporter_build_info{.*version="\([^"]*\)".*/\1/p' <<< "$ne_metrics" | head -1)"
        [[ -n "$ne_version" ]] && info "host node-exporter version $ne_version"
    fi
    for mnt in ${WATCH_MOUNTS}; do
        fstypes="$(findmnt -n -M "$mnt" -o FSTYPE 2>/dev/null | tr '\n' ' ')"
        real_fs="$(tr ' ' '\n' <<< "$fstypes" | grep -vx -e autofs -e '' | head -1)"
        if [[ -n "$real_fs" ]]; then
            pass "$mnt is mounted ($real_fs)"
        elif [[ "$fstypes" == *autofs* ]]; then
            fail "$mnt is only an automount placeholder: the share itself did not mount" \
                 "ls $mnt; sudo journalctl -b | grep -iE 'cifs|mount' | tail; check the server and the credentials file"
            continue
        else
            fail "$mnt is not a mount point" "check its /etc/fstab line, then: sudo mount $mnt"
            continue
        fi
        ok_file="$NODE_EXPORTER_TEXTFILE_DIR/safefamily_mounts.prom"
        if grep -q "mountpoint=\"$mnt\"} 1" "$ok_file" 2>/dev/null; then
            pass "watch check reports $mnt OK"
        else
            warn "watch check has no OK result for $mnt yet" "sudo systemctl start safefamily-dirsize.service, then rerun"
        fi
        # A sandboxed exporter service may not be allowed into /home.
        if (( host_ne )) && [[ "$mnt" == /home/* || "$mnt" == /root/* ]] && [[ -d /run/systemd/system ]]; then
            protect="$(systemctl show prometheus-node-exporter -p ProtectHome --value 2>/dev/null)"
            if [[ -n "$protect" && "$protect" != "no" ]]; then
                fail "prometheus-node-exporter runs with ProtectHome=$protect, so it cannot read $mnt" \
                     "sudo systemctl edit prometheus-node-exporter, add [Service] / ProtectHome=no, then sudo systemctl restart prometheus-node-exporter"
            fi
        fi
        if (( host_ne )); then
            lines="$(grep -F "mountpoint=\"$mnt\"" <<< "$ne_metrics")"
        else
            lines="$(curl -fsS --max-time 5 --get http://127.0.0.1:9090/api/v1/query \
                --data-urlencode "query={__name__=~\"node_filesystem_(size_bytes|device_error)\",mountpoint=\"$mnt\"}" 2>/dev/null \
                | python3 -c '
import json, sys
for r in json.load(sys.stdin)["data"]["result"]:
    print(r["metric"]["__name__"], r["value"][1])' 2>/dev/null)"
        fi
        if grep -q "node_filesystem_size_bytes" <<< "$lines"; then
            pass "node-exporter reports $mnt (Grafana and the share alerts can see it)"
        elif grep -qE 'node_filesystem_device_error.* 1$' <<< "$lines"; then
            # Usually a parent folder the exporter's user may not pass
            # through, e.g. a 750 home directory. Find which ones.
            ne_user="$(systemctl show prometheus-node-exporter -p User --value 2>/dev/null)"
            ne_user="${ne_user:-prometheus}"
            blocked=()
            if (( EUID == 0 )) && id "$ne_user" > /dev/null 2>&1; then
                dir=""
                IFS=/ read -ra parts <<< "${mnt#/}"
                for part in "${parts[@]::${#parts[@]}-1}"; do
                    dir+="/$part"
                    # Stop at the first one: everything below it looks
                    # blocked too until it is fixed, so rerun afterwards.
                    if ! runuser -u "$ne_user" -- test -x "$dir" 2> /dev/null; then
                        blocked+=("$dir")
                        break
                    fi
                done
            fi
            if (( ${#blocked[@]} )); then
                fail "node-exporter (user $ne_user) cannot pass through ${blocked[0]} to reach $mnt" \
                     "sudo setfacl -m u:$ne_user:x ${blocked[0]}  (pass-through only, it cannot list or read it; needs the acl package), wait a minute, rerun"
            else
                fail "node-exporter lists $mnt but cannot read it (device error)" \
                     "check: sudo -u $ne_user stat -f $mnt (run this preflight with sudo to find a blocking parent folder)"
            fi
        else
            fail "node-exporter does not report $mnt at all${ne_version:+ (version $ne_version)}" \
                 "its mount-point/fs-type filter skips it: compare 'prometheus-node-exporter --help 2>&1 | grep -A1 -E \"mount-points|fs-types\"' with $mnt ($real_fs); see docs/monitoring.md 'Samba share'"
        fi
    done
fi

adguard_env=/etc/safefamily/adguard.env
if [[ -e "$adguard_env" ]]; then
    section "AdGuard check"
    mode="$(stat -c '%a %U' "$adguard_env" 2>/dev/null)"
    if [[ "$mode" == "600 root" ]]; then
        pass "$adguard_env is root-only"
    else
        fail "$adguard_env is '$mode', but it holds the AdGuard password" "sudo chown root: $adguard_env && sudo chmod 600 $adguard_env"
    fi
    prom="$NODE_EXPORTER_TEXTFILE_DIR/safefamily_adguard.prom"
    last="$(sed -n 's/^safefamily_adguard_last_check_timestamp_seconds //p' "$prom" 2>/dev/null)"
    if [[ -z "$last" ]]; then
        fail "no AdGuard metrics yet in $prom" \
             "sudo systemctl enable --now safefamily-adguard.timer; journalctl -u safefamily-adguard.service -n 20"
    elif (( $(date +%s) - last > 300 )); then
        fail "the AdGuard check last ran $(( ($(date +%s) - last) / 60 )) minutes ago" "systemctl status safefamily-adguard.timer"
    elif grep -q '^safefamily_adguard_up 1' "$prom"; then
        pass "AdGuard answers with the configured login"
        while read -r domain value; do
            info "$domain is $([[ "$value" == 1 ]] && echo BLOCKED || echo allowed) right now"
        done < <(sed -n 's/^safefamily_adguard_domain_blocked{domain="\([^"]*\)"} \(.*\)$/\1 \2/p' "$prom")
    else
        fail "AdGuard does not answer, or rejects the login" \
             "check ADGUARD_HOSTPORT/USERNAME/PASSWORD in $adguard_env; journalctl -u safefamily-adguard.service -n 5"
    fi
fi

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

section "Encrypted backups (checklist Phase 2)"
backup_started=0
[[ -e /etc/safefamily || -d "$BACKUP_DIR" ]] && backup_started=1
if [[ -d /run/systemd/system ]] && systemctl list-unit-files 'safefamily-*' 2>/dev/null | grep -q safefamily; then
    backup_started=1
fi
if (( ! backup_started )); then
    if command -v age >/dev/null; then
        pass "age $(age --version 2>/dev/null) installed"
    else
        warn "age not installed" "sudo apt install age"
    fi
    warn "backups are not set up yet" "follow docs/operations-checklist.md Phase 2 (steps 7-13) when ready"
elif command -v age >/dev/null; then
    pass "age $(age --version 2>/dev/null)"
else
    fail "age not installed" "sudo apt install age"
fi
if (( backup_started )); then
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
    if [[ -d "$BACKUP_DIR" ]]; then pass "$BACKUP_DIR exists"; else fail "$BACKUP_DIR missing" "sudo mkdir -p $BACKUP_DIR"; fi
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
fi
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx safefamily_db; then
    pass "safefamily_db is running (backups can dump it)"
else
    warn "safefamily_db is not running: backups will fail until it is" "docker compose up -d db"
fi

if (( deep )); then
    section "Container mounts (--deep)"
    ne_image=prom/node-exporter:v1.9.1
    # docker run's errors end with a "Run 'docker run --help'" footer; keep
    # the lines that say what actually went wrong.
    show_error() {
        grep -v -e "^Run 'docker run --help'" -e '^[[:space:]]*$' <<< "$1" | tail -n 3 \
            | sed -e 's/^docker: //' -e 's/^/        error: /'
    }
    # try_run DESCRIPTION FIX DOCKER-RUN-ARGS...: PASS, or FAIL with the real error.
    try_run() {
        local what="$1" fix="$2"
        shift 2
        if out="$(docker run --rm "$@" 2>&1)"; then
            pass "$what"
            return 0
        fi
        fail "$what"
        show_error "$out"
        printf '        fix: %s\n' "$fix"
        return 1
    }
    snap_note="Docker from snap is confined; see 'Host-specific notes' in docs/monitoring.md"
    host_mode_fix="run node-exporter on the host: 'Snap Docker' in docs/monitoring.md (apt install prometheus-node-exporter + add $host_ne_overlay to COMPOSE_FILE)"
    root_ok=1

    # 1. node-exporter measures disks through a read-only mount of /. Under
    # some confinement setups / inside containers is not the host's root, and
    # every disk number (and alert) for / would be wrong.
    if (( host_ne )); then
        info "node-exporter runs on the host, so its container mount tests are skipped"
    elif host_root_kb="$(df -Pk / | awk 'NR==2 {print $2}')" \
        && try_run "node-exporter can mount / read-only" "$snap_note" \
            -v /:/host:ro --entrypoint /bin/ls "$ne_image" /host/etc/hostname; then
        seen_kb="$(docker run --rm -v /:/host:ro --entrypoint /bin/df "$ne_image" -Pk /host 2>/dev/null \
            | awk 'NR==2 {print $2}')"
        if [[ -n "$seen_kb" ]] && (( seen_kb * 100 / host_root_kb >= 99 && seen_kb * 100 / host_root_kb <= 101 )); then
            pass "containers see the host's real / ($((host_root_kb / 1024 / 1024)) GiB), so disk metrics are right"
        else
            root_ok=0
            fail "containers see a different / (${seen_kb:-?} KiB) than the host ($host_root_kb KiB): disk metrics for / would be wrong" \
                 "$host_mode_fix"
        fi
    fi

    # 2. The textfile directory: the scripts write metrics there and
    # node-exporter reads them. Test the directory compose really mounts.
    textfile_src="$NODE_EXPORTER_TEXTFILE_DIR"
    (( compose_ok )) && textfile_src="$(cfg_value node-exporter volume /textfile)"
    snap_textfile=/var/snap/docker/common/node_exporter_textfile
    if (( host_ne )); then
        :
    elif (( ! root_ok )); then
        info "textfile mount test skipped: running node-exporter on the host (fix above) also solves it"
    elif [[ ! -d "$textfile_src" ]]; then
        warn "textfile dir $textfile_src does not exist yet, so it cannot be test-mounted" \
             "sudo mkdir -p $textfile_src, then rerun"
    elif ! try_run "node-exporter can read the textfile dir $textfile_src" \
            "see the suggestion below" \
            -v "$textfile_src:/textfile:ro" --entrypoint /bin/ls "$ne_image" /textfile; then
        # Snap Docker can always use its own data area under /var/snap/docker/common.
        if [[ -d /var/snap/docker/common ]] && docker run --rm -v /var/snap/docker/common:/probe:ro \
                --entrypoint /bin/ls "$ne_image" /probe >/dev/null 2>&1; then
            info "Docker can mount /var/snap/docker/common, so use a textfile dir there:"
            info "  sudo mkdir -p $snap_textfile"
            info "  add to .env:                    NODE_EXPORTER_TEXTFILE_DIR=$snap_textfile"
            info "  add to /etc/safefamily/backup.env: NODE_EXPORTER_TEXTFILE_DIR=$snap_textfile"
            info "  then: docker compose up -d node-exporter, and rerun this check"
        else
            info "$snap_note"
        fi
    fi

    # 3. cadvisor's host mounts.
    try_run "cadvisor can mount /sys, /var/run and the Docker root" "$snap_note" \
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
    # nginx-exporter is "up" even when it cannot reach nginx's status page;
    # nginx_up says whether it actually got data.
    nginx_up="$(curl -fsS --max-time 5 --get http://127.0.0.1:9090/api/v1/query \
        --data-urlencode 'query=nginx_up' 2>/dev/null \
        | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "")' 2>/dev/null)"
    if [[ "$nginx_up" == "1" ]]; then
        pass "nginx status page answers (Requests/s and Connections panels have data)"
    else
        # The config is a single-file bind mount: after git pull the container
        # keeps the old file until it is recreated (a reload is not enough).
        host_has="$(grep -c 'stub_status' deploy/nginx/nginx.docker.conf 2>/dev/null)"
        cont_has="$(docker exec safefamily_proxy grep -c 'stub_status' /etc/nginx/conf.d/default.conf 2>/dev/null)"
        if [[ "${host_has:-0}" != "0" && "${cont_has:-0}" == "0" ]]; then
            fail "nginx is running an old copy of deploy/nginx/nginx.docker.conf (no status page): nginx panels empty" \
                 "docker compose up -d --force-recreate proxy   (a reload does not pick up the new file)"
        else
            fail "nginx-exporter gets no data from http://proxy:8080/stub_status" \
                 "docker compose logs --tail=20 nginx-exporter proxy"
        fi
    fi

    # cadvisor can be up yet unable to tell which container is which (its
    # Docker integration failed); then the container panels and the
    # ContainerDown alert have nothing to go on.
    named="$(curl -fsS --max-time 5 --get http://127.0.0.1:9090/api/v1/query \
        --data-urlencode 'query=count(container_last_seen{name=~"safefamily_(app|db|proxy)"})' 2>/dev/null \
        | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else 0)' 2>/dev/null)"
    if [[ "${named:-0}" == "3" ]]; then
        pass "cadvisor sees app, db and proxy by name"
    elif grep -q "PASS  scrape cadvisor" <<< "${targets:-}"; then
        fail "cadvisor is up but sees ${named:-0} of app/db/proxy by name: container panels empty, ContainerDown fires"
        # The decisive lines first: why the docker factory failed, or why a
        # container could not be attached; else any other recent error.
        cad_all="$(docker logs --tail 500 safefamily_cadvisor 2>&1)"
        cad_log="$(grep -E 'docker container factory failed|Failed to create existing container' <<< "$cad_all" | tail -n 2)"
        [[ -n "$cad_log" ]] || cad_log="$(grep -iE 'fail|error|unable' <<< "$cad_all" \
            | grep -viE 'crio|podman|perf_event|resctrl|product_name|gce\.go' | tail -n 3)"
        while IFS= read -r line; do [[ -n "$line" ]] && printf '        log: %s\n' "${line:0:220}"; done <<< "$cad_log"
        if grep -qi containerd <<< "$cad_log"; then
            hint="set CONTAINERD_SOCKET in .env to the socket preflight finds (Docker section), then docker compose up -d cadvisor"
        elif grep -qiE 'layerdb|read-write layer|mount-id' <<< "$cad_log"; then
            hint="cadvisor cannot read Docker's layer data under /rootfs$root_dir: see 'cadvisor without container names' in docs/monitoring.md"
        elif grep -qi 'docker.sock' <<< "$cad_log"; then
            hint="cadvisor cannot reach the Docker socket: check the /var/run mount in $overlay"
        else
            hint="see 'cadvisor without container names' in docs/monitoring.md"
        fi
        printf '        fix: %s\n' "$hint"
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
