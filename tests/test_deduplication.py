import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# --- MOCK DEPENDENCIES BEFORE IMPORTING BRAIN ---
sys.modules['pandas'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
sys.modules['langchain_core'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()

# Ensure we can import brain
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import brain
import datetime

class TestDeduplication(unittest.TestCase):

    def setUp(self):
        # Reset Global State in Brain
        brain._db_client = None
        brain._df_inventory = MagicMock() # Mock it so it's not None
        brain._inventory_timestamp = datetime.datetime.now(datetime.timezone.utc) # Fresh
        # brain._sales_agent = None  <-- Removed
        brain._safety_model = None

        # Explicitly overwrite brain.firestore with a fresh Mock
        # This ensures that when brain calls firestore.Client, it uses OUR mock
        brain.firestore = MagicMock()

    @patch('brain.create_pandas_dataframe_agent')
    @patch('brain.ChatVertexAI')
    @patch('brain.build')
    @patch('google.auth.default')
    @patch('brain._get_sales_agent')
    def test_deduplication(self, mock_get_agent, mock_auth, mock_build, mock_vertex, mock_create_agent):
        """Test that duplicate message IDs are handled correctly."""

        # Setup mocks
        mock_auth.return_value = (None, None)

        # Configure the Firestore Mock we injected in setUp
        mock_db = MagicMock()
        brain.firestore.Client.return_value = mock_db

        # Mock Collections via side_effect
        mock_processed_coll = MagicMock()
        mock_history_coll = MagicMock()

        def collection_side_effect(name):
            if name == 'processed_messages':
                return mock_processed_coll
            return mock_history_coll # Default for chats_whatsapp

        mock_db.collection.side_effect = collection_side_effect

        # Mock Documents
        mock_processed_doc = MagicMock()
        mock_processed_coll.document.return_value = mock_processed_doc

        mock_history_doc = MagicMock()
        mock_history_coll.document.return_value = mock_history_doc

        # --- Test Case 1: New Message (Not a Duplicate) ---
        mock_processed_doc.get.return_value.exists = False # Document doesn't exist

        # Mock inventory loading to skip it
        brain._df_inventory = MagicMock()

        # Mock agent response
        mock_agent_instance = MagicMock()
        mock_get_agent.return_value = mock_agent_instance
        mock_agent_instance.invoke.return_value = {'output': 'Response Text'}

        # Fallback configuration
        mock_create = sys.modules["langchain_experimental.agents"].create_pandas_dataframe_agent
        mock_create.return_value = mock_agent_instance

        # Mock safety auditor
        brain._safety_model = MagicMock()
        # Mock sequence:
        # 1. _analyze_tone_and_intent -> "SALES_QUERY"
        # 2. _audit_response -> "APROBADO" (contains SAFE implicit check)
        # 3. _should_ask_feedback -> "NO"
        brain._safety_model.invoke.side_effect = [
            MagicMock(content="CATEGORY: SALES_QUERY | TONE: DIRECTO"),
            MagicMock(content="APROBADO"),
            MagicMock(content="NO")
        ]

        # Patch _load_inventory inside process_message to avoid re-init logic failing
        with patch('brain._load_inventory', return_value=True), \
             patch('brain._update_user_profile'): # Avoid this call

            response = brain.process_message("Hello", "123456", "msg_new_123")

        # Verification
        self.assertEqual(response, "Response Text")
        mock_processed_doc.set.assert_called_once() # Should have saved the ID

        # --- Test Case 2: Duplicate Message ---
        mock_processed_doc.reset_mock()
        mock_processed_doc.set.reset_mock()
        mock_processed_doc.get.return_value.exists = True # Document exists

        # We must re-inject the side effects for the second call if needed,
        # but the document mock is persistent, we just changed its return value.

        response = brain.process_message("Hello Again", "123456", "msg_existing_123")

        # Verification
        self.assertIsNone(response)
        mock_processed_doc.set.assert_not_called() # Should NOT save again

if __name__ == '__main__':
    unittest.main()
