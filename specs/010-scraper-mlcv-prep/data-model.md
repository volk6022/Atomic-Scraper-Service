# Data Model: Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration

**Feature**: 010-scraper-mlcv-prep  
**Date**: 2026-05-01

## Entities from Feature Specification

### 1. Business Card

Represents a business listing from Yandex Maps.

**Fields**:
- `name` (string, required): Business name
- `address` (string, required): Street address
- `phone` (string, optional): Contact phone number
- `website` (string, optional): Business website URL
- `geo` (object, optional): Geographic coordinates
  - `lat` (float): Latitude
  - `lng` (float): Longitude
- `category` (string, optional): Business category (e.g., "restaurants")

**Validation**:
- name: non-empty, max 500 chars
- address: non-empty, max 1000 chars
- phone: valid phone format (optional)
- website: valid URL format (optional)
- geo.lat: -90 to 90
- geo.lng: -180 to 180

**Relationships**: Part of Yandex Maps extraction response (collection)

---

### 2. Enriched Content

Represents cleaned and truncated text content extracted from a company website.

**Fields**:
- `url` (string, required): Original URL that was scraped
- `text` (string, required): Cleaned text content
- `word_count` (integer, required): Number of words in text
- `pages_crawled` (array of strings, optional): List of URLs crawled (main + about/services)
- `truncated` (boolean, required): Whether content was truncated to fit limit

**Validation**:
- url: valid URL format
- text: non-empty after cleaning
- word_count: > 0
- pages_crawled: valid URLs if present
- word_count <= 500 (after truncation)

**Relationships**: Returned by site enrichment action

---

### 3. Rate Limit Rule

Represents a domain pattern and associated request limit.

**Fields**:
- `domain_pattern` (string, required): Regex pattern for domain matching (e.g., `*.yandex.*`)
- `requests_per_hour` (integer, required): Maximum requests allowed per hour
- `enabled` (boolean, required): Whether rule is active

**Validation**:
- domain_pattern: valid regex
- requests_per_hour: 1 to 10000
- enabled: boolean

**Default rules**:
- `*.yandex.*`: 30 requests/hour
- `*`: 1000 requests/hour (fallback)

**Relationships**: Used by rate limiter middleware to validate requests

---

### 4. Proxy

Represents a proxy server for browser requests.

**Fields**:
- `host` (string, required): Proxy server hostname or IP
- `port` (integer, required): Proxy server port
- `username` (string, optional): Authentication username
- `password` (string, optional): Authentication password
- `enabled` (boolean, required): Whether proxy is available

**Validation**:
- host: non-empty string
- port: 1 to 65535
- username/password: optional, but if present both required

**Relationships**: Used by browser pool for request routing

---

## Additional Entities (Implicit)

### 5. Health Check Response

**Fields**:
- `status` (string): "healthy" or "unhealthy"
- `timestamp` (ISO datetime): Check timestamp
- `services` (object): Status of dependent services
  - `redis`: "connected" or "disconnected"
  - `browser_pool`: "available" or "unavailable"

---

### 6. Stealth Config

Configuration for stealth browser mode.

**Fields**:
- `enabled` (boolean): Whether stealth mode is active
- `user_agent_pool` (array of strings): Pool of User-Agent strings
- `human_emulation` (boolean): Enable human-like behavior (mouse jitter, typing delays)

---

## State Transitions

### Rate Limiter State

```
[Request] → [Check domain rule] → [Allow] → [Consume token] → [OK]
                              ↓
                         [Deny] → [Return 429] → [Retry-After header]
```

### Browser Pool State

```
[Request] → [Check stealth config] → [Use patchright] → [Execute]
                              ↓
                         [Use standard Playwright]
```

---

## Validation Rules Summary

| Entity | Field | Rule |
|--------|-------|------|
| BusinessCard | name | non-empty, max 500 |
| BusinessCard | address | non-empty, max 1000 |
| BusinessCard | geo.lat | -90 to 90 |
| BusinessCard | geo.lng | -180 to 180 |
| EnrichedContent | text | non-empty after clean |
| EnrichedContent | word_count | <= 500 |
| RateLimitRule | domain_pattern | valid regex |
| RateLimitRule | requests_per_hour | 1 to 10000 |
| Proxy | port | 1 to 65535 |