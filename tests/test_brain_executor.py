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
sys.modules['google.cloud.texttospeech'] = MagicMock()

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import brain

class TestBrainExecutor(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        brain._db_client = self.mock_db

        # Patch the executor directly on the module
        self.executor_patcher = patch('brain._executor')
        self.mock_executor = self.executor_patcher.start()

    def tearDown(self):
        self.executor_patcher.stop()

    def test_manage_history_submits_to_executor(self):
        # Setup mock doc to return empty history so we don't hit other logic
        mock_doc_ref = MagicMock()
        mock_doc_snapshot = MagicMock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = {"mensajes": [], "timestamp": None}
        mock_doc_ref.get.return_value = mock_doc_snapshot
        self.mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Call _manage_history with bot_text to trigger the update
        brain._manage_history("12345", user_text="Hello", bot_text="Hi")

        # Verify submit was called
        self.mock_executor.submit.assert_called_once()

        # Verify arguments (function and args)
        # submit(fn, *args, **kwargs)
        call_args = self.mock_executor.submit.call_args
        self.assertEqual(call_args[0][0], brain._update_user_profile)
        self.assertEqual(call_args[0][1], "12345")
        # The history string passed should contain the new messages
        self.assertIn("Usuario: Hello", call_args[0][2])
        self.assertIn("Bot: Hi", call_args[0][2])

if __name__ == '__main__':
    unittest.main()
