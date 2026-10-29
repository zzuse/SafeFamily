#!/usr/bin/env bash
# Report the size of the directories SafeFamily grows on the host, for the
# "Directory sizes" Grafana panel. node_exporter reads the .prom file from its
# textfile directory. Run every 15 minutes by
# deploy/systemd/safefamily-dirsize.timer.
#
#   SAFEFAMILY_DIR              the repository checkout (default: this script's repo)
#   BACKUP_DIR                  encrypted backups (/var/backups/safefamily)
#   DOCKER_ROOT_DIR             Docker data incl. the Postgres volume (/var/lib/docker;
#                               snap Docker: /var/snap/docker/common/var-lib-docker)
#   NODE_EXPORTER_TEXTFILE_DIR  output directory (/var/lib/node_exporter/textfile)
#   DIR_SIZES_EXTRA             more directories, space separated

set -euo pipefail

repo="${SAFEFAMILY_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
docker_root="${DOCKER_ROOT_DIR:-/var/lib/docker}"
out_dir="${NODE_EXPORTER_TEXTFILE_DIR:-/var/lib/node_exporter/textfile}"

dirs=(
    "$repo"
    "$repo/logs"
    "${BACKUP_DIR:-/var/backups/safefamily}"
    "$docker_root/volumes"
    "$docker_root/containers"
    "/var/log/journal"
)
# shellcheck disable=SC2206  # intentional word splitting
dirs+=(${DIR_SIZES_EXTRA:-})

mkdir -p "$out_dir"
{
    echo "# HELP safefamily_dir_size_bytes Disk usage of a directory (du)."
    echo "# TYPE safefamily_dir_size_bytes gauge"
    for dir in "${dirs[@]}"; do
        [[ -d "$dir" ]] || continue
        bytes="$(du -sxb "$dir" 2>/dev/null | cut -f1 || true)"
        [[ -n "$bytes" ]] && echo "safefamily_dir_size_bytes{path=\"$dir\"} $bytes"
    done
} > "$out_dir/safefamily_dir_sizes.prom.tmp"
mv "$out_dir/safefamily_dir_sizes.prom.tmp" "$out_dir/safefamily_dir_sizes.prom"
