# RAGnostic — Production-Grade Adaptive RAG System
## Complete Implementation Specification for an AI Coding Agent

You are a senior AI/ML software engineer and full-stack architect with 5–10+ years of experience building production-grade AI applications, Retrieval-Augmented Generation (RAG) systems, semantic search systems, backend APIs, and modern web applications.

Build the complete **RAGnostic** application according to the specification below.

Do not treat this as a simple CRUD application. The core purpose of the project is to implement an **adaptive Retrieval-Augmented Generation system** that dynamically decides how deeply to retrieve information based on semantic retrieval confidence.

The implementation must be modular, clean, extensible, testable, and production-oriented.

---

# 1. PROJECT OBJECTIVE

RAGnostic is an adaptive RAG system.

The system should initially perform standard semantic retrieval using ChromaDB.

After semantic retrieval, the system evaluates the retrieval confidence using predefined thresholds.

Depending on the confidence score, it dynamically chooses one of three retrieval depths:

```text
0-Hop → Standard Semantic Retrieval
1-Hop → Semantic Retrieval + One Graph Expansion
2-Hop → Semantic Retrieval + Two Graph Expansions
```

The system must NOT use a machine-learning contextual bandit in V1.

The system must NOT use an LLM to decide the retrieval strategy.

The retrieval strategy must be determined deterministically by a configurable threshold-based controller.

The LLM is responsible only for generating the final answer from the retrieved context.

---

# 2. CORE ARCHITECTURE

The repository MUST contain exactly two primary application folders:

```text
ragnostic/
│
├── client/
│   └── frontend application
│
├── server/
│   └── backend application
│
├── README.md
├── .gitignore
└── .env.example
```

Do not mix frontend and backend code.

The client must contain only frontend-related code.

The server must contain only backend-related code.

The architecture must allow the two applications to be developed, tested, deployed, and scaled independently.

---

# 3. TECHNOLOGY STACK

## Frontend

Use:

- React.js
- TypeScript
- Vite
- Modern CSS or a clean styling solution
- React Router if routing is required
- Fetch API or Axios for backend communication

The frontend must be responsive and optimized for desktop and mobile layouts.

Do not introduce unnecessary UI libraries.

The interface should have a clean, minimal dark theme inspired by modern AI chat applications such as ChatGPT/Grok, but do not copy proprietary UI exactly.

---

# 4. BACKEND

Use:

- Node.js
- NestJS
- TypeScript

NestJS must be organized using proper modules, controllers, services, DTOs, interfaces, configuration, and dependency injection.

Do not create one giant service.

The backend must have clear separation between:

```text
API layer
Business logic
Retrieval logic
Graph logic
Database access
Embedding logic
LLM integration
Configuration
Validation
Error handling
```

---

# 5. DATABASE ARCHITECTURE

The application uses two storage systems with clearly separated responsibilities.

## ChromaDB

ChromaDB is responsible for:

- Vector embeddings
- Semantic similarity search
- Vector metadata
- Retrieving relevant chunks

Conceptually:

```text
Query
 ↓
Embedding
 ↓
ChromaDB
 ↓
Top-K chunks
 ↓
Similarity scores
```

ChromaDB should NOT be treated as the primary source of truth.

---

## Supabase PostgreSQL

Supabase PostgreSQL is the persistent source of truth for structured knowledge.

Use PostgreSQL for:

```text
documents
chunks
entities
relationships
```

The graph representation must be implemented using relational tables.

Do NOT introduce Neo4j in V1.

Do NOT introduce NetworkX in V1.

The PostgreSQL database should represent the graph through entity and relationship tables.

Example:

```text
entities

id
name
type
metadata
created_at
```

```text
relationships

id
source_entity_id
target_entity_id
relation_type
metadata
created_at
```

Chunks should maintain relationships with documents and, where appropriate, entities.

---

# 6. IMPORTANT DATABASE PRINCIPLE

PostgreSQL is the persistent source of truth.

ChromaDB is a retrieval index.

If ChromaDB is deleted, the system should theoretically be able to rebuild its vector collection from the chunks stored in PostgreSQL.

Do not make the application dependent on ChromaDB being the only location containing important information.

---

# 7. RECOMMENDED DATABASE MODEL

Implement a clean relational schema approximately following this structure.

## documents

```text
id
title
source
content
metadata
created_at
updated_at
```

## chunks

```text
id
document_id
chunk_index
content
metadata
created_at
```

## entities

```text
id
name
type
metadata
created_at
```

## chunk_entities

```text
chunk_id
entity_id
```

## relationships

```text
id
source_entity_id
target_entity_id
relation_type
metadata
created_at
```

Use UUIDs where appropriate.

Use foreign keys.

Add appropriate indexes.

Do not duplicate information unnecessarily.

---

# 8. DATA INGESTION PIPELINE

The system must support document ingestion.

The ingestion pipeline should conceptually be:

```text
Document
   ↓
Text Extraction
   ↓
Text Cleaning
   ↓
Chunking
   ↓
Store Documents/Chunks in PostgreSQL
   ↓
Generate Embeddings
   ↓
Store Embeddings in ChromaDB
   ↓
Create/Store Graph Information
```

Keep each stage modular.

Do NOT place the entire ingestion pipeline inside one service.

Use separate components such as:

```text
DocumentService
ChunkingService
EmbeddingService
VectorStoreService
GraphConstructionService
```

---

# 9. CHUNKING

Implement a configurable chunking strategy.

The chunk size and overlap must NOT be hardcoded throughout the application.

Place configuration values in environment/configuration.

For example:

```text
CHUNK_SIZE
CHUNK_OVERLAP
```

The chunking component should be replaceable in the future.

Create an abstraction/interface for the chunker.

Example conceptual interface:

```text
ChunkingStrategy
```

The initial implementation can use a straightforward recursive or token-aware chunking strategy.

---

# 10. EMBEDDING ARCHITECTURE

Do not tightly couple the entire application to one embedding provider.

Create an abstraction such as:

```text
EmbeddingProvider
```

The initial implementation should use a practical embedding model/provider.

The model name must come from configuration.

Example:

```text
EMBEDDING_MODEL
```

The embedding service should expose operations such as:

```text
embedText()
embedDocuments()
embedQuery()
```

Do not duplicate embedding logic in controllers.

---

# 11. VECTOR STORE ABSTRACTION

Create a vector-store interface.

Conceptually:

```text
VectorStore
 ├── add()
 ├── search()
 ├── delete()
 └── rebuild()
```

Implement:

```text
ChromaVectorStore
```

The rest of the application should depend on the abstraction rather than directly accessing ChromaDB everywhere.

This is important because a future version may replace ChromaDB with another vector database.

---

# 12. GRAPH RETRIEVAL ABSTRACTION

Create a graph retrieval abstraction.

Conceptually:

```text
GraphRetriever
 ├── getOneHop()
 └── getTwoHop()
```

The initial implementation must use PostgreSQL/Supabase.

Do not introduce a dedicated graph database.

The graph service should receive entity/chunk identifiers and return connected nodes/chunks.

---

# 13. RETRIEVAL PIPELINE

The retrieval process is the most important part of RAGnostic.

Implement it carefully.

The complete flow is:

```text
User Query
    ↓
Query Validation
    ↓
Query Embedding
    ↓
ChromaDB Semantic Search
    ↓
Top-K Results
    ↓
Similarity Evaluation
    ↓
Threshold Controller
    ↓
0-Hop / 1-Hop / 2-Hop
    ↓
Context Assembly
    ↓
LLM
    ↓
Final Answer
```

---

# 14. RETRIEVAL DEPTH

Define retrieval depth explicitly.

```text
0 = Semantic retrieval only
1 = One graph expansion
2 = Two graph expansions
```

Use an enum or equivalent type.

Do not represent retrieval depth using arbitrary strings throughout the codebase.

---

# 15. THRESHOLD CONTROLLER

Create a dedicated service:

```text
ThresholdController
```

It must be responsible only for deciding retrieval depth.

The controller must NOT call the LLM.

The controller must NOT directly access ChromaDB.

The controller must NOT directly access PostgreSQL.

It should receive retrieval-confidence information and return a retrieval decision.

Example conceptual behavior:

```text
if score >= HIGH_THRESHOLD:
    depth = 0

else if score >= LOW_THRESHOLD:
    depth = 1

else:
    depth = 1
```

After performing 1-hop retrieval, the system must evaluate the resulting retrieval confidence.

If the confidence is sufficient:

```text
stop
```

Otherwise:

```text
perform 2-hop retrieval
```

The exact thresholds must come from configuration.

Example:

```text
HIGH_THRESHOLD=0.75
LOW_THRESHOLD=0.60
MAX_HOPS=2
```

These are initial configurable values, NOT scientifically validated final values.

Do not claim that 0.75 or 0.60 is universally correct.

---

# 16. THRESHOLD DECISION LOGIC

Implement the adaptive logic approximately as:

```text
Step 1:
Perform semantic retrieval.

Step 2:
Calculate retrieval confidence.

Step 3:

If confidence >= HIGH_THRESHOLD:
    use 0-hop context.

Otherwise:
    perform 1-hop graph expansion.

Step 4:
Evaluate the resulting retrieval confidence.

If confidence >= HIGH_THRESHOLD:
    use 1-hop context.

Otherwise:
    perform 2-hop graph expansion.

Step 5:
Use the final retrieved context for generation.
```

Maximum retrieval depth must be configurable but default to 2.

Never allow uncontrolled graph traversal.

---

# 17. IMPORTANT: CONFIDENCE SCORE DESIGN

Do not blindly assume that one raw similarity score is a universal measure of retrieval quality.

Initially, use the top semantic similarity score as the basic confidence signal.

However, isolate this logic behind an abstraction such as:

```text
RetrievalConfidenceEvaluator
```

The initial implementation can use:

```text
confidence = topResultSimilarity
```

Later, this can be upgraded to:

```text
top-k average
score distribution
score margin
retrieval coverage
reranker score
hybrid confidence
```

without changing the rest of the retrieval architecture.

This is essential for future research iterations.

---

# 18. GRAPH EXPANSION

When 1-hop retrieval is selected:

```text
Semantic Results
      ↓
Identify anchor chunks/entities
      ↓
PostgreSQL
      ↓
Find directly connected entities/chunks
      ↓
Retrieve corresponding chunk content
```

When 2-hop retrieval is selected:

```text
Anchor
  ↓
Neighbors
  ↓
Neighbors of neighbors
```

Prevent duplicate nodes.

Prevent cycles from causing infinite traversal.

Respect:

```text
MAX_HOPS
MAX_GRAPH_NODES
```

Use configurable limits.

---

# 19. CONTEXT ASSEMBLY

Create a dedicated:

```text
ContextBuilder
```

The context builder should:

1. Accept semantic results.
2. Accept graph-expanded results.
3. Remove duplicate chunks.
4. Preserve source metadata.
5. Respect a configurable context limit.
6. Produce a clean context object for the LLM.

Do not construct prompts inside database services.

---

# 20. NO RERANKER IN V1

Do NOT implement a reranking model in V1.

Do NOT use CrossEncoder reranking.

Do NOT use an LLM-based reranker.

However, create a clean abstraction point so that reranking can be added later.

For example:

```text
RerankingService
```

or an interface such as:

```text
Reranker
```

The initial implementation should effectively be a no-op/pass-through strategy.

Do not allow this abstraction to add unnecessary complexity to V1.

Future architecture:

```text
Retrieval
   ↓
Reranker
   ↓
Context Builder
   ↓
LLM
```

---

# 21. NO CONTEXTUAL BANDIT IN V1

Do NOT implement:

- Reinforcement learning
- Contextual bandits
- Policy networks
- Reward models
- Learned retrieval policies

These are future extensions.

The V1 policy is deterministic and threshold-based.

Create clean interfaces so a future policy implementation can replace the threshold controller.

Conceptually:

```text
RetrievalPolicy
```

Initial implementation:

```text
ThresholdRetrievalPolicy
```

Future implementation:

```text
BanditRetrievalPolicy
```

The rest of the system should not need major architectural changes when this happens.

---

# 22. LLM GENERATION

The LLM should be called only after retrieval has finished.

The LLM must NOT decide:

```text
0-hop
1-hop
2-hop
```

The LLM is a generation component only.

Create an abstraction:

```text
LLMProvider
```

with methods such as:

```text
generate()
```

The initial provider must be configurable.

Do not hardcode API keys.

Use environment variables.

---

# 23. PROMPT DESIGN

Create a dedicated prompt/template layer.

Do not write large prompt strings directly inside controllers.

The generation prompt should instruct the LLM to:

- Answer using the provided context.
- Avoid inventing unsupported information.
- Clearly indicate when the context does not contain enough information.
- Use retrieved evidence rather than unrelated model knowledge.
- Return a concise, useful answer.
- Preserve source references when available.

The prompt system must be replaceable.

---

# 24. CHAT API

Implement a clean API endpoint such as:

```text
POST /api/chat
```

Request:

```json
{
  "query": "What happens after the turbocharger compresses air?"
}
```

Response should contain at least:

```json
{
  "answer": "...",
  "retrieval": {
    "depth": 1,
    "confidence": 0.68,
    "strategy": "ONE_HOP"
  },
  "sources": []
}
```

Do not expose sensitive internal information.

The frontend should use this metadata to display useful retrieval information where appropriate.

---

# 25. HEALTH API

Implement:

```text
GET /api/health
```

It should return application health information.

Where practical, expose the status of:

```text
NestJS
PostgreSQL
ChromaDB
LLM provider
```

Do not expose credentials or sensitive configuration.

---

# 26. CORS

CORS MUST be implemented properly.

Do not use:

```text
origin: "*"
```

in production configuration.

The allowed frontend origin must come from an environment variable.

Example:

```text
CLIENT_URL=http://localhost:5173
```

NestJS should configure CORS during application bootstrap.

Support development and production environments separately.

---

# 27. ENVIRONMENT CONFIGURATION

Create:

```text
server/.env.example
client/.env.example
```

Never commit real secrets.

The server configuration should include values such as:

```text
NODE_ENV
PORT

CLIENT_URL

SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY

CHROMA_URL
CHROMA_COLLECTION

EMBEDDING_MODEL

LLM_API_KEY
LLM_MODEL

CHUNK_SIZE
CHUNK_OVERLAP

TOP_K

HIGH_THRESHOLD
LOW_THRESHOLD

MAX_HOPS
MAX_GRAPH_NODES
```

Only include variables that are actually used.

Validate environment variables at application startup.

Fail fast if required configuration is missing.

---

# 28. SECURITY

Implement basic production security practices.

Include:

- DTO validation
- Input sanitization where appropriate
- Request size limits
- CORS restrictions
- Environment-based secrets
- No API keys in frontend code
- No sensitive data in logs
- Proper HTTP error responses

Never expose:

```text
LLM API keys
Supabase service keys
database credentials
internal stack traces
```

to the React application.

---

# 29. ERROR HANDLING

Implement centralized error handling.

The API must return consistent responses.

Example:

```json
{
  "success": false,
  "error": {
    "code": "RETRIEVAL_FAILED",
    "message": "Unable to retrieve relevant context."
  }
}
```

Do not leak internal exceptions to users.

Log detailed errors server-side.

---

# 30. LOGGING

Implement structured logging.

Log important events such as:

```text
request received
query processed
semantic retrieval completed
similarity score
selected retrieval depth
graph traversal completed
LLM generation completed
request latency
errors
```

Do not log:

- API keys
- passwords
- authentication tokens
- sensitive user information

A useful retrieval log might look conceptually like:

```text
query_id=abc123
semantic_score=0.68
initial_depth=0
selected_depth=1
graph_nodes=7
latency_ms=420
```

---

# 31. REQUEST ID / QUERY ID

Generate a request/query identifier for each chat request.

Use it for:

- logging
- debugging
- tracing retrieval decisions

Return the identifier in the API response where appropriate.

---

# 32. FRONTEND DESIGN

The frontend must be extremely clean.

Use a modern dark theme.

The visual style should resemble a modern AI chat application.

Do not create a dashboard full of unnecessary cards.

The primary screen should be a conversation interface.

Suggested structure:

```text
┌─────────────────────────────────────────────┐
│ RAGnostic                                   │
├─────────────────────────────────────────────┤
│                                             │
│                                             │
│            Chat conversation                │
│                                             │
│                                             │
│                                             │
├─────────────────────────────────────────────┤
│ Ask RAGnostic...                       Send │
└─────────────────────────────────────────────┘
```

The interface should feel:

- Minimal
- Professional
- Dark
- Fast
- Uncluttered
- AI-oriented

---

# 33. FRONTEND COMPONENT STRUCTURE

Use reusable components.

For example:

```text
client/src/

├── components/
│   ├── chat/
│   │   ├── ChatContainer
│   │   ├── ChatMessage
│   │   ├── ChatInput
│   │   ├── TypingIndicator
│   │   └── SourceList
│   │
│   ├── layout/
│   │   ├── Header
│   │   └── Sidebar
│   │
│   └── common/
│
├── pages/
│   └── ChatPage
│
├── services/
│   └── api.ts
│
├── hooks/
│
├── types/
│
├── utils/
│
├── styles/
│
└── App.tsx
```

Adapt the structure if needed, but maintain the same modular philosophy.

---

# 34. CHAT UI

The chat interface should support:

- User messages
- Assistant messages
- Loading state
- Error state
- Empty state
- Source references
- Retrieval metadata
- Copy answer button
- Clear conversation button

Do not overdesign it.

The main focus is the conversation.

---

# 35. RETRIEVAL METADATA UI

Because RAGnostic is an adaptive retrieval research project, provide an optional compact metadata section below each assistant response.

For example:

```text
Retrieval
1-hop · confidence 0.68 · 7 context nodes
```

For a standard semantic query:

```text
Retrieval
0-hop · confidence 0.84
```

For two-hop:

```text
Retrieval
2-hop · confidence 0.57
```

Do not overwhelm normal users with technical information.

Make the metadata subtle and collapsible if necessary.

---

# 36. FRONTEND STATE MANAGEMENT

Do not introduce Redux unless genuinely necessary.

For V1, React state/hooks should be sufficient.

Create clean service functions for API communication.

Do not place API calls directly throughout UI components.

---

# 37. API CLIENT

Create a centralized API client.

For example:

```text
services/api.ts
```

It should handle:

```text
POST /api/chat
GET /api/health
```

The API base URL must come from frontend environment configuration.

Never hardcode production API URLs.

---

# 38. RESPONSIVENESS

The application must work properly on:

- Desktop
- Laptop
- Tablet
- Mobile

The chat input must remain accessible.

Avoid horizontal scrolling.

---

# 39. ACCESSIBILITY

Use:

- Semantic HTML
- Keyboard navigation
- Accessible buttons
- Proper labels
- Focus states
- Appropriate ARIA attributes where necessary
- Readable contrast

Do not sacrifice accessibility for visual design.

---

# 40. BACKEND MODULE STRUCTURE

Use a modular NestJS structure similar to:

```text
server/src/

├── app.module.ts
├── main.ts
│
├── config/
│   ├── configuration.ts
│   └── validation.ts
│
├── common/
│   ├── filters/
│   ├── interceptors/
│   ├── guards/
│   ├── decorators/
│   └── types/
│
├── chat/
│   ├── chat.controller.ts
│   ├── chat.service.ts
│   ├── dto/
│   └── interfaces/
│
├── ingestion/
│   ├── ingestion.controller.ts
│   ├── ingestion.service.ts
│   ├── chunking/
│   ├── embedding/
│   └── interfaces/
│
├── retrieval/
│   ├── retrieval.service.ts
│   ├── semantic/
│   ├── graph/
│   ├── policy/
│   ├── confidence/
│   └── context/
│
├── vector-store/
│   ├── vector-store.interface.ts
│   └── chroma/
│
├── graph-store/
│   ├── graph-store.interface.ts
│   └── postgres/
│
├── llm/
│   ├── llm.interface.ts
│   └── providers/
│
├── database/
│   └── supabase/
│
└── health/
    ├── health.controller.ts
    └── health.service.ts
```

Keep modules cohesive.

Do not create unnecessary abstraction layers merely for the sake of abstraction.

---

# 41. RETRIEVAL SERVICE DESIGN

The retrieval service should orchestrate components rather than implement every detail itself.

Conceptually:

```text
AdaptiveRetrievalService

    ↓
SemanticRetriever

    ↓
ConfidenceEvaluator

    ↓
RetrievalPolicy

    ↓
GraphRetriever

    ↓
ContextBuilder
```

This separation is extremely important.

The retrieval service should answer:

> "What steps need to happen?"

Individual services should answer:

> "How does that step happen?"

---

# 42. RETRIEVAL POLICY INTERFACE

Create an interface conceptually like:

```text
RetrievalPolicy

decide(context): RetrievalDecision
```

Initial implementation:

```text
ThresholdRetrievalPolicy
```

Future implementation:

```text
BanditRetrievalPolicy
```

Do not implement the bandit now.

The application should be able to replace the policy without rewriting the entire retrieval pipeline.

---

# 43. RETRIEVAL DECISION

Use a structured object rather than returning arbitrary strings.

Conceptually:

```text
RetrievalDecision

depth
reason
threshold
confidence
```

Example:

```json
{
  "depth": 1,
  "reason": "semantic_confidence_below_threshold",
  "confidence": 0.68,
  "threshold": 0.75
}
```

This will make debugging and future research evaluation much easier.

---

# 44. SOURCE TRACKING

Every retrieved chunk should retain metadata such as:

```text
chunkId
documentId
documentTitle
source
similarity
retrievalMethod
hopDepth
```

This enables the frontend to display sources and enables future evaluation.

---

# 45. NO DUPLICATE RETRIEVAL

When combining semantic and graph retrieval results:

- Deduplicate chunk IDs.
- Preserve the strongest/most relevant score.
- Track the retrieval path where useful.

Example:

```text
Chunk A
retrieved by semantic search
and
retrieved again through graph traversal
```

The final context must contain it only once.

---

# 46. PERFORMANCE REQUIREMENTS

Avoid unnecessary database calls.

Do not perform sequential requests when independent operations can safely run in parallel.

Use batching where appropriate.

Limit:

```text
TOP_K
MAX_GRAPH_NODES
MAX_HOPS
CONTEXT_SIZE
```

to prevent excessive computation.

Avoid loading an entire document corpus into memory during normal queries.

---

# 47. GRAPH QUERY PERFORMANCE

Add appropriate PostgreSQL indexes for:

```text
source_entity_id
target_entity_id
chunk_id
document_id
```

Avoid N+1 database queries.

Prefer batched queries.

For 2-hop traversal, use efficient SQL rather than fetching every node individually.

---

# 48. DATA INGESTION API

Create an ingestion endpoint.

For example:

```text
POST /api/ingestion
```

It should support adding documents to the knowledge base.

Keep ingestion separate from chat/query logic.

The frontend may initially provide a simple document upload/interface, but prioritize a clean backend ingestion pipeline.

---

# 49. TESTING

Implement tests for critical backend logic.

At minimum test:

## Threshold policy

```text
score >= high threshold → 0-hop

medium score → 1-hop

low score → deeper retrieval

maximum depth → never exceed 2
```

## Graph traversal

Test:

- 0-hop
- 1-hop
- 2-hop
- duplicate nodes
- cycles
- missing nodes
- disconnected nodes

## Context builder

Test:

- duplicate chunks
- empty results
- metadata preservation
- context size limits

## API

Test:

- valid query
- empty query
- malformed request
- retrieval failure
- LLM failure

---

# 50. CODE QUALITY REQUIREMENTS

The code must be:

- Clean
- Modular
- Typed
- Readable
- Maintainable
- Testable
- Consistent

Use meaningful names.

Avoid:

```text
data
temp
thing
stuff
helper2
serviceFinal
```

Prefer descriptive names.

Do not write massive files.

If a service becomes too large, split it by responsibility.

---

# 51. TYPESCRIPT REQUIREMENTS

Use strict TypeScript.

Enable:

```text
strict: true
```

Avoid `any`.

Use interfaces/types for:

```text
retrieval results
retrieval decisions
graph nodes
graph edges
chat requests
chat responses
LLM responses
embedding results
```

---

# 52. API VALIDATION

Use NestJS DTO validation.

Reject:

```text
empty queries
excessively large queries
invalid parameters
invalid IDs
```

Return appropriate HTTP status codes.

---

# 53. README

Create a comprehensive root README.

It must explain:

```text
What is RAGnostic?
Architecture
Technology stack
Database architecture
Retrieval algorithm
Threshold mechanism
0/1/2-hop strategy
Project structure
Environment variables
Installation
Database setup
ChromaDB setup
Running frontend
Running backend
Testing
Future extensions
```

Include architecture diagrams using Mermaid where useful.

---

# 54. SETUP EXPERIENCE

The project should be easy to run.

The README should clearly provide commands such as:

```text
git clone ...
cd ragnostic

cd server
npm install

cd ../client
npm install
```

Provide development commands.

Example:

```text
npm run dev
```

or equivalent.

Make sure the commands actually match the generated project.

Do not document commands that don't exist.

---

# 55. ROOT PROJECT SCRIPTS

If practical, provide root-level scripts to start both applications conveniently.

For example:

```text
npm run dev
```

could start:

```text
client
server
```

Use a clean approach such as concurrently if necessary.

---

# 56. DATABASE MIGRATIONS

Do not rely on manually creating tables through undocumented SQL.

Provide version-controlled database schema/migrations.

If Supabase migrations are used, include them in the repository.

The database schema must be reproducible.

---

# 57. SEED DATA

Provide a small seed dataset for development.

The seed dataset should demonstrate:

```text
documents
chunks
entities
relationships
```

Include enough interconnected data to demonstrate:

```text
0-hop
1-hop
2-hop
```

retrieval.

Do not require a huge dataset just to test the application.

---

# 58. DEMONSTRATION QUERY

Include several demonstration queries in the README.

For example:

```text
What is X?
```

should ideally demonstrate semantic retrieval.

Another query should require a direct relationship.

Another should require multi-hop reasoning.

The README should explain what behavior the developer should observe.

---

# 59. OBSERVABILITY

The backend should make it possible to inspect:

```text
query
initial semantic score
threshold
selected depth
number of semantic results
number of graph nodes
final context size
LLM latency
total latency
```

This information is extremely important for evaluating RAGnostic experimentally.

Provide structured logs.

Optionally expose non-sensitive retrieval metadata through the API.

---

# 60. EXPERIMENTAL EVALUATION READINESS

Design the backend so retrieval decisions can later be stored.

For example:

```text
query_id
query
initial_score
initial_depth
final_depth
threshold
number_of_chunks
latency
```

This should not be mandatory for basic operation, but the architecture should make adding an evaluation/telemetry table straightforward.

Do not build a huge analytics subsystem in V1.

---

# 61. FUTURE EXTENSIBILITY

The architecture must make these future additions possible without major rewrites:

```text
V2:
Reranker

V3:
Contextual Bandit

V4:
Learned Retrieval Policy

V5:
Hybrid Search

V6:
Streaming LLM responses

V7:
Advanced evaluation dashboard
```

The current architecture must not implement these features.

Create appropriate interfaces where they provide real architectural value.

Do not over-engineer.

---

# 62. WHAT MUST NOT BE IMPLEMENTED IN V1

Do NOT implement:

```text
Contextual bandit
Reinforcement learning
Reranker
Neo4j
NetworkX
Complex agentic workflows
Multi-agent architecture
Unnecessary microservices
Kubernetes
Distributed vector infrastructure
Overcomplicated authentication
```

The objective is a clean, modular, research-ready monolithic application.

---

# 63. MONOLITHIC BACKEND

Use a modular monolith.

Do NOT split NestJS into multiple backend services.

The architecture should be:

```text
React
   ↓
NestJS Modular Monolith
   ├── Chat
   ├── Retrieval
   ├── Ingestion
   ├── Graph
   ├── Vector Store
   ├── Embeddings
   └── LLM
```

This is appropriate for the current project scale.

---

# 64. FINAL QUERY EXECUTION MODEL

The complete execution path must be:

```text
User
 ↓
React
 ↓
POST /api/chat
 ↓
NestJS
 ↓
Validate query
 ↓
Generate query embedding
 ↓
ChromaDB semantic search
 ↓
Top-K results
 ↓
Calculate confidence
 ↓
ThresholdRetrievalPolicy
 ↓
 ┌──────────────────────────────┐
 │                              │
 │ confidence >= HIGH_THRESHOLD │
 │                              │
 └──────────────┬───────────────┘
                ↓
              0-Hop
                │
                ▼
          Context Builder


Otherwise
                ↓
             1-Hop
                ↓
        PostgreSQL Graph
                ↓
        Additional Chunks
                ↓
        Evaluate Confidence
                │
        ┌───────┴────────┐
        │                │
     sufficient       insufficient
        │                │
        ▼                ▼
      1-Hop             2-Hop
        │                │
        └───────┬────────┘
                ▼
         Context Builder
                ↓
              LLM
                ↓
             Answer
                ↓
              React
```

---

# 65. IMPORTANT IMPLEMENTATION PRINCIPLE

The code must reflect this separation:

```text
ChromaDB
= semantic retrieval

PostgreSQL
= persistent knowledge + graph relationships

Threshold Policy
= retrieval strategy decision

LLM
= answer generation
```

Do not blur these responsibilities.

---

# 66. FINAL DEVELOPMENT REQUIREMENT

Before considering the project complete, verify all of the following:

1. Client and server are completely separated.
2. React application runs successfully.
3. NestJS application runs successfully.
4. CORS works correctly.
5. Environment variables are validated.
6. PostgreSQL/Supabase integration works.
7. ChromaDB integration works.
8. Documents can be ingested.
9. Chunks are generated.
10. Embeddings are generated.
11. Semantic retrieval works.
12. Similarity scores are returned.
13. Threshold policy works.
14. 0-hop retrieval works.
15. 1-hop graph retrieval works.
16. 2-hop graph retrieval works.
17. Graph traversal prevents cycles/duplicates.
18. Context assembly works.
19. LLM generation works.
20. Chat API works.
21. Frontend chat interface works.
22. Loading/error states work.
23. Sources can be displayed.
24. Retrieval metadata can be displayed.
25. Tests exist for critical retrieval logic.
26. README contains complete setup instructions.
27. No secrets are committed.
28. No unnecessary dependencies are introduced.
29. TypeScript strict mode passes.
30. Production build succeeds for both client and server.

---

# 67. FINAL EXPECTATION

Do not merely generate code that "works."

Generate a codebase that another experienced engineer can open six months later and immediately understand.

Every major subsystem must have a single clear responsibility.

Prefer composition over tightly coupled services.

Prefer interfaces at genuine architectural boundaries.

Prefer configuration over hardcoded values.

Prefer deterministic behavior over hidden magic.

Prefer simple, reliable engineering over unnecessary complexity.

The final implementation should feel like a serious research-grade AI application that can later evolve into a production system.

After implementation, provide:

1. Complete project structure.
2. Explanation of important architectural decisions.
3. Setup instructions.
4. Environment variables required.
5. Database schema/migrations.
6. How ChromaDB is configured.
7. How threshold-based adaptive retrieval works.
8. How to run the complete application.
9. How to test the system.
10. Known limitations.
11. Recommended next implementation step for adding the reranker.

Do not claim the system is production-ready unless it has actually been validated.

Do not hide errors.

If a dependency, API, model, database configuration, or external service cannot be verified, clearly identify the issue and provide the correct integration boundary rather than inventing functionality.