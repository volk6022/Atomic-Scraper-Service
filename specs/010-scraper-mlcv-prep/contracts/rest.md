# REST API Contracts: Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration

**Feature**: 010-scraper-mlcv-prep  
**Date**: 2026-05-01

---

## Endpoint 1: Health Check

**Path**: `GET /healthz`

**Description**: Returns service health status for Docker healthchecks and load balancers.

**Response** (200 OK):
```json
{
  "status": "healthy",
  "timestamp": "2026-05-01T12:00:00Z",
  "services": {
    "redis": "connected",
    "browser_pool": "available"
  }
}
```

**Response** (503 Service Unavailable):
```json
{
  "status": "unhealthy",
  "timestamp": "2026-05-01T12:00:00Z",
  "services": {
    "redis": "disconnected",
    "browser_pool": "unavailable"
  }
}
```

**SLA**: Response time must be < 200ms

---

## Endpoint 2: Yandex Maps Extraction

**Path**: `POST /scrape/yandex-maps`

**Description**: Extract business data from Yandex Maps based on location parameters.

**Request**:
```json
{
  "category": "restaurants",
  "center": {
    "lat": 59.934,
    "lng": 30.306
  },
  "radius": 1000,
  "use_stealth": true,
  "proxy": {
    "host": "proxy.example.com",
    "port": 8080,
    "username": "user",
    "password": "pass"
  }
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "businesses": [
    {
      "name": "Restaurant Name",
      "address": "123 Main Street, Saint Petersburg",
      "phone": "+7 (812) 123-45-67",
      "website": "https://restaurant.example.com",
      "geo": {
        "lat": 59.9345,
        "lng": 30.307
      },
      "category": "restaurants"
    }
  ],
  "total_found": 15,
  "request_id": "req-abc123"
}
```

**Response** (429 Too Many Requests):
```json
{
  "success": false,
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded for *.yandex.* domains",
  "retry_after": 3600
}
```

**Response** (400 Bad Request):
```json
{
  "success": false,
  "error": "invalid_request",
  "message": "Invalid category or coordinates"
}
```

---

## Endpoint 3: Site Enrichment

**Path**: `POST /enrich/site`

**Description**: Extract clean text content from company website.

**Request**:
```json
{
  "url": "https://company.example.com",
  "crawl_pages": ["about", "services"],
  "max_words": 500,
  "use_stealth": true
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "url": "https://company.example.com",
  "text": "Company description text...",
  "word_count": 487,
  "pages_crawled": [
    "https://company.example.com",
    "https://company.example.com/about",
    "https://company.example.com/services"
  ],
  "truncated": false
}
```

**Response** (400 Bad Request):
```json
{
  "success": false,
  "error": "invalid_url",
  "message": "URL must be a valid HTTP/HTTPS URL"
}
```

**Response** (413 Payload Too Large):
```json
{
  "success": false,
  "error": "content_too_large",
  "message": "Extracted content exceeds memory limits"
}
```

---

## Endpoint 4: Atomic Scraping (Existing - Stealth Option)

**Path**: `POST /scraper`

**Description**: Existing endpoint extended with stealth option.

**Request** (extended):
```json
{
  "url": "https://example.com",
  "use_stealth": true,
  "proxy": {
    "host": "proxy.example.com",
    "port": 8080
  },
  "actions": [
    {"type": "goto", "url": "https://example.com"},
    {"type": "extract", "selector": ".content"}
  ]
}
```

**Response**: Unchanged from existing contract.

---

## Rate Limit Headers

All endpoints return rate limit headers:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests per window |
| `X-RateLimit-Remaining` | Requests remaining in window |
| `X-RateLimit-Reset` | Unix timestamp when window resets |
| `Retry-After` | Seconds to wait before retry (429 only) |