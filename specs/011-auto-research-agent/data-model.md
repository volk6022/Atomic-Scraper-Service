# Data Model: Auto-Research Agent

**Branch**: `011-auto-research-agent` | **Date**: 2026-05-11

## Entities

### ResearchMode (Enum)

| Field | Type | Description |
|-------|------|-------------|
| `speed` | EnumValue | Fast mode: 2 iterations, 4K tokens, high concurrency |
| `balanced` | EnumValue | Default mode: 5 iterations, 8K tokens |
| `quality` | EnumValue | Deep analysis: 10 iterations, 16K tokens, may decompose queries |

### ResearchRequest (Pydantic Model)

| Field | Type | Validation | Description |
|-------|------|------------|-------------|
| `query` | string | Required, min 3 chars | Natural language research question |
| `mode` | ResearchMode | Optional, default=balanced | Research depth preset |
| `max_iterations` | int | Optional, 1-20 | Override mode's iteration limit |
| `max_tokens` | int | Optional, 1000-32000 | Override mode's token budget |

### ResearchTask (Internal State)

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | UUID | Unique identifier for the research job |
| `query` | string | Original research question |
| `mode` | ResearchMode | Selected mode |
| `status` | enum | pending/running/completed/failed |
| `current_node` | string | Current graph node being executed |
| `progress` | ProgressInfo | Phase and percentage complete |
| `result` | ResearchReport | Final report when completed |
| `created_at` | datetime | Task creation timestamp |
| `updated_at` | datetime | Last status update |

### ResearchReport (Output)

| Field | Type | Description |
|-------|------|-------------|
| `answer_markdown` | string | Synthesized answer with [n] citations |
| `citations` | list[Citation] | Referenced sources with URL, title, snippet |
| `facts` | list[Fact] | Extracted claims with confidence scores |
| `stats` | ResearchStats | Execution metadata |

### Citation

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Source URL |
| `title` | string | Page title |
| `snippet` | string | Relevant content snippet |

### Fact

| Field | Type | Description |
|-------|------|-------------|
| `claim` | string | Extracted factual claim |
| `confidence` | float | 0.0-1.0 confidence score |
| `source_url` | string | Origin URL |

### ResearchStats

| Field | Type | Description |
|-------|------|-------------|
| `iterations` | int | Number of graph cycles executed |
| `urls_visited` | int | Count of unique URLs scraped |
| `elapsed_seconds` | float | Total execution time |
| `mode_used` | ResearchMode | Mode that was applied |
| `completed_normally` | bool | True if not cut short by constraints |

### ResearchState (LangGraph State)

| Field | Type | Description |
|-------|------|-------------|
| `query` | string | Current research question |
| `mode` | ResearchMode | Active mode |
| `max_iterations` | int | Iteration cap |
| `token_budget` | int | Max tokens allowed |
| `deadline_ts` | float | Wall-clock deadline timestamp |
| `iterations` | int | Current iteration count |
| `beast_mode` | bool | True if budget/deadline/stall triggered |
| `stall_counter` | int | Consecutive zero-new-URL count |
| `visited_urls` | set[str] | URLs already processed |
| `search_results` | list[dict] | Pending search results to process |
| `scraped_content` | list[dict] | Fetched page content |
| `extracted_facts` | list[Fact] | Claims gathered so far |
| `gaps` | list[str] | Unanswered sub-questions |
| `answer` | string | Final synthesized answer |
| `citations` | list[Citation] | Source references |
| `error` | string | Error message if failed |

### ProgressInfo

| Field | Type | Description |
|-------|------|-------------|
| `phase` | string | Current phase (classifying/planning/searching/scrape/extracting/synthesizing) |
| `percent` | int | 0-100 progress estimate |
| `message` | string | Human-readable status |

## Validation Rules

- `ResearchRequest.query`: Minimum 3 characters, maximum 2000 characters
- `ResearchRequest.max_iterations`: If provided, must be between 1 and 20
- `ResearchRequest.max_tokens`: If provided, must be between 1000 and 32000
- `ResearchMode`: Must be one of "speed", "balanced", "quality"
- `Fact.confidence`: Float between 0.0 and 1.0

## State Transitions (LangGraph)

```
START → classify → plan → search → rank_dedupe → scrape → extract_facts → reflect → answer → END
                                      ↑                                    ↓
                                      └── beast_mode triggered → answer →
```

### Node Routing Conditions

| Condition | Next Node |
|-----------|-----------|
| `gaps` not empty and `not beast_mode` | plan (loop back) |
| `gaps` empty or `beast_mode` | answer |
| `iterations >= max_iterations` | answer (force finish) |
| `time > deadline_ts` | answer (force finish) |
| `stall_counter >= 2` | answer (force finish) |

## Relationships

- `ResearchTask` references `ResearchRequest` and `ResearchReport`
- `ResearchReport` contains `citations[]`, `facts[]`, `stats`
- `ResearchState` is internal to LangGraph, not exposed via API
- `ResearchTask` stored in Redis with 24-hour TTL