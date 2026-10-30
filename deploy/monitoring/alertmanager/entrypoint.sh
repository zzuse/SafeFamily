#!/bin/sh
# Render alertmanager.yml.tmpl with values from the environment, then start
# Alertmanager. Values are single-quoted in the template, so a ' inside a
# value is doubled to stay valid YAML.
set -eu

# Unset or empty ALERT_EMAIL_TO: mail the sending account itself.
: "${ALERT_EMAIL_TO:=$MAIL_ACCOUNT}"
export ALERT_EMAIL_TO

out=/tmp/alertmanager.yml
awk '{
    while (match($0, /\$\{[A-Z_]+\}/)) {
        name = substr($0, RSTART + 2, RLENGTH - 3)
        value = ENVIRON[name]
        gsub(/'\''/, "'\'''\''", value)
        $0 = substr($0, 1, RSTART - 1) value substr($0, RSTART + RLENGTH)
    }
    print
}' /etc/alertmanager/alertmanager.yml.tmpl > "$out"
chmod 600 "$out"

exec /bin/alertmanager \
    --config.file="$out" \
    --storage.path=/alertmanager \
    "$@"
