#!/usr/bin/env bash
# Parse-only (Phase 1) over 3 SPb zones, concurrent C=20. Resumable & hole-safe
# (only successful cells cache; failures re-fetch on a re-run). Research is launched
# separately once parsing is complete and proxy quota is sufficient.

ROOT="/c/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
cd "$ROOT" || exit 1
PY="uv run python"
EXP="$ROOT/yandex_enrichment_experiment"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

ZONES=(
  "petrogradka|59.965900|30.311728|2500"
  "optikov|59.998787|30.224594|2000"
  "kirovsky|59.869442|30.272305|2000"
)

log "=== ensure api up ==="
docker compose up -d redis >/dev/null 2>&1
pm2 start ecosystem.config.js --only scraper-api >/dev/null 2>&1 || true
for _ in $(seq 1 40); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:8000/healthz)" = "200" ] && break
  sleep 3
done

for z in "${ZONES[@]}"; do
  IFS='|' read -r name lat lon rad <<< "$z"
  dir="$EXP/data_2026-06-10_$name"
  mkdir -p "$dir"
  log "=== [PARSE] $name (center $lat,$lon r=${rad}m, C=20) -> $dir ==="
  COLLECT_REVIEWS=both GRID_CONCURRENCY=20 \
    YA_CENTER_LAT="$lat" YA_CENTER_LON="$lon" YA_RADIUS_M="$rad" \
    YA_DATA_DIR="$dir" PYTHONIOENCODING=utf-8 $PY "$EXP/01_scrape_yandex.py" \
    > "$dir/parse.log" 2>&1
  log "  [PARSE] $name finished (rc=$?). dedup..."
  YA_DATA_DIR="$dir" PYTHONIOENCODING=utf-8 $PY "$EXP/01b_dedup.py" > "$dir/dedup.log" 2>&1
  n=$($PY -c "import json; print(json.load(open(r'$dir/organizations_dedup.json',encoding='utf-8'))['total_after_dedup'])" 2>/dev/null || echo '?')
  log "  [PARSE] $name unique after dedup: $n"
done
log "=== PARSE PHASE DONE (all 3 zones). Research is launched separately. ==="
