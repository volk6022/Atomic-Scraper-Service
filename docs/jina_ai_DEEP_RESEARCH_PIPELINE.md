# DeepResearch Pipeline Documentation

https://github.com/jina-ai/node-deepresearch

## Overview

This document describes the deep research pipeline implemented in node-DeepResearch. The system performs iterative search-read-reason cycles until a definitive answer is found or token budget is exceeded.

---

## Main Flowchart

```mermaid
flowchart TD
    Start([Start]) --> Init[Initialize context & variables]
    Init --> CheckBudget{Token budget<br/>exceeded?}
    CheckBudget -->|No| GetQuestion[Get current question<br/>from gaps]
    CheckBudget -->|Yes| BeastMode[Enter Beast Mode]

    GetQuestion --> GenPrompt[Generate prompt]
    GenPrompt --> ModelGen[Generate response<br/>using Gemini]
    ModelGen --> ActionCheck{Check action<br/>type}

    ActionCheck -->|answer| AnswerCheck{Is original<br/>question?}
    AnswerCheck -->|Yes| EvalAnswer[Evaluate answer]
    EvalAnswer --> IsGoodAnswer{Is answer<br/>definitive?}
    IsGoodAnswer -->|Yes| HasRefs{Has<br/>references?}
    HasRefs -->|Yes| End([End])
    HasRefs -->|No| GetQuestion
    IsGoodAnswer -->|No| StoreBad[Store bad attempt<br/>Reset context]
    StoreBad --> GetQuestion

    AnswerCheck -->|No| StoreKnowledge[Store as intermediate<br/>knowledge]
    StoreKnowledge --> GetQuestion

    ActionCheck -->|reflect| ProcessQuestions[Process new<br/>sub-questions]
    ProcessQuestions --> DedupQuestions{New unique<br/>questions?}
    DedupQuestions -->|Yes| AddGaps[Add to gaps queue]
    DedupQuestions -->|No| DisableReflect[Disable reflect<br/>for next step]
    AddGaps --> GetQuestion
    DisableReflect --> GetQuestion

    ActionCheck -->|search| SearchQuery[Execute search]
    SearchQuery --> NewURLs{New URLs<br/>found?}
    NewURLs -->|Yes| StoreURLs[Store URLs for<br/>future visits]
    NewURLs -->|No| DisableSearch[Disable search<br/>for next step]
    StoreURLs --> GetQuestion
    DisableSearch --> GetQuestion

    ActionCheck -->|visit| VisitURLs[Visit URLs]
    VisitURLs --> NewContent{New content<br/>found?}
    NewContent -->|Yes| StoreContent[Store content as<br/>knowledge]
    NewContent -->|No| DisableVisit[Disable visit<br/>for next step]
    StoreContent --> GetQuestion
    DisableVisit --> GetQuestion

    BeastMode --> FinalAnswer[Generate final answer] --> End

```

---

## Detailed Mermaid Diagrams

### 1. Search Action Flow

```mermaid
flowchart TD
    subgraph SEARCH["Action: search"]
        direction LR
        S1[Model returns<br/>search action] --> S2[Deduplicate<br/>search requests]
        S2 --> S3[Execute search<br/>via Jina API]
        S3 --> S4[Store URLs<br/>in allURLs]
        S4 --> S5[Rewrite queries<br/>with cognitive personas]
        S5 --> S6[Execute more<br/>searches]
        S6 --> S7[Add knowledge<br/>to allKnowledge]
    end
    
    S1 -.->|"searchRequests: string[]"| S2
    S2 -.->|"MAX_QUERIES_PER_STEP=5"| S2
    S3 -.->|"results: SearchSnippet[]"| S4
```

### 2. Visit Action Flow

```mermaid
flowchart TD
    subgraph VISIT["Action: visit"]
        direction LR
        V1[Model returns<br/>visit action] --> V2[Normalize URLs<br/>remove tracking]
        V2 --> V3[Rank by<br/>relevance score]
        V3 --> V4[Fetch via<br/>Jina Reader API]
        V4 --> V5[Extract<br/>main content]
        V5 --> V6[Store in<br/>allWebContents]
    end
    
    V1 -.->|"URLTargets: number[]"| V2
    V2 -.->|"removeUTMParams|removeSessionIDs"| V2
    V4 -.->|"https://r.jina.ai/"| V4
```

### 3. Reflect Action Flow

```mermaid
flowchart TD
    subgraph REFLECT["Action: reflect"]
        direction LR
        R1[Model returns<br/>reflect action] --> R2[Generate<br/>sub-questions]
        R2 --> R3{Deduplicate<br/>with existing?}
        R3 -->|Yes| R4[Add to gaps<br/>queue]
        R3 -->|No| R5[Disable reflect<br/>for next step]
        R4 --> R6[Continue loop<br/>with new question]
    end
    
    R1 -.->|"questionsToAnswer: string[]"| R2
    R2 -.->|"MAX_REFLECT_PER_STEP=2"| R2
    R4 -.->|"gaps.push(...questions)"| R4
```

### 4. Answer & Evaluation Flow

```mermaid
flowchart TD
    subgraph EVAL["Answer Evaluation Pipeline"]
        direction TB
        E1[Get question<br/>evaluation types] --> E2{Check each<br/>evaluation type}
        
        E2 -->|"definitive"| E3[Is answer<br/>definitive?]
        E2 -->|"freshness"| E4[Is content<br/>recent enough?]
        E2 -->|"plurality"| E5[Are required items<br/>provided?]
        E2 -->|"completeness"| E6[All aspects<br/>addressed?]
        E2 -->|"strict"| E7[Full rubric<br/>check]
        
        E3 -->|"pass=true"| E8[Continue next check]
        E3 -->|"pass=false"| E9[Return fail]
        E4 --> E8
        E5 --> E8
        E6 --> E8
        E7 --> E9
        E9 --> E10[Return with<br/>improvement_plan]
        
        E8 --> E11{More checks?}
        E11 -->|Yes| E2
        E11 -->|No| E12[Return pass]
    end
    
    E1 -.->|"needsDefinitive<br/>needsFreshness<br/>needsPlurality<br/>needsCompleteness"| E1
```

### 5. Model Interaction Flow

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent
    participant M as Gemini Model
    participant S as SafeGenerator
    participant J as Jina API
    participant E as Evaluator

    U->>A: Question
    A->>M: Generate with schema
    M-->>A: Action (search/visit/reflect/answer)
    
    alt action = search
        A->>J: Execute search
        J-->>A: Search results
        A->>A: Store URLs
    end
    
    alt action = visit
        A->>J: Fetch URLs
        J-->>A: Content
        A->>A: Store content
    end
    
    alt action = answer
        A->>E: Evaluate answer
        E-->>A: pass/fail + reason
        alt pass = false
            A->>A: Reset context
            A->>M: Generate new action
        end
    end
    
    A-->>U: Final Answer
```

### 6. Data Flow Diagram

```mermaid
flowchart TB
    subgraph INPUT["Input"]
        Q[Question] --> IC[Initialize Context]
    end
    
    subgraph STATE["State Management"]
        direction LR
        G["gaps: string[]"] -.->|current question| M
        K["allKnowledge: KnowledgeItem[]"] -.->|context| M
        U[ allURLs: Record ] -.->|URLs| M
    end
    
    subgraph PROCESS["Main Loop"]
        M[Model + Schema] --> A[Action Executor]
    end
    
    subgraph OUTPUT["Output"]
        A --> R[Final Answer]
    end
    
    IC --> G
    IC --> K
    IC --> U
    M --> G
    M --> K
    M --> U
```

### 7. Token Budget Flow

```mermaid
flowchart TD
    START[Start] --> INIT[Initialize<br/>tokenBudget]
    INIT --> CHECK{Used < 85%?}
    
    CHECK -->|Yes| LOOP[Execute Step]
    LOOP --> SEARCH[search action]
    SEARCH --> VISIT[visit action]
    VISIT --> ANSWER[answer action]
    ANSWER --> EVAL[evaluate]
    EVAL --> TRACK[Track tokens]
    TRACK --> CHECK
    
    CHECK -->|No| BEAST[Beast Mode]
    BEAST --> FINAL[Generate final answer]
    FINAL --> END([End])
    
    style START fill:#90EE90
    style END fill:#90EE90
    style BEAST fill:#FFB6C1
```

### 8. URL Processing Pipeline

```mermaid
flowchart LR
    subgraph URL_IN["URL Processing"]
        direction TB
        U1[Raw URLs from<br/>search] --> U2[normalizeUrl]
        U2 --> U3{Remove tracking}
        U3 -->|UTM params| U4[removeUTMParams]
        U3 -->|Session IDs| U5[removeSessionIDs]
        U3 -->|Anchors| U6[removeAnchors]
        
        U4 --> U7[Calculate<br/>boost scores]
        U5 --> U7
        U6 --> U7
        
        U7 --> U8[rankURLs]
        U8 --> U9[filterURLs]
        U9 --> U10[keepKPerHostname]
        U10 --> U11[Weighted URLs<br/>for model]
    end
    
    U2 -.->|"removeAnchors<br/>removeSessionIDs<br/>removeUTMParams<br/>removeTrackingParams"| U2
    U7 -.->|"freqBoost<br/>hostnameBoost<br/>pathBoost<br/>jinaRerankBoost"| U7
```

### 9. Query Rewriting Flow

```mermaid
flowchart TD
    subgraph QR["Query Rewriter"]
        direction TB
        Q1[Initial search<br/>query] --> Q2[Analyze intent<br/>7 layers]
        
        Q2 --> Q3{Generate with<br/>7 personas}
        
        Q3 -->|"Expert Skeptic"| Q4[Edge cases<br/>limitations]
        Q3 -->|"Detail Analyst"| Q5[Granular specs]
        Q3 -->|"Historical"| Q6[Evolution<br/>history]
        Q3 -->|"Comparative"| Q7[Alternatives<br/>trade-offs]
        Q3 -->|"Temporal"| Q8[Time-sensitive]
        Q3 -->|"Globalizer"| Q9[Authoritative<br/>region]
        Q3 -->|"Skepticalist"| Q10[Contradicting<br/>evidence]
        
        Q4 --> Q11[Collect queries]
        Q5 --> Q11
        Q6 --> Q11
        Q7 --> Q11
        Q8 --> Q11
        Q9 --> Q11
        Q10 --> Q11
        
        Q11 --> Q12[Deduplicate]
        Q12 --> Q13[Final search<br/>queries]
    end
    
    Q1 -.->|"tbs, location, q"| Q1
    Q2 -.->|"Surface → Practical → Emotional → Social → Identity → Taboo → Shadow"| Q2
```

### 10. Knowledge Building Flow

```mermaid
flowchart TD
    subgraph KB["Knowledge Building"]
        direction LR
        
        K1[Search results] --> K2[Create KnowledgeItem]
        K2 --> K3{Type}
        
        K3 -->|"url"| K4[Store with reference]
        K3 -->|"qa"| K5[Store Q&A pair]
        K3 -->|"side-info"| K6[Store side info]
        K3 -->|"coding"| K7[Store code result]
        
        K4 --> K8[allKnowledge]
        K5 --> K8
        K6 --> K8
        K7 --> K8
        
        K8 --> K9[Build context<br/>for next step]
    end
    
    K2 -.->|"question<br/>answer<br/>references<br/>type<br/>updated"| K2
```

### 11. Evaluation Types Detail

```mermaid
flowchart LR
    subgraph EVAL_TYPES["Evaluation Types"]
        direction TB
        
        ET1["definitive<br/>Is answer clear<br/>and confident?"]
        ET2["freshness<br/>Is content recent?<br/>(days_ago <= max_age_days)"]
        ET3["plurality<br/>Required items<br/>provided?"]
        ET4["completeness<br/>All aspects<br/>addressed?"]
        ET5["strict<br/>Full rubric<br/>check"]
    end
    
    ET1 -.->|"pass: boolean<br/>think: string"| ET1
    ET2 -.->|"pass: boolean<br/>freshness_analysis"| ET2
    ET3 -.->|"pass: boolean<br/>plurality_analysis"| ET3
    ET4 -.->|"pass: boolean<br/>completeness_analysis"| ET4
    ET5 -.->|"pass: boolean<br/>improvement_plan"| ET5
```

### 12. Beast Mode Flow

```mermaid
flowchart TD
    BM_START[Enter Beast Mode] --> BM_PROMPT[Generate special prompt]
    
    BM_PROMPT --> BM_SCHEMA[Schema: allowAnswer only]
    BM_SCHEMA --> BM_FLAGS[Disable:<br/>- allowSearch<br/>- allowRead<br/>- allowReflect<br/>- allowCoding]
    
    BM_FLAGS --> BM_CALL[Call model with<br/>beastMode flag]
    BM_CALL --> BM_FORCE["🔥 MAXIMUM FORCE<br/>ABSOLUTE PRIORITY"]
    
    BM_FORCE --> BM_ANSWER[Generate answer]
    BM_ANSWER --> BM_BUILD[Build final markdown]
    BM_BUILD --> BM_REFS[Add references]
    BM_REFS --> BM_END([Return final answer])
    
    style BM_START fill:#FFB6C1
    style BM_FORCE fill:#FF6B6B,color:#fff
    style BM_END fill:#90EE90
```

### 13. Research Team (Parallel) Flow

```mermaid
flowchart TD
    RT_START[Complex question] --> RT_ANALYZE[Analyze topic]
    
    RT_ANALYZE --> RT_DECOMPOSE[Decompose into<br/>N orthogonal subproblems]
    RT_DECOMPOSE --> RT_VALIDATE[Validate orthogonality]
    
    RT_VALIDATE -->|"Valid"| RT_PARALLEL[Parallel execution]
    RT_VALIDATE -->|"Invalid| RT_DECOMPOSE
    
    RT_PARALLEL --> RT_1[Subproblem 1<br/>researcher 1]
    RT_PARALLEL --> RT_2[Subproblem 2<br/>researcher 2]
    RT_PARALLEL --> RT_3[Subproblem N<br/>researcher N]
    
    RT_1 --> RT_AGGREGATE[Aggregate results]
    RT_2 --> RT_AGGREGATE
    RT_3 --> RT_AGGREGATE
    
    RT_AGGREGATE --> RT_MERGE[Merge knowledge]
    RT_MERGE --> RT_FINAL[Final answer]
    
    RT_DECOMPOSE -.->|"teamSize parameter"| RT_DECOMPOSE
    RT_PARALLEL -.->|"getResponse(..., teamSize=1)"| RT_PARALLEL
```

### 14. State Transitions

```mermaid
stateDiagram-v2
    [*] --> IDLE: Start
    
    IDLE --> SEARCH: action = search
    IDLE --> VISIT: action = visit
    IDLE --> REFLECT: action = reflect
    IDLE --> ANSWER: action = answer
    IDLE --> CODING: action = coding
    
    SEARCH --> SEARCH: More queries
    SEARCH --> IDLE: Store URLs
    
    VISIT --> VISIT: More URLs
    VISIT --> IDLE: Store content
    
    REFLECT --> REFLECT: New questions
    REFLECT --> IDLE: Add to gaps
    
    ANSWER --> EVALUATE: Evaluate
    EVALUATE --> IDLE: Fail → reset
    EVALUATE --> [*]: Pass → end
    
    CODING --> IDLE: Store result
```

### 1. Main Agent Loop (`src/agent.ts`)

The main orchestration happens in `getResponse()` function (lines 419-1146).

**Key Variables:**
```typescript
const gaps: string[] = [question];        // Questions queue
const allKnowledge: KnowledgeItem[] = []; // Intermediate knowledge
const allURLs: Record<string, SearchSnippet> = {}; // URL storage
const weightedURLs: BoostedSearchSnippet[] = []; // Ranked URLs
const regularBudget = tokenBudget * 0.85; // 85% for normal mode
```

**Loop Condition:**
```typescript
while (context.tokenTracker.getTotalUsage().totalTokens < regularBudget) {
    // ... step execution
}
```

---

## Step Types and Processing

### Action: `search`

**Flow:** Search Query → Execute Search → Store URLs → Add to Knowledge

**Code Location:** `src/agent.ts:804-931`

```typescript
} else if (thisStep.action === 'search' && thisStep.searchRequests) {
    // Deduplicate search requests
    thisStep.searchRequests = chooseK(
        (await dedupQueries(thisStep.searchRequests, [], context.tokenTracker)).unique_queries,
        MAX_QUERIES_PER_STEP
    );

    // Execute search
    const { searchedQueries, newKnowledge } = await executeSearchQueries(
        thisStep.searchRequests.map(q => ({ q })),
        context,
        allURLs,
        SchemaGen,
        allWebContents,
        onlyHostnames,
        searchProvider
    );
```

**Search Providers:**
- `jina` (default) - Jina AI search API
- `duck` - DuckDuckGo
- `brave` - Brave Search
- `serper` - Serper API

**Query Rewriting:**
After initial search, queries are rewritten using cognitive personas (`src/tools/query-rewriter.ts`):

```typescript
// 7 cognitive perspectives generate orthogonal queries:
1. Expert Skeptic      - Focus on edge cases, limitations
2. Detail Analyst      - Granular technical specs
3. Historical Researcher - Evolution over time
4. Comparative Thinker - Alternatives, trade-offs
5. Temporal Context   - Time-sensitive queries
6. Globalizer        - Authoritative language/region
7. Reality-Hater-Skepticalist - Contradicting evidence
```

---

### Action: `visit`

**Flow:** Visit URLs → Extract Content → Store as Knowledge

**Code Location:** `src/agent.ts:931-986`

**URL Processing Pipeline:**
1. Normalize URLs (remove tracking params, sessions)
2. Rank by relevance score
3. Fetch content via Jina Reader API
4. Extract main content and metadata

**Storage:** Content stored in `allWebContents`:
```typescript
const allWebContents: Record<string, WebContent> = {};
// WebContent:
//   - full: string
//   - chunks: string[]
//   - chunk_positions: number[][]
//   - title: string
```

---

### Action: `reflect`

**Flow:** Generate Sub-Questions → De-duplicate → Add to Gaps Queue

**Code Location:** `src/agent.ts:773-803`

```typescript
} else if (thisStep.action === 'reflect' && thisStep.questionsToAnswer) {
    thisStep.questionsToAnswer = chooseK(
        (await dedupQueries(thisStep.questionsToAnswer, allQuestions, context.tokenTracker)).unique_queries,
        MAX_REFLECT_PER_STEP
    );
    // Add to gaps queue
    gaps.push(...newGapQuestions);
    allQuestions.push(...newGapQuestions);
```

---

### Action: `answer`

**Flow:** Generate Answer → Evaluate → Check Quality

**Code Location:** `src/agent.ts:612-747`

**Evaluation Types:**
- `definitive` - Must provide clear, confident response
- `freshness` - Must have recent information
- `plurality` - Must provide requested number of items
- `completeness` - Must address all explicitly named aspects
- `strict` - Full rubric-based evaluation

---

## Models Used

### Primary Reasoning Model

**Model:** `gemini-2.0-flash` (default) or OpenAI-compatible models

**Purpose:** Main agent reasoning, action selection, answer generation

**Configuration:**
```typescript
const generator = new ObjectGeneratorSafe(context.tokenTracker);
const result = await generator.generateObject({
    model: 'agent',
    schema,
    system,
    messages: msgWithKnowledge,
    numRetries: 2,
});
```

### Specialized Models

| Model Name | Purpose | Schema |
|-----------|--------|--------|
| `agent` | Main reasoning loop | `getAgentSchema()` |
| `agentBeastMode` | Fallback when budget exceeded | `getAgentSchema(allowAnswerOnly)` |
| `queryRewriter` | Expand queries with cognitive personas | `getQueryRewriterSchema()` |
| `evaluator` | Evaluate answer quality | `getEvaluatorSchema()` |
| `researchPlanner` | Decompose complex topics | `getResearchPlanSchema()` |
| `serpCluster` | Cluster search results | `getSerpClusterSchema()` |

---

## Structured Output Schemas

### Agent Schema (Main)

**File:** `src/utils/schemas.ts:268-335`

```typescript
getAgentSchema(allowReflect, allowRead, allowAnswer, allowSearch, allowCoding, currentQuestion)
```

**Output Structure:**
```typescript
{
    think: string,                    // Reasoning explanation
    action: "search" | "answer" | "reflect" | "visit" | "coding",
    
    // Action-specific fields:
    search?: {
        searchRequests: string[]      // Google search queries
    },
    answer?: {
        answer: string               // Final/mid-answer
    },
    reflect?: {
        questionsToAnswer: string[]   // Gap questions
    },
    visit?: {
        URLTargets: number[]         // URL indices from list
    },
    coding?: {
        codingIssue: string          // Problem description
    }
}
```

### Query Rewriter Schema

**File:** `src/utils/schemas.ts:191-203`

```typescript
getQueryRewriterSchema()
```

**Output:**
```typescript
{
    think: string,
    queries: {
        tbs?: "qdr:h" | "qdr:d" | "qdr:w" | "qdr:m" | "qdr:y",  // Time filter
        location?: string,         // Search location
        q: string                 // Keyword query (2-3 words)
    }[]
}
```

### Evaluator Schema

**File:** `src/utils/schemas.ts:205-266`

**Definitive Evaluation:**
```typescript
{
    type: "definitive",
    think: string,
    pass: boolean
}
```

**Freshness Evaluation:**
```typescript
{
    type: "freshness",
    think: string,
    freshness_analysis: {
        days_ago: number,
        max_age_days: number
    },
    pass: boolean
}
```

**Plurality Evaluation:**
```typescript
{
    type: "plurality",
    think: string,
    plurality_analysis: {
        minimum_count_required: number,
        actual_count_provided: number
    },
    pass: boolean
}
```

**Completeness Evaluation:**
```typescript
{
    type: "completeness",
    think: string,
    completeness_analysis: {
        aspects_expected: string,
        aspects_provided: string
    },
    pass: boolean
}
```

**Strict Evaluation:**
```typescript
{
    type: "strict",
    think: string,
    improvement_plan: string,
    pass: boolean
}
```

---

## Prompt Templates

### Main Agent Prompt

**File:** `src/agent.ts:110-245`

```typescript
function getPrompt(
    context?: string[],
    allQuestions?: string[],
    allKeywords?: string[],
    allowReflect: boolean = true,
    allowAnswer: boolean = true,
    allowRead: boolean = true,
    allowSearch: boolean = true,
    allowCoding: boolean = true,
    knowledge?: KnowledgeItem[],
    allURLs?: BoostedSearchSnippet[],
    beastMode?: boolean,
): { system: string, urlList?: string[] }
```

**System Prompt Structure:**
```
Current date: {date}

You are an advanced AI research agent from Jina AI. You are specialized in multistep reasoning. 
Using your best knowledge, conversation with the user and lessons learned, answer the user question with absolute certainty.

[context section]
You have conducted the following actions:
<context>
{context}
</context>

[url-list section]
<action-visit>
- Ground the answer with external web content
- Read full content from URLs...
<url-list>
{urlListStr}
</url-list>
</action-visit>

[search section]
<action-search>
- Use web search to find relevant information...
</action-search>

[answer section]
<action-answer>
- For greetings, casual conversation... answer directly
- Provide deep, unexpected insights...
</action-answer>

[reflect section]
<action-reflect>
- Think slowly and planning lookahead...
</action-reflect>

[actions]
Based on the current context, you must choose one of the following actions:
<actions>
{actionSections}
</actions>
```

### Query Rewriter Prompt

**File:** `src/tools/query-rewriter.ts:7-201`

**Cognitive Persona System Prompt:**
```system
You are an expert search query expander with deep psychological understanding.
You optimize user queries by extensively analyzing potential user intents and generating comprehensive query variations.

<intent-mining>
Analyze through 7 layers:
1. Surface Intent: literal interpretation
2. Practical Intent: tangible goal
3. Emotional Intent: feelings driving search
4. Social Intent: relationships/standing
5. Identity Intent: who they want to be
6. Taboo Intent: unspoken aspects
7. Shadow Intent: unconscious motivations
</intent-mining>

<cognitive-personas>
Generate ONE query from each:
1. Expert Skeptic
2. Detail Analyst
3. Historical Researcher
4. Comparative Thinker
5. Temporal Context
6. Globalizer
7. Reality-Hater-Skepticalist
</cognitive-personas>
```

---

## Data Storage

### File Storage

**Location:** Current working directory (files created during execution)

| File | Content |
|-----|---------|
| `prompt-{step}.txt` | System prompt for each step |
| `context.json` | All context steps |
| `queries.json` | All searched queries |
| `questions.json` | All questions (gaps) |
| `knowledge.json` | Intermediate knowledge |
| `urls.json` | Weighted URLs |
| `messages.json` | Messages with knowledge |

**Code Location:** `src/agent.ts:1148-1192`

```typescript
async function storeContext(prompt, schema, memory, step) {
    await fs.writeFile(`prompt-${step}.txt`, ...);
    await fs.writeFile('context.json', ...);
    await fs.writeFile('queries.json', ...);
    // ... etc
}
```

### In-Memory Storage

| Variable | Type | Purpose |
|----------|------|---------|
| `allContext` | `StepAction[]` | All steps taken |
| `allKnowledge` | `KnowledgeItem[]` | Intermediate answers |
| `allURLs` | `Record<string, SearchSnippet>` | Discovered URLs |
| `weightedURLs` | `BoostedSearchSnippet[]` | Ranked URLs |
| `allWebContents` | `Record<string, WebContent>` | Crawled content |
| `visitedURLs` | `string[]` | Visited URLs |
| `badURLs` | `string[]` | Failed URLs |

---

## URL Processing Pipeline

### URL Ranking

**File:** `src/utils/url-tools.ts`

**Boost Factors:**
- `freqBoost` - URL frequency in results
- `hostnameBoost` - Hostname boosting
- `pathBoost` - Path relevance
- `jinaRerankBoost` - Jina reranker score

**Processing Steps:**
1. Normalize URL (remove tracking, sessions)
2. Calculate boost scores
3. Rank by final score
4. Keep top K per hostname (diversity)

### URL Normalization

```typescript
normalizeUrl(urlString, options = {
    removeAnchors: true,
    removeSessionIDs: true,
    removeUTMParams: true,
    removeTrackingParams: true,
    removeXAnalytics: true
})
```

---

## Evaluation Pipeline

### Question Evaluation

**File:** `src/tools/evaluator.ts:560-596`

Determines which evaluation types to apply:

```typescript
export async function evaluateQuestion(
    question: string,
    trackers: TrackerContext,
    schemaGen: Schemas
): Promise<EvaluationType[]> {
    // Returns: definitive, freshness, plurality, completeness
}
```

### Answer Evaluation

**File:** `src/tools/evaluator.ts:622-677`

```typescript
export async function evaluateAnswer(
    question: string,
    action: AnswerAction,
    evaluationTypes: EvaluationType[],
    trackers: TrackerContext,
    allKnowledge: KnowledgeItem[],
    schemaGen: Schemas
): Promise<EvaluationResponse>
```

**Evaluation Order:**
1. `definitive` - Always first
2. `freshness` - If required
3. `plurality` - If required
4. `completeness` - If required
5. `strict` - Final rubric check

---

## Research Team (Parallel Processing)

### Research Planner

**File:** `src/tools/research-planner.ts`

**Purpose:** Decompose complex topics into orthogonal subproblems

```typescript
export async function researchPlan(
    question: string,
    teamSize: number,
    soundBites: string,
    trackers: TrackerContext,
    schemaGen: Schemas
): Promise<string[]>
```

**System Prompt:**
```
You are a Principal Research Lead managing a team of {teamSize} junior researchers.
Your role is to break down a complex research topic into focused, manageable subproblems.

Orthogonality Requirements:
- Each subproblem must address a fundamentally different aspect/dimension
- Use different decomposition axes
- Minimize subproblem overlap

Depth Requirements:
- Each subproblem should require 15-25 hours of focused research
- Must go beyond surface-level information
```

---

## Beast Mode (Fallback)

**File:** `src/agent.ts:1036-1076`

When token budget exceeded (85%), enters Beast Mode:

```typescript
if (!(thisStep as AnswerAction).isFinal) {
    const { system } = getPrompt(
        diaryContext,
        allQuestions,
        allKeywords,
        false,  // allowReflect
        false,  // allowRead
        false,  // allowSearch
        false,  // allowCoding
        true,   // allowAnswer
        allKnowledge,
        weightedURLs,
        true,   // beastMode
    );
    
    schema = SchemaGen.getAgentSchema(false, false, true, false, false, question);
    // Generate with maximum force
}
```

---

## Search APIs Used

### Jina Search API

**Endpoint:** `https://svip.jina.ai/`

**File:** `src/tools/jina-search.ts`

```typescript
export async function search(
    query: SERPQuery,
    domain?: string,
    num?: number,
    meta?: string,
    tracker?: TokenTracker
): Promise<{ response: JinaSearchResponse }>
```

### Jina Reader API

**Endpoint:** `https://r.jina.ai/`

**File:** `src/tools/read.ts`

```typescript
export async function readUrl(
    url: string,
    withAllLinks?: boolean,
    tracker?: TokenTracker,
    withAllImages?: boolean
): Promise<{ response: ReadResponse }>
```

---

## Patterns Used

### 1. Gap-Driven Iteration

Questions stored in `gaps[]` queue, processed round-robin:
```typescript
const currentQuestion: string = gaps[totalStep % gaps.length];
```

### 2. Action Flags

Actions can be disabled after failure:
```typescript
allowAnswer = false;   // After failed answer
allowSearch = false;    // After failed search
allowRead = false;     // After failed visit
allowReflect = false;  // After no new questions
```

### 3. Knowledge Building

Intermediate knowledge built incrementally:
```typescript
allKnowledge.push({
    question: currentQuestion,
    answer: thisStep.answer,
    type: 'qa',
    updated: formatDateBasedOnType(new Date(), 'full')
});
```

### 4. De-duplication

Queries and questions always deduplicated:
```typescript
const { unique_queries } = await dedupQueries(items, existingItems, tokenTracker);
```

### 5. Token Budget Tracking

Every operation tracks token usage:
```typescript
tokenTracker.trackUsage('search', { totalTokens: credits, ... });
tokenTracker.trackUsage('read', { totalTokens: tokens, ... });
```

---

## Configuration Constants

**File:** `src/utils/schemas.ts`

```typescript
export const MAX_URLS_PER_STEP = 5
export const MAX_QUERIES_PER_STEP = 5
export const MAX_REFLECT_PER_STEP = 2
export const MAX_CLUSTERS = 5
```

---

## Types Reference

**File:** `src/types.ts`

### Core Types

```typescript
type StepAction = SearchAction | AnswerAction | ReflectAction | VisitAction | CodingAction;

type SearchAction = {
    action: "search";
    think: string;
    searchRequests: string[];
};

type AnswerAction = {
    action: "answer";
    think: string;
    answer: string;
    references: Reference[];
    isFinal?: boolean;
    mdAnswer?: string;
};

type ReflectAction = {
    action: "reflect";
    think: string;
    questionsToAnswer: string[];
};

type VisitAction = {
    action: "visit";
    think: string;
    URLTargets: number[];
};

type KnowledgeItem = {
    question: string;
    answer: string;
    references?: Reference[];
    type: 'qa' | 'side-info' | 'chat-history' | 'url' | 'coding';
    updated?: string;
};
```

---

## Execution Flow Summary

```
1. Initialize
   ├── Set up token budget (default: 1M tokens)
   ├── Create knowledge/base messages
   └── Initialize URL storage

2. Main Loop (while budget < 85%)
   ├── Get current question from gaps
   ├── Generate prompt with context
   ├── Call model with schema
   ├── Execute chosen action
   │   ├── search → execute queries → store URLs
   │   ├── visit → fetch URLs → extract content
   │   ├── reflect → generate sub-questions → add to gaps
   │   └── answer → evaluate → check quality
   └── Track tokens

3. Beast Mode (budget >= 85%)
   └── Generate final answer with all available knowledge

4. Finalize
   ├── Build markdown answer
   ├── Add references
   └── Return result
```

---

## Related Files

| File | Purpose |
|------|---------|
| `src/agent.ts` | Main orchestration |
| `src/utils/schemas.ts` | All Zod schemas |
| `src/utils/safe-generator.ts` | Model calling |
| `src/tools/jina-search.ts` | Search API |
| `src/tools/read.ts` | Reader API |
| `src/tools/query-rewriter.ts` | Query expansion |
| `src/tools/evaluator.ts` | Answer evaluation |
| `src/tools/url-tools.ts` | URL processing |
| `src/tools/research-planner.ts` | Team parallelization |
| `src/types.ts` | Type definitions |