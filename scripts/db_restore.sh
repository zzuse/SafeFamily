#!/usr/bin/env bash
# Restore a backup made by scripts/db_backup.sh.
#
#   scripts/db_restore.sh -i ~/safefamily-backup-key.txt BACKUP.dump.age
#       Restores into a scratch database (safefamily_restore_test) and prints
#       row counts: a safe restore drill that leaves the live data alone.
#
#   scripts/db_restore.sh -i KEY --into-live BACKUP.dump.age
#       Replaces the live database's contents after you type its name. Stop
#       the app first: docker compose stop app
#
# Without -i the file must already be decrypted (a plain .dump). To avoid
# copying the private key to the server, decrypt on the machine that holds it
# and stream the result ("-" reads stdin; --confirm DBNAME replaces the typed
# confirmation, since stdin carries the backup):
#   age -d -i key.txt BACKUP.dump.age | ssh server 'cd SafeFamily && scripts/db_restore.sh -'
#   age -d -i key.txt BACKUP.dump.age \
#       | ssh server 'cd SafeFamily && scripts/db_restore.sh --into-live --confirm logdb -'

set -euo pipefail

CONTAINER="${BACKUP_DB_CONTAINER:-safefamily_db}"
TEST_DB="safefamily_restore_test"
identity=""
into_live=0
confirm=""

usage() { sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--identity) identity="$2"; shift 2 ;;
        --into-live) into_live=1; shift ;;
        --confirm) confirm="$2"; shift 2 ;;
        -h|--help) usage ;;
        -) break ;;
        -*) echo "unknown option $1" >&2; usage ;;
        *) break ;;
    esac
done
[[ $# -eq 1 ]] || usage
backup="$1"

live_db="$(docker exec "$CONTAINER" sh -c 'echo "$POSTGRES_DB"')"
if [[ $into_live -eq 1 ]]; then
    target="$live_db"
    if [[ -z "$confirm" ]]; then
        # Ask on the terminal, not stdin: stdin may be carrying the backup.
        read -r -p "This REPLACES all data in database '$target'. Type the database name to continue: " \
            confirm < /dev/tty
    fi
    [[ "$confirm" == "$target" ]] || { echo "aborted: confirmation does not match '$target'" >&2; exit 1; }
else
    target="$TEST_DB"
fi

stream() {
    if [[ "$backup" == "-" ]]; then
        cat
    elif [[ -n "$identity" ]]; then
        age --decrypt --identity "$identity" "$backup"
    else
        cat "$backup"
    fi
}

if [[ $into_live -eq 0 ]]; then
    docker exec "$CONTAINER" sh -c \
        'dropdb -U "$POSTGRES_USER" --if-exists "$1" && createdb -U "$POSTGRES_USER" "$1"' sh "$target"
fi

echo "restoring into database '$target'..." >&2
# --clean --if-exists makes a live restore replace existing objects; on the
# fresh scratch database it is a harmless no-op.
stream | docker exec -i "$CONTAINER" sh -c \
    'pg_restore -U "$POSTGRES_USER" -d "$1" --clean --if-exists --no-owner --exit-on-error' sh "$target"

echo "restored. Row counts:" >&2
docker exec "$CONTAINER" sh -c 'psql -U "$POSTGRES_USER" -d "$1" -c "
    SELECT table_name AS table, (xpath(\$\$/row/c/text()\$\$, query_to_xml(
        format(\$\$SELECT count(*) AS c FROM %I.%I\$\$, table_schema, table_name),
        false, true, \$\$\$\$)))[1]::text::bigint AS rows
    FROM information_schema.tables
    WHERE table_schema = \$\$public\$\$ AND table_type = \$\$BASE TABLE\$\$
    ORDER BY 1"' sh "$target"
if [[ $into_live -eq 0 ]]; then
    echo "Drop the scratch database when done: docker exec $CONTAINER dropdb -U \"\$DB_USER\" $TEST_DB" >&2
fi
