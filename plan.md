
1. *Refactor `brain.py` completely.*
   - Remove `pandas`, `create_pandas_dataframe_agent`, `_df_inventory`, `_inventory_timestamp`, `_load_inventory`, `reload_inventory`, `_get_sales_agent`, `SafePythonAstREPLTool`, `_find_similar_cars`.
   - Add `_search_cars(query: str) -> str`:
     - Initialize Vertex AI TextEmbeddingModel (`text-embedding-004`).
     - Generate embedding for the query.
     - Execute vector search using `_db_client.collection("inventory_vectors").find_nearest(...)`.
     - Format results as a string.
   - Modify `process_message`:
     - Remove logic related to `pandas_agent` and inventory reloading.
     - Call `_search_cars` with the user query.
     - Construct a prompt including the search results (context) and the user query.
     - Invoke `ChatVertexAI` directly with this prompt.
     - Ensure image analysis and audio handling logic remains (checking for regression).
   - Ensure `_init_services` initializes necessary components.
   - Maintain `_analyze_tone_and_intent`, `_analyze_image`, `_analyze_audio`, `_should_ask_feedback`, `_handle_negative_feedback`, `_update_user_profile`, `_manage_history`, `_audit_response`, `_check_is_duplicate`, `_text_to_speech`.

2. *Update `main.py`.*
   - In `/sync-inventory` route, replace `brain.reload_inventory()` with `ingestor.sync_inventory(request)`.

3. *Update `requirements.txt`.*
   - Remove `pandas`.
   - Remove `langchain-experimental`.

4. *Complete pre commit steps.*
   - Create a test file `tests/test_brain_vector_search.py` to mock `_db_client` and `TextEmbeddingModel` and verify `_search_cars` logic and `process_message` integration.
   - Run the new tests.
   - Verify `ingestor.py` is importable and has `sync_inventory`.

5. *Submit the change.*
