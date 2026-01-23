## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-23 - [Optimistic Search & Executor Crash Fix]
**Learning:**
1. The global `_executor` variable in `brain.py` was undefined, causing crashes in background tasks (profile updates).
2. Global `ThreadPoolExecutor` leaks tasks across unit tests if not isolated. Tasks from one test can consume mocks from another test (Ghost Task pattern), leading to flaky failures.
**Action:**
1. Defined `_executor` in `brain.py`.
2. Implemented "Optimistic Search" (parallelizing Intent Analysis and Vector Search) to reduce latency by ~500ms.
3. Updated unit tests to isolate `_executor` (replace with local executor and wait for shutdown) to prevent state leakage.
