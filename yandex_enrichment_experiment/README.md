# Yandex Enrichment Experiment

Эксперимент: спарсить организации в районе **59°54'57"N 30°19'49"E ± 2км** (≈ Гражданка / Полюстрово, СПб) и прогнать каждую через Research Agent для генерации идей ML/CV-автоматизаций.

## Структура

```
yandex_enrichment_experiment/
├── README.md                — этот файл
├── 01_scrape_yandex.py     — парсинг Yandex Maps по категориям + фильтр по радиусу
├── 02_research_orgs.py     — последовательный прогон через Research Agent
├── data/
│   ├── raw/<category>.json — сырые ответы yandex-maps по каждой категории
│   ├── organizations.json  — итоговый список уникальных орг в радиусе
│   ├── research/<oid>.json — отчёт research-агента по каждой орг
│   └── research_summary.json — сводка по всем
```

## Параметры

- Центр: lat=59.91583, lon=30.33028
- Радиус: 2000 м
- API: http://localhost:8000, key `default_internal_key`
- LLM: http://100.70.230.73:20022/v1/ (qwen3.5-9b)
- Прокси: 20 HTTP-прокси из `proxies.txt` (для yandex-maps)
- Research mode: `speed` (минимум итераций)

## Запуск

```bash
# 1. Парсинг (~5-10 мин)
uv run python yandex_enrichment_experiment/01_scrape_yandex.py

# 2. Research (~30-60 сек на орг × N орг = долго)
uv run python yandex_enrichment_experiment/02_research_orgs.py
```

Скрипт 02 идемпотентен — пропускает уже обработанные `oid`.
