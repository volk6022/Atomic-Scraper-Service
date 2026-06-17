#!/usr/bin/env bash
# Wait for the already-running Беговая (optikov) parse to finish, then dedup +
# enrich 100 orgs (NO_TELEGRAM). Does NOT touch the running parser — only watches
# its log. Research starts after parse so parse/research don't contend for proxies.

ROOT="/c/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
cd "$ROOT" || exit 1
PY="uv run python"
EXP="$ROOT/yandex_enrichment_experiment"
OPT="$EXP/data_2026-06-10_optikov"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== waiting for Беговая (optikov) parse+reviews to finish ==="
for _ in $(seq 1 300); do   # up to ~2.5h
  if grep -q "Concurrent reviews done" "$OPT/parse.log" 2>/dev/null; then
    break
  fi
  sleep 30
done
log "  parse signal seen. grid cells: $(ls "$OPT/raw_grid" 2>/dev/null | wc -l)/6025"

log "=== dedup ==="
YA_DATA_DIR="$OPT" PYTHONIOENCODING=utf-8 $PY "$EXP/01b_dedup.py" > "$OPT/dedup.log" 2>&1
n=$($PY -c "import json; print(json.load(open(r'$OPT/organizations_dedup.json',encoding='utf-8'))['total_after_dedup'])" 2>/dev/null || echo '?')
log "  unique after dedup: $n"

log "=== start q8 llama + worker for enrichment ==="
pm2 start ecosystem.llama-deep.config.js >/dev/null 2>&1 || pm2 restart llama-server >/dev/null 2>&1
pm2 start ecosystem.config.js --only taskiq-worker >/dev/null 2>&1 || pm2 restart taskiq-worker >/dev/null 2>&1
for _ in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 http://localhost:20022/health)" = "200" ] && { log "  llama healthy"; break; }
  sleep 3
done
sleep 5

log "=== ENRICHMENT: 100 orgs Беговая (NO_TELEGRAM=1, concurrency=3) ==="
LIMIT=100 NO_TELEGRAM=1 CONCURRENCY=3 \
  YA_DATA_DIR="$OPT" YA_RESEARCH_DIR="$OPT/research" PYTHONIOENCODING=utf-8 \
  $PY "$EXP/02_research_orgs.py" > "$OPT/research.log" 2>&1
done=$(ls "$OPT/research/"*.json 2>/dev/null | wc -l)
log "=== DONE: $done enriched cards in $OPT/research/ ==="
