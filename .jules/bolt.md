## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-28 - [Optimistic Search & Threading in Tests]
**Learning:** Implementing optimistic concurrency with `ThreadPoolExecutor` (global in `brain.py`) exposed hidden dependencies in unit tests. Specifically, `test_deduplication.py` relied on a shared `side_effect` iterator for LLM calls. The new background thread (`_search_cars`) consumed an item from this iterator unexpectedly because `_embeddings_service` wasn't mocked in that specific test, triggering a lazy initialization that used the shared mock.
**Action:** When introducing threaded logic, ensure unit tests isolate the function under test (e.g., using `@patch`) to prevent background threads from contaminating mock state or consuming side effects meant for the main thread.
