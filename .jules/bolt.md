## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-02-04 - [Parallel Architecture for RAG]
**Learning:** The RAG pipeline was strictly sequential: History Fetch -> Intent Analysis -> Vector Search. However, Vector Search is independent of Intent Analysis (mostly) and History Fetch.
**Action:** Implemented an "Optimistic Search" pattern using `ThreadPoolExecutor`. `_manage_history` (read) and `_search_cars` (search) now run in parallel. `_analyze_tone_and_intent` runs after history is fetched but concurrently with the tail end of the search.
**Note:** When testing threaded code with `unittest.mock`, ensure all background tasks are mocked or handled. Unpatched functions in threads can silently crash or pollute state, causing flaky tests (e.g., `_search_cars` trying to init credentials in a test environment).
