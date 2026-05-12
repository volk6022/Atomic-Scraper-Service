# Research: LM Studio Structured Output Testing

**Date**: 2026-05-12  
**Objective**: Determine best approach for structured JSON output using local LLM via LM Studio

## Context

The qwen3.5-9b model (`qwen3.5-9b-claude-4.6-opus-reasoning-distilled`) was proposed to replace Jina Reader for HTML extraction. Testing revealed it is a **reasoning/thinking model** with ~2 tokens/sec output speed, making it impractical for extraction workloads.

## Test Results

| Approach | Model | Result | valid_json | Latency | Issues |
|----------|-------|--------|------------|---------|--------|
| A - response_format | qwen3.5-9b | ERROR | no | - | `response_format.type` must be `json_schema` or `text` |
| B - Direct JSON | qwen3.5-9b | TIMEOUT | - | >180s | Reasoning model too slow |
| C - Markdown JSON | qwen3.5-9b | TIMEOUT | - | >180s | Reasoning model too slow |
| D - Schema | qwen3.5-9b | TIMEOUT | - | >180s | Reasoning model too slow |
| A - response_format | jinaai.readerlm-v2 | schema returned | partial | ~3s | Returns schema, not data |
| B - Direct prompt | jinaai.readerlm-v2 | `{"title":"Hello World"...}` | yes | ~3s | Wrapped in ```json |
| C - Markdown request | jinaai.readerlm-v2 | `{"title":"Your Title"...}` | yes | ~3s | Placeholder values |
| **D - Schema in system** | **jinaai.readerlm-v2** | **`{"title":"Product Page","content":"$99"}`** | **yes** | **~3s** | **Cleanest output** |

## Key Findings

1. **qwen3.5-9b is unsuitable** for extraction - reasoning model (~2 tokens/sec)
2. **jinaai.readerlm-v2 works excellently** - optimized for extraction (~3s)
3. **Approach D (Schema in system prompt)** produces the cleanest output
4. LM Studio does not support `response_format: {"type": "json_object"}` - only `json_schema` or `text`

## Decision

**Selected Model**: `jinaai.readerlm-v2`

**Selected Approach**: Schema in system prompt (Approach D)

### Recommended Curl Example

```bash
curl -X POST http://100.70.230.73:20022/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jinaai.readerlm-v2",
    "messages": [
      {"role": "system", "content": "Extract structured data from HTML. Schema: {\"type\":\"object\",\"properties\":{\"title\":{\"type\":\"string\"},\"content\":{\"type\":\"string\"},\"links\":{\"type\":\"array\"}}}}"},
      {"role": "user", "content": "HTML: <html><head><title>Product Page</title></head><body><p>Price: $99</p></body></html>"}
    ]
  }'
```

**Output**: `{"title":"Product Page","content":"Price: $99","links":[]}`

## Implementation Notes

1. Use `jinaai.readerlm-v2` model ID in OpenAI-compatible client
2. Pass extraction schema in system prompt as JSON schema
3. Add fallback JSON parsing for markdown code blocks (some responses wrap in ```json)
4. Typical latency ~3 seconds per extraction

## Specification Update Required

**FR-003** and **FR-004** should reference `jinaai.readerlm-v2` instead of `qwen3.5-9b`.
