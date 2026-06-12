# Batched inference for mass research — design notes & feasibility

**Status:** exploration only (no implementation). Goal: decide whether a
batched-inference / KV-paging scheduler is worth building for running ~100 research
agents in parallel, and what it would take.

---

## 1. The proposed architecture (restated)
Run ~100 research agents from a queue, each checkpointing state to JSON, and drive
inference as a **bulk-synchronous scheduler**:
1. Step every task's *large-context* call (one agent turn each) through llama under a
   single config; **defer the small-context calls** (critic/refraser/answer).
2. After ~100 large calls drain, **reload llama with a config tuned to the next call
   class** and drain those.
3. Reload llama **rarely** (config switch = weight reload from disk = expensive IO).
4. **Persist KV to SSD** so prefill isn't redone when a task resumes; keep a **RAM KV
   buffer** with **prefetch** of the next 5–6 tasks' KV.
5. Possibly drop llama.cpp for an engine with finer KV control.

This is, by name: **BSP scheduling over agents + KV-cache paging** (prefix reuse +
SSD/RAM tiering + prefetch). It's a known pattern — most of it already exists in
serving engines.

## 2. What existing engines already give you (don't hand-roll)
| Component in the design | Provided by |
|---|---|
| Prefill reuse of shared prefix (system+query) | vLLM **automatic prefix caching**; **SGLang RadixAttention**; llama.cpp in-slot only |
| KV on SSD / CPU-RAM tiering | **LMCache** (on vLLM): KV offload to CPU/disk/remote; SGLang CPU/disk offload |
| Persist/restore a task's KV | llama.cpp `--slot-save-path` + slot save/restore (primitive); vLLM/SGLang via cache layer |
| RAM buffer + prefetch next N | LMCache tiered cache; SGLang radix tree + LRU eviction |
| Mixed-size continuous batching | vLLM / SGLang native — removes the need for manual "phase by config" |

**Closest match to the vision: SGLang / RadixAttention** — a radix tree of KV that
auto-shares prefixes across every agent call and evicts to CPU/disk. It was designed
for agent loops with branching + heavy KV reuse. Second: **vLLM + LMCache** (PagedAttention
+ prefix cache + SSD/RAM KV offload). Re-implementing either on llama.cpp = weeks of
reinventing them.

## 3. Where the design meets reality (ranked)
1. **The hard gate is VRAM, not software.** On this box (8 GB, q8 model already ~7.6/8 GB)
   there is no room for a KV pool. PagedAttention/RadixAttention shine when many
   sequences' KV live *in VRAM* (24 GB+, np 20–50). At 8 GB you spill to RAM/SSD
   immediately → **IO-bound**, which becomes the ceiling — exactly the thing the design
   tries to outrun. **This architecture's natural habitat is a 24 GB+ card**, where it's
   almost free via the engines above.
2. **"Phase by config" fights the agent control flow.** critic/refraser are *intra-task*
   dependencies (a task cannot pass `submit` without the critic's verdict), so they
   can't be cleanly deferred into a separate global phase. And a config switch reloads
   weights from disk. Engines sidestep this with native mixed-size continuous batching —
   no manual phasing, no reloads.
3. **Model-format migration.** Leaving llama.cpp means GGUF → AWQ/GPTQ/FP8 for vLLM/SGLang.
   At 8 GB a 9B model must be ~4-bit to leave KV room.
4. **Is prefill-redundancy even the bottleneck?** With `concurrency == np` (3 tasks on 3
   slots) each task owns a slot for its lifetime → KV is preserved → there is **no
   redundant prefill**. KV-paging only pays off under **oversubscription** (100 tasks on
   3 slots, time-sliced) — a regime the design itself creates. Measure the prefill waste
   before building the machine to remove it.

## 4. The *actual* current bottleneck (different from what KV-paging fixes)
Empirically (this run): `compaction_count = 0` on all cards → the ~40k context is **not**
exhausted; context is not the limiter. The pain is the **timeout tail** (see
`§ timeout analysis` below), driven by:
- **Decode contention at np=3** — 3 agents share one llama, each gets ~⅓ throughput, so
  turns are slow.
- **Proxy-pool degradation under sustained load** — agent tools (web_serp/web_scrape) go
  through the residential pool; as it degrades (observed **4/10 ports live**, surviving
  ones up to ~5 s), each tool call rotates past dead ports → tool wall-time balloons.

Neither is fixed by KV-paging. KV-paging fixes *redundant prefill under oversubscription*.
So the grand design targets a **future massive-parallelism regime**, not today's pain.
Today's levers are: higher np (needs VRAM), proxy-pool health, smaller per-task context
→ more concurrency, or faster hardware.

## 5. What to measure FIRST (cheap, gates everything)
The dataset already exists — the llama-server log of the current run records `n_prompt`,
`n_predict`, timings per request. Build a small parser (≈half a day) to get:
1. **Context-size distribution by call type** (main turn / critic / refraser / answer).
   Tag types either by size signature or a tiny marker added to each prompt. Answers
   "how bimodal is context, what % of calls/tokens are small (batchable)".
2. **Prefill-redundancy estimate** — how many tokens are re-prefilled on task resume vs
   reused. This is the literal prize of KV-paging; if it's small, the whole idea is moot.
3. **tps vs context curve on THIS hardware** — confirm the 10k/np4≈110 vs 40k/np3≈70
   numbers, and measure SSD KV-restore time for a 30k-token cache vs just re-prefilling
   30k tokens. On 8 GB the restore may not beat re-prefill — measure before believing.

Rough upside ceiling: if small-context calls are ~30% of token-volume and batching
speeds them ~57% (110/70), overall win ≈ 0.3 × 0.36 ≈ **~10 %** — modest unless the
analysis shows a much larger small-context / redundant-prefill population.

### Measured (2026-06-11, this run, from llama-server log + `/metrics`)
Parsed 16.1k requests (`slot release … n_tokens` = full context; `prompt eval … M tokens`
= new tokens prefilled). Live monitor: `yandex_enrichment_experiment/monitor_llama_ctx.py`
→ `llama_ctx_monitor.log`.

- **Context per request:** med **4842**, mean **7097**, p90 **14826**, recent-window max
  ~21k (`/metrics n_tokens_max = 21316`). The 36 096-tok/slot window is loaded to ~40%
  even at p90 → **context is not the constraint** (matches compaction_count = 0).
- **New prefill per request:** med **993**, mean **1702** → only **~24 % of context is
  re-prefilled; ~76–80 % is already KV-reused** (llama.cpp in-slot prefix cache +
  context checkpoints, both visible in the log).

**Implication — this guts the KV-paging prize.** The expensive thing the SSD/RAM scheme
removes (redundant prefill) is *already* ~76–80 % handled by the engine in the current
`concurrency==np` regime, and the residual ~1700 tok/req is mostly genuinely-new content
(the latest tool result), which any cache must still prefill. So KV-paging would save
~nothing here; it only pays under heavy oversubscription where slots are evicted and lose
their cached prefix. Net: **don't build KV-paging for this workload/hardware** — the
measured reuse already captures the win.

## 6. Recommendation / priority
1. **Do §5 analysis first.** Cheap, retro on the existing log, and it's the gate: it
   quantifies both the batchable fraction and the prefill-redundancy prize.
2. **If the prize is real, prototype on SGLang** (closest to the KV vision) or vLLM+LMCache
   — do **not** hand-roll the scheduler/cache on llama.cpp.
3. **Be honest about 8 GB.** The design wants 24 GB+. On 8 GB it's an IO fight; a cheaper
   interim is "raise np via context discipline" (aggressive elision / shorter prefill →
   fit np=5–6 → higher throughput → fewer timeouts) — smaller change, addresses today's
   actual bottleneck.
4. **Verdict:** architecturally sound and largely pre-built in SGLang/vLLM, but its payoff
   on current hardware is throttled by VRAM/IO and it doesn't address today's bottleneck
   (decode contention + proxy health). Treat as a **future / bigger-GPU** play; spend now
   on the cheap measurement and on the np/proxy levers.

---

### Appendix — timeout analysis (where "16%" came from)
Per-org research has a hard cap `POLL_MAX_S = 1800` (30 min) in `02_research_orgs.py`;
on expiry it saves a `{oid,title,status:"timeout",query}` stub with `result:null`
(the "query-only ~4 KB files"). Mechanics:
- `concurrency=3` → 3 agents share one np=3 llama; each turn is ~⅓-rate decode.
- Each org does ~10 turns + critic/refraser, **every turn gated on a proxy-bound tool**
  (web_serp/web_scrape). Completed orgs already cluster near the cap (median ~18–21 min,
  max ~29.5 min) — the distribution sits right against 1800 s, so any slowdown spills
  orgs over the edge into timeout.
- **Snapshot 1** (38 cards): 6 timeouts = **16%**, completed-median 1095 s.
- **Snapshot 2** (58 cards): 14 timeouts = **24%**, completed-median 1249 s; the recent
  batch alone ran ~40% timeout. The whole distribution shifted right.
- **Cause of the climb:** proxy-pool degradation under sustained load (4/10 sampled ports
  live, survivors up to ~5 s) → tool latency rising → more orgs cross 30 min. Not context
  (compaction=0), not llama (slots healthy), not quota (live).
- **Note:** timeout stubs block retry (`if out_path.exists(): return`), so a recovery
  pass must delete them first; re-run at lower concurrency (more llama/agent) and/or a
  warmed proxy pool to clear the tail.
