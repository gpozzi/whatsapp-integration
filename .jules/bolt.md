## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-27 - [Optimistic Search Implementation]
**Learning:** Sequential execution of LLM Intent Analysis and Vector Search introduced unnecessary latency. Since the "Happy Path" (Sales Query) requires both, they can be executed in parallel.
**Action:** Implemented Optimistic Search using `ThreadPoolExecutor` in `brain.py`. Both tasks are submitted simultaneously. We pay the cost of a potentially wasted search (on non-sales intents) to gain significant latency reduction on the primary use case.
