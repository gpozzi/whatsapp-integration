import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# --- MOCK DEPENDENCIES BEFORE IMPORTING BRAIN ---
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()

# Ensure we can import brain
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import brain
import datetime

# Helper class to run tasks synchronously
class SynchronousExecutor:
    def submit(self, fn, *args, **kwargs):
        future = MagicMock()
        try:
            result = fn(*args, **kwargs)
            future.result.return_value = result
        except Exception as e:
            future.result.side_effect = e
        return future

class TestDeduplication(unittest.TestCase):

    def setUp(self):
        # Reset Global State in Brain
        brain._db_client = None
        brain._safety_model = None

        # Patch executor to run synchronously
        self.original_executor = brain._executor
        brain._executor = SynchronousExecutor()

        # Explicitly overwrite brain.firestore with a fresh Mock
        brain.firestore = MagicMock()

    def tearDown(self):
        brain._executor = self.original_executor

    @patch('brain.ChatVertexAI')
    @patch('brain.Vector')
    def test_deduplication(self, mock_vector_cls, mock_vertex):
        """Test that duplicate message IDs are handled correctly."""

        # Configure the Firestore Mock we injected in setUp
        mock_db = MagicMock()
        brain.firestore.Client.return_value = mock_db

        # Mock Collections via side_effect
        mock_processed_coll = MagicMock()
        mock_history_coll = MagicMock()
        mock_vectors_coll = MagicMock()

        def collection_side_effect(name):
            if name == 'processed_messages':
                return mock_processed_coll
            elif name == 'inventory_vectors':
                return mock_vectors_coll
            return mock_history_coll # Default for chats_whatsapp

        mock_db.collection.side_effect = collection_side_effect

        # Mock Documents
        mock_processed_doc = MagicMock()
        mock_processed_coll.document.return_value = mock_processed_doc

        mock_history_doc = MagicMock()
        mock_history_coll.document.return_value = mock_history_doc

        # --- Test Case 1: New Message (Not a Duplicate) ---
        mock_processed_doc.get.return_value.exists = False # Document doesn't exist

        # Mock LLM instances
        mock_llm_instance = MagicMock()
        mock_vertex.return_value = mock_llm_instance

        # Mock responses
        # 1. Intent/Tone analysis
        # 2. RAG Response
        # 3. Safety Check
        # 4. Feedback Decision (Optional)
        # 5. User Profile Update (Background task running synchronously now)

        responses = iter([
            MagicMock(content="CATEGORY: SALES_QUERY | TONE: DIRECTO"), # Intent
            MagicMock(content="Response Text"), # Sales Agent Response
            MagicMock(content="APROBADO"), # Audit
            MagicMock(content="NO"), # Feedback
            MagicMock(content="{}") # User Profile Update
        ])

        def smart_side_effect(prompt_or_messages):
            # Extract text from prompt arg
            text = ""
            if isinstance(prompt_or_messages, str):
                text = prompt_or_messages
            elif isinstance(prompt_or_messages, list):
                 # List of BaseMessage
                 text = prompt_or_messages[0].content if prompt_or_messages else ""
            elif hasattr(prompt_or_messages, 'content'):
                text = prompt_or_messages.content

            # Detect stale prompt from test_brain_vector_search (lingering background task)
            if "Toyota Corolla" in text or "Busco un auto" in text:
                return MagicMock(content="STALE_TASK_RESPONSE")

            # Return next item
            try:
                return next(responses)
            except StopIteration:
                return MagicMock(content="")

        # We also need to mock _search_cars or ensure it doesn't crash
        mock_vectors_coll.find_nearest.return_value.get.return_value = [] # No results, fine

        mock_llm_instance.invoke.side_effect = smart_side_effect

        # Patch _init_services to return our LLM
        with patch('brain._init_services', return_value=mock_llm_instance):
            # Manually set _db_client because we bypassed _init_services
            brain._db_client = mock_db
            brain._safety_model = mock_llm_instance # Reuse for simplicity

            response = brain.process_message("Hello", "123456", "msg_new_123")

        # Verification
        self.assertEqual(response, "Response Text")
        mock_processed_doc.set.assert_called_once() # Should have saved the ID

        # --- Test Case 2: Duplicate Message ---
        mock_processed_doc.reset_mock()
        mock_processed_doc.set.reset_mock()
        mock_processed_doc.get.return_value.exists = True # Document exists

        response = brain.process_message("Hello Again", "123456", "msg_existing_123")

        # Verification
        self.assertIsNone(response)
        mock_processed_doc.set.assert_not_called() # Should NOT save again

if __name__ == '__main__':
    unittest.main()
