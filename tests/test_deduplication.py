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

    @patch('brain.firestore.Client')
    @patch('brain.create_pandas_dataframe_agent')
    @patch('brain.ChatVertexAI')
    @patch('brain.build')
    @patch('google.auth.default')
    def test_deduplication(self, mock_auth, mock_build, mock_vertex, mock_agent, mock_firestore):
        """Test that duplicate message IDs are handled correctly."""

        # Setup mocks
        mock_auth.return_value = (None, None)
        mock_db = MagicMock()
        mock_firestore.return_value = mock_db

        # Force initialization
        brain._db_client = None # Reset
        brain._init_services()

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
        brain._sales_agent = mock_agent_instance
        mock_agent_instance.invoke.return_value = {'output': 'Response Text'}

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
        mock_processed_doc.get.return_value.exists = True # Document exists

        response = brain.process_message("Hello Again", "123456", "msg_existing_123")

        # Verification
        self.assertIsNone(response)
        mock_processed_doc.set.assert_not_called() # Should NOT save again

if __name__ == '__main__':
    unittest.main()
