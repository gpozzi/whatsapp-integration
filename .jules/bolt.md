## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-21 - [Ingestor Resource Optimization]
**Learning:** Re-instantiating `VertexAIEmbeddings` for every inventory synchronization request in `ingestor.py` is inefficient, especially for batch updates or frequent syncs. This mirrors the pattern previously optimized in `brain.py`.
**Action:** Implemented a Singleton pattern for `VertexAIEmbeddings` in `ingestor.py` using a global `_embeddings_service` variable. This reduces authentication and connection overhead for inventory updates.
