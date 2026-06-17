#!/usr/bin/env bash
# Full 3-zone run (restored scope, quota now ~6GB). Parse and research never overlap
# (both use the proxy pool). Begovaya(optikov) is already parsing as an orphan; we wait
# for it, then parse Kirovsky, then research 100 orgs/zone (NO_TELEGRAM). Petrogradka
# is already parsed — only its research is queued.

ROOT="/c/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
cd "$ROOT" || exit 1
PY="uv run python"
EXP="$ROOT/yandex_enrichment_experiment"
PET="$EXP/data_2026-06-10_petrogradka"
OPT="$EXP/data_2026-06-10_optikov"      # Begovaya
KIR="$EXP/data_2026-06-10_kirovsky"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ---------- PHASE A: parse (proxy, no GPU) ----------
log "=== wait for Begovaya(optikov) parse+reviews to finish ==="
for _ in $(seq 1 300); do
  grep -q "Concurrent reviews done" "$OPT/parse.log" 2>/dev/null && break
  sleep 30
done
log "  Begovaya parse done. grid: $(ls "$OPT/raw_grid" 2>/dev/null | wc -l)/6025"

log "=== [PARSE] Kirovsky (59.869442,30.272305 r=2000m, C=20) ==="
mkdir -p "$KIR"
COLLECT_REVIEWS=both GRID_CONCURRENCY=20 \
  YA_CENTER_LAT=59.869442 YA_CENTER_LON=30.272305 YA_RADIUS_M=2000 \
  YA_DATA_DIR="$KIR" PYTHONIOENCODING=utf-8 $PY "$EXP/01_scrape_yandex.py" > "$KIR/parse.log" 2>&1
log "  Kirovsky parse done (rc=$?). grid: $(ls "$KIR/raw_grid" 2>/dev/null | wc -l)/6025"

log "=== dedup all 3 zones ==="
for d in "$PET" "$OPT" "$KIR"; do
  YA_DATA_DIR="$d" PYTHONIOENCODING=utf-8 $PY "$EXP/01b_dedup.py" > "$d/dedup.log" 2>&1
  n=$($PY -c "import json;print(json.load(open(r'$d/organizations_dedup.json',encoding='utf-8'))['total_after_dedup'])" 2>/dev/null || echo '?')
  log "  $(basename "$d") unique: $n"
done

# ---------- PHASE B: research (proxy + GPU) ----------
log "=== start q8 llama + worker ==="
docker compose up -d redis >/dev/null 2>&1
pm2 start ecosystem.config.js --only scraper-api >/dev/null 2>&1 || true
pm2 start ecosystem.llama-deep.config.js >/dev/null 2>&1 || pm2 restart llama-server >/dev/null 2>&1
pm2 start ecosystem.config.js --only taskiq-worker >/dev/null 2>&1 || pm2 restart taskiq-worker >/dev/null 2>&1
for _ in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:20022/health)" = "200" ] && { log "  llama healthy"; break; }
  sleep 3
done
sleep 5

# Begovaya first (current focus), then Petrogradka, then Kirovsky.
for z in "optikov|$OPT" "petrogradka|$PET" "kirovsky|$KIR"; do
  IFS='|' read -r name dir <<< "$z"
  log "=== [RESEARCH] $name — 100 orgs (NO_TELEGRAM=1, concurrency=3) ==="
  LIMIT=100 NO_TELEGRAM=1 CONCURRENCY=3 \
    YA_DATA_DIR="$dir" YA_RESEARCH_DIR="$dir/research" PYTHONIOENCODING=utf-8 \
    $PY "$EXP/02_research_orgs.py" > "$dir/research.log" 2>&1
  log "  [RESEARCH] $name done — $(ls "$dir/research/"*.json 2>/dev/null | wc -l) cards"
done
log "=== ALL DONE: 3 zones parsed + 100/zone enriched ==="
