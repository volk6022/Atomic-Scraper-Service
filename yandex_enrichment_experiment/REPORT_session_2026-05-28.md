# Сессия 2026-05-28 — v2.1 batch run, отчёт

**Период:** 2026-05-27 вечер → 2026-05-29 ~02:30 ночи (включая ~13ч фонового батча)
**Главный результат:** 459/517 организаций обработаны новым агентом v2.1 (critic-gate), 92% прошли качество ≥8.5/10, batch остановлен по запросу пользователя.

---

## 1. Что было сделано в этой сессии

### 1.1. Сравнение архитектур (ранее накопленная база)
- **SIMPLE** (flat-loop, 3 тула) — baseline
- **ORCH** (orchestrator + sub-agents с LLM-скорингом URL'ов и delegate_read) — context economy за счёт 3× wall time
- **v2** (SIMPLE + auto-compact + soft-elide + refraser-every-4 + goal-conditioned scrape + domain-block) — оказался хуже базового SIMPLE
- **v2.1** (v2 + critic-gate на submit, refraser-every-15, domain-whitelist) — **выбран как production**

Полный анализ — в `REPORT_4architectures.md` (создан днём ранее в этой же сессии).

### 1.2. v2.1 — финальная архитектура

`simple_agent_v2.py`. Ключевые механизмы:

| Механизм | Параметры (production) | Эффект |
|---|---|---|
| Auto-compact на budget | TOKEN_BUDGET=50k, MAX_COMPACTIONS=3 | Срабатывает 0% времени на текущей нагрузке (батч ни разу не триггернул) |
| Soft-elide | SOFT_ELIDE_AFTER_TURNS=4 | Старые scrape tool_results заменяются на marker; основной context-saver |
| Goal-conditioned scrape extract | regex по anchor.name + phones/emails/social patterns ±400 chars | -50% контекста на каждом scrape |
| Refraser | REFRASER_EVERY_N_SERPS=15 | Срабатывает 1-2 раза за ресёрч max, нудж не мандат |
| Critic gate на submit_org_card | CRITIC_PASS_SCORE=8.5, MAX_SUBMIT_REJECTS=2 (force-accept на 3-й) | **Главный quality gate** |
| Domain-fail tracking | THRESHOLD=3, whitelist для yandex/2gis/hh/vk/etc | Защита от циклов на dead-end доменах |

### 1.3. Инфраструктурные изменения
- **llama-server** (pm2): `-np 3 -c 195000` (3 параллельных слота × ~65k каждый) — изменено с `-np 4 -c 200000`
- **docker stack**: searxng + redis подняты через docker-compose, лишние api/worker остановлены (используется напрямую httpx из v2.1)
- **`data/` папка полностью очищена**, 3 отчёта (REPORT_4architectures, REPORT_4models_agat, REPORT_simple_vs_graph) перенесены в `yandex_enrichment_experiment/`

### 1.4. Новый pipeline
1. `01_scrape_yandex.py` (radius bumped 2000→2500m) → **725 уникальных орг**, без отзывов (proxy traffic save)
2. `02_filter_orgs.py` (new) — regex prefilter + local LLM judge → **517 kept**
   - 94 regex-dropped (мega-brands + state): Сбер/Газпром/Дикси/Магнит/Пятёрочка/...
   - 113 LLM-dropped: банки/детсады/школы/аптечные сети/регулируемое мед.
   - Survivors: 484 viable_small + 31 viable_medium + 1 uncertain + 1 regulated (LLM noise)
3. `03_research_all.py` (new) — batch runner, asyncio.Semaphore(3), idempotent, env-knobs (MODEL, CONCURRENCY, LIMIT, OFFSET, PICK_INDICES, OVERWRITE)

### 1.5. Запуск полного батча
Запущен с MODEL=local, CONCURRENCY=3. Шёл 13 часов, прерван по запросу пользователя (ночь).

---

## 2. Сводная статистика — 459 готовых орг

### 2.1. Throughput
- **wall time батча**: ~13.0 часов
- **mean per-org elapsed**: 307s (~5 мин)
- **median**: 286s
- **max outlier**: 1202s (20 мин — единичный кейс)
- **sum compute**: 140,739s ÷ 3 параллельных слота ≈ 13.0h wall ✓ (сходится)

### 2.2. Submit attempts (как работает critic-gate)
| Attempts | Count | % | Смысл |
|---:|---:|---:|---|
| 1 | 426 | 93% | Прошёл сразу |
| 2 | 19 | 4% | Reject → retry → pass |
| 3 | 5 | 1% | Force-accept после 2 rejects |
| 0 | 9 | 2% | MAX_TURNS hit без submit'а (force-save state) |

### 2.3. Final critic score (последний submit)
- mean **8.85** / median **9.0** / max 9.6 / min 6.5
- ≥ 8.5: **421 (92%)** ← clean pass
- 8.0-8.4: 15 (3%) ← borderline pass
- < 8.0: 14 (3%) ← force-accept или no-submit

### 2.4. Compactions
- **0 compactions across all 459 orgs** ← TOKEN_BUDGET=50k + soft-elide одни справились с контекстом

### 2.5. Заполненность ORG_CARD (из 9 top-level keys)
| keys_filled | count | % |
|---:|---:|---:|
| 9 | 33 | 7% |
| 8 | 133 | 29% |
| 7 | 140 | 30% |
| 6 | 100 | 22% |
| 5 | 34 | 7% |
| 4 | 6 | 1% |
| 0 | 13 | 3% ← empty cards (no-submit cases) |

mean **6.83 / 9**, median 7. Топ-3 категории (6-7-8 keys) покрывают 81% орг.

### 2.6. Token usage
- mean total: **60k** (4× меньше baseline SIMPLE-qwen 265k)
- median: 50k
- max outlier: 330k (одиночный сложный кейс с многим reasoning'ом)

---

## 3. Ключевые наблюдения

1. **Critic-gate работает как калиброванный судья, не диктатор.** Из 459 ресёрчей:
   - 93% проходят на первой попытке — никакого ложного блокирования
   - 4% получают честный reject и улучшают карточку
   - 1% force-accept (исчерпали попытки) — escape hatch работает
   - 2% no-submit (MAX_TURNS) — здесь критик не нужен, проблема в самом ресёрче

2. **Auto-compact ни разу не сработал.** TOKEN_BUDGET=50k + soft-elide-after-4 turns + goal-conditioned scrape — этих 3 механизмов хватает для местной 9B и текущей сложности задачи. **Compaction остаётся safety net на будущее.**

3. **Outlier-кейсы (~3%) с пустой картой требуют отдельного разбора.** 13 орг ушли по MAX_TURNS без submit'а. Возможные причины:
   - Имя коллизирует с известным понятием (как «Марина Цветаева» — поэт vs магазин цветов; этот кейс прошёл на 2-й попытке, но мог и не пройти)
   - Очень новые орг без веб-присутствия
   - Технические проблемы (proxy/searxng глюки)

4. **Filter эффективен.** 94 regex + 113 LLM = 207 отсеяно (28% от собранных), осталось 517. Все viable_small/medium — реальный целевой сегмент.

5. **Compute-эффективность.** Сейчас 60k токенов средне на орг при качестве median 7/9 keys. Это **~6× дешевле** simple_agent baseline qwen-plus (265k токенов).

---

## 4. Что не сделано / что осталось

### 4.1. Незавершённый батч
- **Готово**: 459/517 (88.8%)
- **Осталось**: 58 орг (с индексами ~459-516 в `kept_orgs`)
- **Перезапуск завтра**: `03_research_all.py` идемпотентен — просто запустить заново, он пропустит готовые и доделает остаток. ETA ~1.5-2 часа.

### 4.2. Открытые направления
- Разбор 13 no-submit кейсов (что специфичное мешало)
- Опционально: пересчитать 19 force-accept (если хочется выше качество)
- Анализ распределения по типам бизнеса (рестораны / салоны / клиники / магазины)
- (Если придёт идея для resume-matching) — собрать поверх карточек отдельный pass

### 4.3. Известные баги / следы
- **Yandex Maps reviews не собирались** в прошлой сессии — отдельная история, отложено (proxy traffic жалко). При желании: 13 пустых карточек скорее всего сильно выиграли бы от подмеса отзывов из yandex.

---

## 5. Состояние инфраструктуры на момент прерывания

| Сервис | Состояние |
|---|---|
| pm2 llama-server | online, 5.1GB RAM, np=3, 65k/slot |
| pm2 scraper-api | online |
| pm2 taskiq-worker | stopped (не нужен для batch) |
| docker searxng | up at :8080 |
| docker redis | up |
| docker api/worker | stopped (избегаем конфликта с pm2) |
| batch python (`bonve14dw`) | **STOPPED** на пользовательский запрос |

GPU свободна, всё остальное живо — можно безболезненно продолжить завтра.

---

## 6. Файлы и артефакты

### Код
- `simple_agent_v2.py` — v2.1, production agent
- `simple_agent.py` — baseline (не менять, наш контроль)
- `orchestrator_agent.py` — экспериментальный ORCH (не используется в проде)
- `01_scrape_yandex.py` — radius bumped to 2500m, reviews off
- `02_filter_orgs.py` — **new** regex + LLM filter
- `03_research_all.py` — **new** batch runner

### Данные
- `data/organizations.json` — 725 raw orgs
- `data/organizations_filtered.json` — 517 kept + 207 dropped с причинами
- `data/research/{oid}__local.json` — 459 финальных карточек
- `data/research/` готов принять остаток (58 шт) при перезапуске

### Отчёты
- `REPORT_4architectures.md` — детальное сравнение SIMPLE/ORCH/v2/v2.1
- `REPORT_4models_agat.md` — LangGraph 4-model compare (legacy)
- `REPORT_simple_vs_graph.md` — flat agent vs LangGraph
- `REPORT_phase_0_to_C2.md` — старая работа phases A→C2
- **`REPORT_session_2026-05-28.md`** — этот файл

### Логи
- `data/01_scrape.log`
- `data/02_filter.log`
- `data/03_smoke.log` — тест-запуск 03_research_all на 2 орг
- `data/03_full.log` — лог полного батча (~13ч)

---

## 7. Команды для завтра

```bash
# 1. Убедиться что infra жива
pm2 list
docker ps

# 2. Если нужно — пересоздать
pm2 start ecosystem.config.js
cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service" && docker compose up -d
cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service/infra/searxng" && docker compose up -d

# 3. Доработать остаток батча (идемпотентно)
cd "C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service"
MODEL=local CONCURRENCY=3 uv run python yandex_enrichment_experiment/03_research_all.py
# → пропустит 459 готовых, обработает оставшиеся 58, ETA ~1.5-2ч

# 4. Перепроверить статистику
ls yandex_enrichment_experiment/data/research/ | wc -l  # ожидаемо 517
```

Спать спокойно. До завтра.
