## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-18 - [Parallel Execution and Test Isolation]
**Learning:** When using a global `ThreadPoolExecutor` (or similar shared state) in a module, unit tests can become polluted if background threads persist across test cases. This is especially dangerous when mocks are swapped (e.g. `side_effect` iterators), as a lingering thread might consume a side-effect intended for a subsequent test.
**Action:** Implemented "Optimistic Search" by parallelizing Intent Analysis and Vector Search using `ThreadPoolExecutor`. Crucially, updated unit tests to mock the `_executor` to run synchronously (or return immediate mocks), ensuring test isolation and deterministic behavior.
