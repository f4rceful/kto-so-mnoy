#!/bin/sh
set -eu

project="${COMPOSE_PROJECT_NAME:-kto-so-mnoy}"
dir="${1:-backups}"
stamp="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$dir"

docker compose exec -T db pg_dump -U kto kto_so_mnoy | gzip > "$dir/database-$stamp.sql.gz"
echo "database: $dir/database-$stamp.sql.gz"

for volume in grafana-data prometheus-data loki-data alertmanager-data; do
  if docker volume inspect "${project}_${volume}" > /dev/null 2>&1; then
    docker run --rm -v "${project}_${volume}:/data:ro" -v "$(cd "$dir" && pwd):/backup" alpine \
      tar czf "/backup/${volume}-${stamp}.tar.gz" -C /data .
    echo "$volume: $dir/${volume}-${stamp}.tar.gz"
  fi
done
