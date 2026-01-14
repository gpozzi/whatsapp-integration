import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# --- MOCK DEPENDENCIES BEFORE IMPORTING BRAIN ---
# Ideally, we shouldn't mock the root 'google' if it causes issues with submodules.
# But existing tests rely on it.
# To allow 'from google.api_core.exceptions import AlreadyExists', we need to mock it properly.

mock_exceptions = MagicMock()
mock_exceptions.AlreadyExists = Exception # Needs to be a class inheriting from BaseException

sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.api_core'] = MagicMock()
sys.modules['google.api_core.exceptions'] = mock_exceptions
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['google.cloud.texttospeech'] = MagicMock()

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import brain

class TestBrainMemory(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        brain._db_client = self.mock_db

    def test_manage_history_limit_and_hygiene(self):
        # Setup mock doc
        mock_doc_ref = MagicMock()
        self.mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Create a history with:
        # 1. Technical errors (to be filtered)
        # 2. Old messages (to be cut off by limit)
        # 3. Valid recent messages

        msg_1k = "A" * 1000

        messages = [
            f"Usuario: Oldest {msg_1k}", # Should be cut (idx 0)
            "Bot: Error processing request", # Should be filtered (idx 1)
            f"Usuario: Middle1 {msg_1k}", # (idx 2)
            "Bot: Agent stopped due to iteration limit", # Should be filtered (idx 3)
            f"Bot: Middle2 {msg_1k}", # (idx 4)
            f"Usuario: Recent1 {msg_1k}", # (idx 5)
            f"Bot: Recent2 {msg_1k}", # Most recent (idx 6)
        ]

        # Mock get()
        mock_doc_snapshot = MagicMock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = {"mensajes": messages}
        mock_doc_ref.get.return_value = mock_doc_snapshot

        # Call _manage_history (read only mode)
        history_str = brain._manage_history("123456789")

        # Assertions
        self.assertNotIn("Error processing", history_str, "Should filter technical errors")
        self.assertNotIn("Agent stopped", history_str, "Should filter technical errors")

        # Check limit (approx 4000)
        self.assertLessEqual(len(history_str), 4200, "Should respect character limit")

        # Check content
        self.assertIn("Recent2", history_str, "Should contain recent messages")
        self.assertIn("Recent1", history_str, "Should contain recent messages")
        self.assertIn("Middle2", history_str, "Should contain middle messages")
        self.assertNotIn("Oldest", history_str, "Should truncate old messages")

    def test_manage_history_async_update(self):
        # Setup mock doc
        mock_doc_ref = MagicMock()
        self.mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock exists to return False
        mock_doc_ref.get.return_value.exists = False

        # Mock the executor
        # Since _executor is instantiated at module level, we can patch it on the brain module
        with patch.object(brain._executor, 'submit') as mock_submit:
            # Call with bot_text to trigger update
            brain._manage_history("123456789", user_text="Hello", bot_text="Hi there")

            # Verify submit was called
            mock_submit.assert_called_once()
            args = mock_submit.call_args[0]
            # args[0] should be the function _update_user_profile
            self.assertEqual(args[0], brain._update_user_profile)
            # args[1] should be the phone
            self.assertEqual(args[1], "123456789")

if __name__ == '__main__':
    unittest.main()
