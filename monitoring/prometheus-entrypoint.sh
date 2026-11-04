#!/bin/sh
set -eu

printf '%s' "${METRICS_TOKEN:-}" > /tmp/metrics-token

if [ -n "${PUBLIC_URL:-}" ]; then
  printf '[{"targets":["%s/api/health"]}]' "${PUBLIC_URL%/}" > /tmp/public-targets.json
else
  printf '[]' > /tmp/public-targets.json
fi

exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --storage.tsdb.retention.time=30d
