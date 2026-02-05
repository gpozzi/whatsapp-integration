## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-02-05 - [TTS Client Optimization & Executor Fix]
**Learning:** Google Cloud clients (especially gRPC ones like TextToSpeech) are expensive to instantiate. Reusing a singleton instance avoids connection overhead.
**Action:** Implement Singleton pattern for all Google Cloud clients in `_init_services` or similar initialization blocks.
**Note:** Found and fixed a critical bug where `_executor` was used but undefined in `brain.py`. Always check variable definition when refactoring globals.
