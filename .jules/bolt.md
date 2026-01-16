## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-16 - [Parallel Execution and Async Tasks]
**Learning:** `brain.py` contained a call to `_executor` in `_manage_history` but `_executor` was not defined, causing a potential crash. Additionally, sequential execution of independent LLM and DB tasks increased latency.
**Action:** Defined a global `ThreadPoolExecutor` in `brain.py`. Utilized it to parallelize:
1. Intent Analysis and Vector Search (Optimistic Search).
2. Safety Audit and Feedback Decision.
This reduces end-to-end latency by overlapping I/O-bound operations.
