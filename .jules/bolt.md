## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-31 - [Optimistic Vector Search]
**Learning:** Background threads in `ThreadPoolExecutor` (used for optimistic concurrency) can persist across unit tests, causing race conditions where a lingering thread from one test consumes a mock side-effect in a subsequent test.
**Action:** Always patch `_executor` in unit tests with a synchronous mock or ensure strictly isolated tearDown to prevent test pollution.
