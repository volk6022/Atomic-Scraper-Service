# Research: Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration

**Feature**: 010-scraper-mlcv-prep  
**Date**: 2026-05-01

## Research Questions from Technical Context

### Q1: AI/ML for Yandex Maps Extraction

**Question**: Does Yandex Maps extraction require AI/ML calls for parsing, or can it be done with CSS selectors?

**Finding**: CSS selectors are sufficient for Yandex Maps extraction. The page structure is relatively stable with identifiable class names for business cards. However, due to the anti-bot protection (Principle IX), the extraction will require stealth browser to succeed. AI/LLM is NOT required for the extraction itself - CSS selectors can parse the business data.

**Decision**: Use CSS selectors for Yandex Maps extraction. No LLMFacade calls required.

**Alternatives considered**:
- LLM-based extraction: Overkill for structured data, adds latency and cost
- Omni-Parser: Not needed for Yandex Maps' relatively simple DOM structure

---

### Q2: Stealth Library Selection

**Question**: Which stealth library provides better anti-bot evasion - playwright-stealth or patchright?

**Research findings**:

| Criteria | playwright-stealth | patchright |
|----------|-------------------|------------|
| Approach | JavaScript injection | Protocol-level binary patching |
| Detection bypass | Good for basic detection | Excellent - passes Cloudflare, Akamai, DataDome |
| Console.log | Works | Disabled (limitation) |
| Browser support | Chromium, Firefox, WebKit | Chromium only |
| Maintenance | Community-driven | Active, auto-tracks Playwright releases |
| Python support | Yes | Yes |

**Recommendation**: Use **patchright** for this feature.

**Rationale**:
1. Yandex Maps has sophisticated anti-bot detection - patchright provides superior bypass
2. Protocol-level patches are more robust than JavaScript injection
3. Console.log limitation is acceptable for automated scraping
4. Chromium-only is fine - the service primarily uses Chromium

**Alternatives considered**:
- playwright-stealth: Insufficient for Yandex Maps, simpler detection bypass
- Manual patches: High maintenance burden, same limitations as playwright-stealth

---

### Q3: Rate Limiter Implementation

**Question**: Should the rate limiter be Redis-based token bucket or in-memory with Redis persistence?

**Research findings**:

Available approaches:
1. **Redis-based token bucket** (recommended): Atomic Lua script execution, distributed across instances, proven libraries available
2. **In-memory with Redis persistence**: Simpler but less reliable for distributed deployments
3. **Redis hash with INCR**: Simpler but lacks burst handling

**Existing libraries**:
- `hooiv/redis-rate-limiter`: Full-featured, FastAPI integration, async support
- `otovo/redis-rate-limiters`: Token bucket and semaphore implementations, sync/async

**Recommendation**: Use Redis-based token bucket with custom implementation.

**Rationale**:
1. The project already uses Redis (for Taskiq) - no new infrastructure required
2. Token bucket algorithm supports burst handling (important for user experience)
3. Atomic Lua scripts ensure consistency across distributed instances
4. Domain-specific configuration (e.g., 30/hour for `*.yandex.*`) can be hardcoded

**Implementation approach**:
- Use Redis hash to store per-domain token buckets
- Lua script for atomic check-and-consume
- Middleware in FastAPI for request validation

**Alternatives considered**:
- Existing libraries: Add unnecessary dependencies
- In-memory: Doesn't work with Taskiq worker distribution

---

## Summary of Decisions

| Question | Decision | Rationale |
|-----------|----------|-----------|
| Yandex Maps extraction | CSS selectors only | DOM is stable, no AI needed |
| Stealth library | patchright | Superior bypass for Yandex Maps |
| Rate limiter | Redis token bucket | Distributed, atomic, existing infrastructure |

---

## Risks and Mitigations

1. **Risk**: patchright may lag behind Playwright releases
   **Mitigation**: Monitor releases, test after Playwright updates

2. **Risk**: Yandex Maps may change DOM structure
   **Mitigation**: Add selector validation in tests, log failures for quick response

3. **Risk**: Rate limiter Redis keys may grow unbounded
   **Mitigation**: TTL on keys, cleanup job for expired domains