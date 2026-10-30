#!/usr/bin/env bash
# Full, encrypted backup of the SafeFamily Postgres database.
#
# Dumps every table (including logs and media, unlike scripts/db_export.py)
# in pg_dump custom format, checks the dump is readable, and encrypts it with
# age to one or more PUBLIC keys. Only public keys live on this host, so a
# stolen server or backup disk cannot be used to read the backups; decrypting
# needs the private key you keep elsewhere (see docs/monitoring.md).
#
# Run on the host (it uses `docker exec`), weekly via
# deploy/systemd/safefamily-backup.timer or cron. Settings come from the
# environment, typically /etc/safefamily/backup.env:
#
#   BACKUP_DIR              where backups go       (/var/backups/safefamily)
#   BACKUP_AGE_RECIPIENTS   file of age public keys (/etc/safefamily/backup-recipients.txt)
#   BACKUP_KEEP_WEEKLY      weekly backups to keep  (8)
#   BACKUP_KEEP_MONTHLY     monthly backups to keep (6)
#   BACKUP_DB_CONTAINER     Postgres container      (safefamily_db)
#   NODE_EXPORTER_TEXTFILE_DIR  metrics for Prometheus (/var/lib/node_exporter/textfile)

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/safefamily}"
RECIPIENTS="${BACKUP_AGE_RECIPIENTS:-/etc/safefamily/backup-recipients.txt}"
KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-8}"
KEEP_MONTHLY="${BACKUP_KEEP_MONTHLY:-6}"
CONTAINER="${BACKUP_DB_CONTAINER:-safefamily_db}"
TEXTFILE_DIR="${NODE_EXPORTER_TEXTFILE_DIR:-/var/lib/node_exporter/textfile}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
name="safefamily-${stamp}.dump.age"
container_tmp="/tmp/safefamily-backup-${stamp}.dump"
start_ts="$(date +%s)"
partial=""

log() { echo "[db_backup] $*" >&2; }

write_metrics() {
    # $1 = 1 on success, 0 on failure. Written atomically so node_exporter
    # never reads a half-written file.
    [[ -d "$TEXTFILE_DIR" ]] || return 0
    local prom="$TEXTFILE_DIR/safefamily_backup.prom"
    local now
    now="$(date +%s)"
    {
        echo "# HELP safefamily_backup_last_run_success 1 if the last backup run succeeded."
        echo "# TYPE safefamily_backup_last_run_success gauge"
        echo "safefamily_backup_last_run_success $1"
        echo "# HELP safefamily_backup_last_run_timestamp_seconds When the last backup run finished."
        echo "# TYPE safefamily_backup_last_run_timestamp_seconds gauge"
        echo "safefamily_backup_last_run_timestamp_seconds $now"
        if [[ "$1" == 1 ]]; then
            echo "# HELP safefamily_backup_last_success_timestamp_seconds When the last successful backup finished."
            echo "# TYPE safefamily_backup_last_success_timestamp_seconds gauge"
            echo "safefamily_backup_last_success_timestamp_seconds $now"
            echo "# HELP safefamily_backup_last_size_bytes Size of the last encrypted backup."
            echo "# TYPE safefamily_backup_last_size_bytes gauge"
            echo "safefamily_backup_last_size_bytes $(stat -c %s "$BACKUP_DIR/weekly/$name")"
            echo "# HELP safefamily_backup_last_duration_seconds How long the last backup took."
            echo "# TYPE safefamily_backup_last_duration_seconds gauge"
            echo "safefamily_backup_last_duration_seconds $((now - start_ts))"
        elif [[ -f "$prom" ]]; then
            # Keep the previous success time so the "backup too old" alert
            # still measures from the last good backup.
            grep -E '^safefamily_backup_last_(success_timestamp_seconds|size_bytes|duration_seconds) ' "$prom" || true
        fi
    } > "$prom.tmp"
    # Readable by node_exporter (runs as nobody); the umask below is for backups.
    chmod 644 "$prom.tmp"
    mv "$prom.tmp" "$prom"
}

cleanup() {
    local status=$?
    docker exec "$CONTAINER" rm -f "$container_tmp" >/dev/null 2>&1 || true
    [[ -n "$partial" ]] && rm -f "$partial"
    if [[ $status -ne 0 ]]; then
        log "FAILED (exit $status)"
        write_metrics 0 || true
    fi
}
trap cleanup EXIT

command -v age >/dev/null || { log "age is not installed (apt install age)"; exit 1; }
[[ -s "$RECIPIENTS" ]] || { log "recipients file $RECIPIENTS is missing or empty"; exit 1; }
if grep -q "AGE-SECRET-KEY" "$RECIPIENTS"; then
    log "$RECIPIENTS contains a PRIVATE key; it must only hold public keys (age1...)"
    exit 1
fi

umask 077
mkdir -p "$BACKUP_DIR/weekly" "$BACKUP_DIR/monthly"

# Dump inside the container using its own POSTGRES_* env, so the DB password
# never passes through this script. pg_restore --list proves the archive is
# complete and readable before it is encrypted.
log "dumping database from $CONTAINER"
docker exec "$CONTAINER" sh -c \
    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 --file="$1" \
     && pg_restore --list "$1" > /dev/null' \
    sh "$container_tmp"

partial="$BACKUP_DIR/weekly/.$name.partial"
docker exec "$CONTAINER" cat "$container_tmp" | age --encrypt --recipients-file "$RECIPIENTS" --output "$partial"
mv "$partial" "$BACKUP_DIR/weekly/$name"
partial=""
log "wrote $BACKUP_DIR/weekly/$name ($(du -h "$BACKUP_DIR/weekly/$name" | cut -f1))"

# Keep the first backup of each month for longer. A hard link costs no space.
month="${stamp:0:6}"
if ! compgen -G "$BACKUP_DIR/monthly/safefamily-${month}*.dump.age" > /dev/null; then
    ln "$BACKUP_DIR/weekly/$name" "$BACKUP_DIR/monthly/$name"
    log "kept as monthly backup for ${month}"
fi

# Keep the newest N of each set, by count rather than age, so a long run of
# failed backups never prunes away the last good ones. Names sort
# chronologically.
prune() {
    local dir="$1" keep="$2" old
    find "$dir" -name 'safefamily-*.dump.age' -printf '%f\n' | sort -r \
        | tail -n "+$((keep + 1))" | while read -r old; do
            rm -f "$dir/$old"
            log "pruned $(basename "$dir") backup $old"
        done
}
prune "$BACKUP_DIR/weekly" "$KEEP_WEEKLY"
prune "$BACKUP_DIR/monthly" "$KEEP_MONTHLY"

write_metrics 1
log "done in $(($(date +%s) - start_ts))s"
