## 2026-01-11 - [Initial Performance Optimization]
**Learning:** Instantiating `VertexAIEmbeddings` for every user query (in `_search_cars`) creates significant overhead due to authentication and connection setup.
**Action:** Implemented a Singleton pattern for the embeddings service in `brain.py`, initializing it once in `_init_services` and reusing it globally. Future services should follow this pattern unless thread-safety is a concern.

## 2026-01-14 - [Dependency Mocks in Tests]
**Learning:** Adding imports from submodules (e.g., `from google.api_core.exceptions import AlreadyExists`) breaks unit tests that unsafely mock the root package (e.g., `sys.modules['google'] = MagicMock()`) because the mock object is not a package.
**Action:** When mocking large libraries like `google`, verify if tests are mocking the root package. If so, either remove the root mock or explicitly mock the imported submodules (e.g., `sys.modules['google.api_core'] = MagicMock()`) to prevent `ImportError`.
