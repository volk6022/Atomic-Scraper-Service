## Research Findings

### Correct CSS Selectors (2026-05-13)

Based on inspecting the live Google Search page:

| Field | Selector | Notes |
|-------|----------|-------|
| **Title** | `.b8lM7 h3` | Contains the result title |
| **Link** | `.b8lM7 a` | The URL in the title link |
| **Snippet** | `.kb0PBd.A9Y9g .VwiC3b` | Description text |

**Note:** The title and snippet containers are separate but can be indexed together (same index position).

### Search URL Format

**Correct:** `https://www.google.com/search?q={query}`

The format used in `search_client.py:27` is correct: `f"https://www.google.com/search?q={quote(query)}&num=20"` 

However, the `&num=20` parameter is deprecated - Google controls result count via the UI, not this parameter. It's harmless but unnecessary.

### Issues with Current Implementation

1. **Line 34:** `await page.locator(".g").all()` - **BROKEN** - The `.g` class no longer exists in Google's DOM. This is why no results are being extracted.

2. **Line 38-39:** Uses `.g h3` and `.g a` inside the non-existent `.g` container.

3. **Line 52:** `container.locator(".VwiC3b, .st").first` - The `.VwiC3b` part works but the `.st` fallback is an old/deprecated class.

4. **Line 27:** The search URL correctly uses `quote(query)` for proper URL encoding.

### Recommended Fixes

The implementation needs to be updated to use:
- Title/Link: `.b8lM7` container
- Snippet: `.kb0PBd.A9Y9g .VwiC3b`

Or alternatively use a fallback approach that queries both selectors separately and matches by index.

## Структурный подход (без привязки к классам)

### Ключевые стабильные паттерны

| Поле | Как найти (структурный подход) |
|------|--------------------------------|
| **Link** | `a[ping]` — все ссылки результатов имеют атрибут `ping` (для click tracking Google) |
| **Title** | `h3` внутри того же контейнера что и `a[ping]` |
| **Snippet** | `.VwiC3b` — класс описывает семантику "visibility class 3" |

### Контейнер результатов

Основной контейнер: `.eqAnXb` (внутри `<main role="main">`)

Каждый результат имеет атрибут `data-rpos` — позиция в результатах (1, 2, 3...)

### Рекомендуемый селектор для извлечения

```python
# 1. Найти все контейнеры с data-rpos
results = page.locator('[data-rpos]')

# 2. Для каждого результата:
title = container.locator('h3').text_content()
link = container.locator('a[ping]').get_attribute('href')
snippet = container.locator('.VwiC3b').text_content()
```

### Почему это более стабильно

1. **`a[ping]`** — атрибут `ping` обязателен для всех результатов Google (механизм отслеживания кликов)
2. **`data-rpos`** — позиция результата, используется внутренней системой Google
3. **`.VwiC3b`** — более семантичен чем `.st` (старый класс), но возможно изменится
4. **`h3`** — стандартный HTML тег заголовка, очень стабильный

### Резюме

- **Link:** `a[ping]` (обязательный атрибут)
- **Title:** `h3` внутри того же родителя что и `a[ping]`
- **Snippet:** `.VwiC3b`
- **Container:** `[data-rpos]`

Классы `.b8lM7`, `.kb0PBd` временные — могут измениться в любой момент.

Based on my analysis, I've identified several issues. Let me summarize what I found:

## Analysis Summary

### Current Implementation (search_client.py:32-33)
```python
await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
await asyncio.sleep(3)  # Already has a 3-second delay
```

The code already has a 3-second delay, but there are potential issues:

1. **`wait_until="domcontentloaded"`** - Fires too early, before search results are rendered
2. **No wait_for_selector** - Doesn't wait for actual search result elements
3. **No CAPTCHA detection** - Google may return empty page with CAPTCHA challenge

### Related Issues in Logs
- **research.py:88**: `TypeError: object int can't be used in 'await' expression` - `get_concurrent_task_count()` returns a sync value but is being awaited
- **Yandex Maps timeouts** - Uses `"networkidle"` which is too strict

---

## Proposed Plan

### 1. Fix search_client.py
- Change `wait_until` from `"domcontentloaded"` to `"load"` (more reliable)
- Add `wait_for_selector` for search result elements (e.g., `div[data-rpos]`, `.g`, or `#search`)
- Add CAPTCHA detection and graceful fallback
- Keep existing 3-second delay as backup

### 2. Fix research.py:88
- Check `get_concurrent_task_count` function - likely needs to be async or shouldn't be awaited

### 3. Test Multiple Times
- Make 5-10 requests to /serper to verify reliability

---

**Do you want me to proceed with implementing these changes?** I can:
1. Update search_client.py with proper wait conditions and CAPTCHA handling
2. Fix the research.py TypeError
3. Then you can test the endpoint

Should I proceed with implementation, or do you want to clarify anything first?