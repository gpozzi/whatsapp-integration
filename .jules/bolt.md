## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-30 - [Parallel Execution of Intent Analysis and Vector Search]
**Learning:** Sequential execution of independent tasks (LLM Intent Analysis and Vector Search) introduced unnecessary latency. Running them in parallel using `ThreadPoolExecutor` hides the latency of the faster task.
**Action:** Refactored `process_message` to use optimistic concurrency. Also learned that global executors persist across tests, requiring explicit shutdown/cleanup in `setUp` to prevent state pollution and race conditions in unit tests.
