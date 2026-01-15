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

class TestDeduplication(unittest.TestCase):

    def setUp(self):
        # Reset Global State in Brain
        brain._db_client = None
        brain._safety_model = None

        # Explicitly overwrite brain.firestore with a fresh Mock
        brain.firestore = MagicMock()

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

        # Mock LLM instances - Use separate mocks for Sales and Safety to avoid call counting confusion
        mock_sales_llm = MagicMock()
        mock_safety_model = MagicMock()

        mock_vertex.return_value = mock_sales_llm # Default, though we override via patch

        # Mock responses

        # Sales Agent (Main LLM)
        mock_sales_llm.invoke.return_value = MagicMock(content="Response Text")

        # Safety Model (Intent, Audit, Feedback)
        # 1. Intent/Tone analysis
        # 2. Audit (Parallel)
        # 3. Feedback Decision (Parallel)

        # Note: Audit and Feedback run in parallel. We use "SI" (Positive) for both so order doesn't matter.
        # "SI" for Audit -> Safe (no "PELIGRO")
        # "SI" for Feedback -> True
        mock_safety_model.invoke.side_effect = [
            MagicMock(content="CATEGORY: SALES_QUERY | TONE: DIRECTO"), # Intent
            MagicMock(content="SI"), # Parallel 1 (Audit/Feedback)
            MagicMock(content="SI")  # Parallel 2 (Audit/Feedback)
        ]

        # We also need to mock _search_cars or ensure it doesn't crash
        # _search_cars calls inventory_vectors.find_nearest().get()
        mock_vectors_coll.find_nearest.return_value.get.return_value = [] # No results, fine

        # Patch _init_services to return our LLM
        with patch('brain._init_services', return_value=mock_sales_llm):
            # Manually set _db_client because we bypassed _init_services
            brain._db_client = mock_db
            brain._safety_model = mock_safety_model # Explicit safety model

            response = brain.process_message("Hello", "123456", "msg_new_123")

        # Verification
        # Since parallel execution enables feedback (SI), check containment
        self.assertIn("Response Text", response)
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
