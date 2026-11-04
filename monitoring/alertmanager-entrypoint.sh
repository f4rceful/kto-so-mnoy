#!/bin/sh
set -eu

printf '%s' "${METRICS_TOKEN:-}" > /tmp/alert-token

exec /bin/alertmanager \
  --config.file=/etc/alertmanager/alertmanager.yml \
  --storage.path=/alertmanager
