## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-25 - [Async Profile Updates]
**Learning:** The `_executor` variable was used in `brain.py` for background tasks but was undefined, causing `NameError` and preventing async operations.
**Action:** Defined `_executor = ThreadPoolExecutor(max_workers=4)` globally in `brain.py` and added `tests/test_brain_executor.py` to verify it is used correctly. Also updated `tests/test_deduplication.py` to patch `_executor` to avoid test flakiness due to background threads consuming mocks.
