## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-26 - [Async Executor Crash & Testing Threads]
**Learning:** Implementing `ThreadPoolExecutor` for background tasks (like `_update_user_profile` in `brain.py`) exposed a critical bug where the executor was undefined, causing crashes. Furthermore, unmocked background threads in unit tests caused race conditions and side-effect consumption issues (e.g. consuming `mock_llm.invoke` results meant for the main thread) in subsequent tests.
**Action:** Defined the global `_executor` in `brain.py` to fix the crash and enable async processing. Updated all relevant unit tests (`test_deduplication`, `test_audio`, etc.) to patch `brain._executor`, preventing thread leakage and ensuring test isolation.
