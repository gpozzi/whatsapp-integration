## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-02-02 - [Parallel Message Processing]
**Learning:** Sequential execution of independent heavy tasks (LLM Intent Analysis, LLM Image Analysis, Vector Search) in `brain.process_message` causes unnecessary latency. Thread pollution from global `ThreadPoolExecutor` in unit tests can cause flaky failures ("phantom calls") when `MagicMock` instances are shared or reused.
**Action:** Implemented parallel execution using a global `ThreadPoolExecutor` in `brain.py`. Refactored `tests/test_deduplication.py` to use a `SynchronousExecutor` and distinct mocks for different LLM roles (`mock_sales` vs `mock_safety`) to prevent side-effect collisions from zombie threads.
