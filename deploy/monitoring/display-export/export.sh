#!/bin/sh
# Render the "SafeFamily Display" Grafana dashboard to a PNG for the P4
# display, every DISPLAY_INTERVAL seconds (--once: a single run).
#
# Each run: Grafana's /render API (backed by the grafana-renderer service)
# -> a hidden temp file in the export folder -> check it is a PNG of the
# right size -> rename over one fixed file name, so readers never see a
# partial file and old files never pile up. A failed run leaves the last good
# picture in place; the display's STALE banner then shows it is old.
#
#   GRAFANA_URL               http://grafana:3000/grafana (Grafana's sub path)
#   GRAFANA_USER / GRAFANA_PASSWORD   a Grafana login (default admin user)
#   DISPLAY_DASHBOARD_UID     safefamily-display
#   DISPLAY_WIDTH / DISPLAY_HEIGHT    1280 / 800
#   DISPLAY_TZ                time zone for the timeline, e.g. America/Toronto
#   DISPLAY_INTERVAL          seconds between exports (300); after a failed
#                             export it retries after DISPLAY_RETRY (60) instead
#   DISPLAY_FILE              file name in the export folder (grafana-status.png)
#   DISPLAY_EXPORT_REQUIRE_FSTYPE  only write when the export folder is this
#                             filesystem type, e.g. cifs; "" = any
#   EXPORT_DIR                export folder inside the container (/export)
set -u

GRAFANA_URL="${GRAFANA_URL:-http://grafana:3000/grafana}"
UID_="${DISPLAY_DASHBOARD_UID:-safefamily-display}"
WIDTH="${DISPLAY_WIDTH:-1280}"
HEIGHT="${DISPLAY_HEIGHT:-800}"
INTERVAL="${DISPLAY_INTERVAL:-300}"
RETRY="${DISPLAY_RETRY:-60}"
FILE="${DISPLAY_FILE:-grafana-status.png}"
DIR="${EXPORT_DIR:-/export}"
REQUIRE_FSTYPE="${DISPLAY_EXPORT_REQUIRE_FSTYPE-cifs}"
TMP="$DIR/.$FILE.tmp"

log() { echo "[display-export] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }

# Filesystem type of the export folder, from this process's mount table.
fstype_of() {
    awk -v m="$1" '{ for (i = 1; i <= NF; i++) if ($i == "-") { if ($5 == m) t = $(i + 1); break } } END { print t }' \
        /proc/self/mountinfo
}

# PNG signature and IHDR width/height (big-endian, bytes 17-24).
png_size() {
    sig="$(head -c 8 "$1" | od -An -tx1 | tr -d ' \n')"
    [ "$sig" = "89504e470d0a1a0a" ] || return 1
    dims="$(head -c 24 "$1" | tail -c 8 | od -An -tu1)"
    # shellcheck disable=SC2086  # split the eight byte values on purpose
    set -- $dims
    echo "$(( ($1 << 24) + ($2 << 16) + ($3 << 8) + $4 ))x$(( ($5 << 24) + ($6 << 16) + ($7 << 8) + $8 ))"
}

export_once() {
    if [ -n "$REQUIRE_FSTYPE" ]; then
        actual="$(fstype_of "$DIR")"
        case "|$REQUIRE_FSTYPE|" in
            *"|$actual|"*) ;;
            *)
                log "not writing: $DIR is '${actual:-not a mount}', expected $REQUIRE_FSTYPE (share not mounted when this container started? docker compose restart display-export)"
                return 1 ;;
        esac
    fi
    url="$GRAFANA_URL/render/d/$UID_?orgId=1&width=$WIDTH&height=$HEIGHT&kiosk=true&theme=dark&timeout=60"
    [ -n "${DISPLAY_TZ:-}" ] && url="$url&tz=$DISPLAY_TZ"
    if ! curl -fsS --max-time 120 -u "${GRAFANA_USER:-admin}:${GRAFANA_PASSWORD:-}" -o "$TMP" "$url"; then
        log "render request failed"
        rm -f "$TMP"
        return 1
    fi
    size="$(png_size "$TMP")" || { log "Grafana did not return a PNG"; rm -f "$TMP"; return 1; }
    if [ "$size" != "${WIDTH}x${HEIGHT}" ]; then
        log "PNG is $size, expected ${WIDTH}x${HEIGHT}"
        rm -f "$TMP"
        return 1
    fi
    mv -f "$TMP" "$DIR/$FILE" && log "wrote $DIR/$FILE ($size, $(wc -c < "$DIR/$FILE") bytes)"
}

# Grafana answers /api/health once it is ready (no login needed).
wait_for_grafana() {
    tries=0
    until curl -fsS --max-time 5 -o /dev/null "$GRAFANA_URL/api/health" 2> /dev/null; do
        tries=$((tries + 1))
        [ "$tries" -eq 1 ] && log "waiting for Grafana at $GRAFANA_URL"
        [ "$tries" -ge 60 ] && { log "Grafana still not ready after 5 minutes, trying anyway"; return 0; }
        sleep 5
    done
}

if [ "${1:-}" = "--once" ]; then
    export_once
    exit $?
fi
wait_for_grafana
while :; do
    if export_once; then
        sleep "$INTERVAL"
    else
        # Retry soon so one failure does not make the display go STALE.
        sleep "$RETRY"
    fi
done
