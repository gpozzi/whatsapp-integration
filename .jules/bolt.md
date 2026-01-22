## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-22 - [Parallel RAG & Intent Analysis]
**Learning:** Sequential execution of Intent Analysis (LLM) and Vector Search (Embeddings + DB) caused unnecessary latency (~200ms+). By implementing "Optimistic Search" (running search in parallel with intent analysis), we reduce latency to the slowest of the two operations.
**Action:** Added global `ThreadPoolExecutor` to `brain.py` and parallelized `_analyze_tone_and_intent` and `_search_cars`.
**Testing Insight:** Unit tests involving global `ThreadPoolExecutor` and background tasks (like `_update_user_profile`) are prone to race conditions where stale tasks consume mock side effects. The fix is to explicitly mock `_executor.submit` in tests to control task execution and ignore background noise.
