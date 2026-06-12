#!/usr/bin/env bash
# Full-pipeline run over 3 new SPb geo-points (2026-06-10).
# Phase 1 (no GPU): parse grid + reviews + dedup for all 3 zones.
# Phase 2 (GPU):     start q8 llama + worker, research 100 orgs/zone (NO_TELEGRAM).
# Resumable: grid cells + reviews + research are cached per file; re-running skips done work.

ROOT="/c/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
cd "$ROOT" || exit 1
PY="uv run python"
EXP="$ROOT/yandex_enrichment_experiment"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# name|lat|lon|radius_m
ZONES=(
  "petrogradka|59.965900|30.311728|2500"
  "optikov|59.998787|30.224594|2000"
  "kirovsky|59.869442|30.272305|2000"
)

dir_for() { echo "$EXP/data_2026-06-10_$1"; }

wait_health() {  # url label
  for _ in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "$1" 2>/dev/null)
    [ "$code" = "200" ] && { log "  $2 healthy"; return 0; }
    sleep 3
  done
  log "  !! $2 NOT healthy after 180s ($1)"; return 1
}

log "=== bringing up redis + api (parse needs api) ==="
docker compose up -d redis >/dev/null 2>&1
pm2 start ecosystem.config.js --only scraper-api >/dev/null 2>&1 || pm2 restart scraper-api >/dev/null 2>&1
wait_health "http://localhost:8000/healthz" "scraper-api" || exit 1

# ---------- PHASE 1: parse + reviews + dedup (no GPU) ----------
for z in "${ZONES[@]}"; do
  IFS='|' read -r name lat lon rad <<< "$z"
  dir="$(dir_for "$name")"
  mkdir -p "$dir"
  log "=== [PARSE] $name (center $lat,$lon r=${rad}m, C=20) -> $dir ==="
  COLLECT_REVIEWS=both GRID_CONCURRENCY=20 \
    YA_CENTER_LAT="$lat" YA_CENTER_LON="$lon" YA_RADIUS_M="$rad" \
    YA_DATA_DIR="$dir" PYTHONIOENCODING=utf-8 $PY "$EXP/01_scrape_yandex.py" \
    > "$dir/parse.log" 2>&1
  log "  [PARSE] $name done (rc=$?). dedup..."
  YA_DATA_DIR="$dir" PYTHONIOENCODING=utf-8 $PY "$EXP/01b_dedup.py" > "$dir/dedup.log" 2>&1
  n=$($PY -c "import json,sys; print(json.load(open(r'$dir/organizations_dedup.json',encoding='utf-8'))['total_after_dedup'])" 2>/dev/null || echo "?")
  log "  [PARSE] $name unique orgs after dedup: $n"
done

# ---------- PHASE 2: start GPU, research 100/zone ----------
log "=== starting q8 llama + worker for research ==="
pm2 start ecosystem.llama-deep.config.js >/dev/null 2>&1 || pm2 restart llama-server >/dev/null 2>&1
pm2 start ecosystem.config.js --only taskiq-worker >/dev/null 2>&1 || pm2 restart taskiq-worker >/dev/null 2>&1
wait_health "http://localhost:20022/health" "llama-q8" || exit 1
sleep 5

for z in "${ZONES[@]}"; do
  IFS='|' read -r name lat lon rad <<< "$z"
  dir="$(dir_for "$name")"
  log "=== [RESEARCH] $name — 100 orgs (NO_TELEGRAM=1, concurrency=3) ==="
  LIMIT=100 NO_TELEGRAM=1 CONCURRENCY=3 \
    YA_DATA_DIR="$dir" YA_RESEARCH_DIR="$dir/research" PYTHONIOENCODING=utf-8 \
    $PY "$EXP/02_research_orgs.py" > "$dir/research.log" 2>&1
  done=$(ls "$dir/research/"*.json 2>/dev/null | wc -l)
  log "  [RESEARCH] $name done — $done cards in $dir/research/"
done

log "=== ALL DONE: 3 zones parsed + 100/zone researched ==="
