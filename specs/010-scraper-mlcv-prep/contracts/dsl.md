# DSL Contracts: Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration

**Feature**: 010-scraper-mlcv-prep  
**Date**: 2026-05-01

---

## New DSL Actions

### Action 1: yandex_maps_extract

Extracts business data from Yandex Maps search results.

**Command Payload**:
```json
{
  "action": "yandex_maps_extract",
  "params": {
    "category": "restaurants",
    "center_lat": 59.934,
    "center_lng": 30.306,
    "radius_meters": 1000,
    "stealth": true,
    "max_results": 50
  }
}
```

**Result Payload**:
```json
{
  "success": true,
  "businesses": [
    {
      "name": "...",
      "address": "...",
      "phone": "...",
      "website": "...",
      "geo": {"lat": 0, "lng": 0}
    }
  ],
  "total": 15,
  "errors": []
}
```

**Errors**:
- `DETECTION_BLOCKED`: Yandex Maps blocked the request
- `NO_RESULTS`: No businesses found in area
- `INVALID_PARAMS`: Invalid category or coordinates

---

### Action 2: site_enrich

Extracts and cleans content from company websites.

**Command Payload**:
```json
{
  "action": "site_enrich",
  "params": {
    "url": "https://company.example.com",
    "crawl_targets": ["about", "services"],
    "max_words": 500,
    "stealth": true
  }
}
```

**Result Payload**:
```json
{
  "success": true,
  "text": "Cleaned content...",
  "word_count": 487,
  "sources": [
    {"url": "https://company.example.com", "words": 300},
    {"url": "https://company.example.com/about", "words": 187}
  ],
  "truncated": false
}
```

**Errors**:
- `ROBOTS_BLOCKED`: robots.txt disallows scraping
- `CONTENT_TOO_LARGE`: Content exceeds memory limits
- `PARSE_ERROR`: Failed to parse page content

---

### Action 3: apply_stealth

Applies stealth configuration to browser context.

**Command Payload**:
```json
{
  "action": "apply_stealth",
  "params": {
    "user_agent_rotation": true,
    "human_emulation": true,
    "proxy": {
      "host": "proxy.example.com",
      "port": 8080
    }
  }
}
```

**Result Payload**:
```json
{
  "success": true,
  "applied_config": {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    "proxy": "proxy.example.com:8080"
  }
}
```

---

## Extended Existing Actions

### Action 4: goto (Extended)

Existing `goto` action extended with stealth parameter.

**Command Payload** (extended):
```json
{
  "action": "goto",
  "params": {
    "url": "https://yandex.ru/maps/",
    "stealth": true,
    "wait_until": "network_idle",
    "timeout": 30000
  }
}
```

---

## Rate Limiting Integration

Rate limiting is enforced at the API layer, not in DSL. DSL actions that call `/scraper` or `/scrape/yandex-maps` will receive 429 responses if limits are exceeded.

**DSL Result on Rate Limit**:
```json
{
  "success": false,
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded for domain",
  "retry_after": 3600
}
```

---

## Action Registry Entry Format

New actions must be registered in `src/actions/registry.py`:

```python
ACTIONS = {
    # ... existing actions ...
    "yandex_maps_extract": YandexMapsExtractAction,
    "site_enrich": SiteEnrichAction,
    "apply_stealth": ApplyStealthAction,
}
```

Each action class must implement:
- `execute(page: Page, params: dict) -> dict`
- `validate_params(params: dict) -> bool`
- `get_name() -> str`