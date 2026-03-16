# REST API Contracts

## Authentication
All requests require the `X-API-Key` header.

---

## 1. Stateless Scraper
**Endpoint**: `POST /scraper`

**Request Body**:
```json
{
  "url": "https://example.com",
  "proxy": "http://user:pass@host:port" (optional),
  "wait_until": "domcontentloaded" (optional)
}
```

**Response (200 OK)**:
```json
{
  "id": "uuid",
  "url": "https://example.com",
  "content": "<html>...</html>",
  "status": "success"
}
```

---

## 2. Serper-Compatible Search
**Endpoint**: `POST /serper`

**Request Body**:
```json
{
  "q": "query string",
  "num": 10
}
```

**Response (200 OK)**:
```json
{
  "searchParameters": { "q": "...", "type": "search", "engine": "google" },
  "organic": [
    { "title": "...", "link": "...", "snippet": "...", "position": 1 }
  ]
}
```

---

## 4. Omni-Parser Analysis
**Endpoint**: `POST /omni-parse`

**Request Body**:
```json
{
  "base64_image": "...",
  "prompt": "Find the login button" (optional)
}
```

**Response (200 OK)**:
```json
{
  "elements": [
    {"id": 1, "label": "button", "box": [x1, y1, x2, y2], "text": "Login"}
  ]
}
```

---

## 5. Jina Extraction
**Endpoint**: `POST /jina-extract`

**Request Body**:
```json
{
  "html": "<html>...</html>",
  "format": "markdown",
  "schema": {} (optional)
}
```

**Response (200 OK)**:
```json
{
  "content": "...",
  "extracted_data": {} (optional)
}
```
