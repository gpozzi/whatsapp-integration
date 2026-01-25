
import unittest
from unittest.mock import MagicMock, patch
import sys

# Pre-mock google dependencies to avoid import errors
sys.modules["google"] = MagicMock()
sys.modules["google.auth"] = MagicMock()
sys.modules["google.cloud"] = MagicMock()
sys.modules["google.cloud.firestore"] = MagicMock()
sys.modules["google.cloud.texttospeech"] = MagicMock()
sys.modules["google.cloud.pubsub_v1"] = MagicMock()
sys.modules["langchain_google_vertexai"] = MagicMock()
sys.modules["langchain_core"] = MagicMock()
sys.modules["langchain_core.messages"] = MagicMock()

import brain

class TestBrainExecutor(unittest.TestCase):
    def setUp(self):
        # Mock DB client to avoid errors
        brain._db_client = MagicMock()
        # Mock document to return exists=True so it proceeds to history logic
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'mensajes': [], 'timestamp': None}
        brain._db_client.collection.return_value.document.return_value.get.return_value = mock_doc

    def test_executor_submit_called(self):
        # Patch the executor on the brain module
        with patch('brain._executor') as mock_executor:
            # Trigger the logic that uses the executor
            brain._manage_history("test_phone", user_text="Hello", bot_text="Hi there")

            # Verify submit was called
            self.assertTrue(mock_executor.submit.called, "Executor.submit should be called for background profile update")

            # Verify arguments (optional but good)
            args, _ = mock_executor.submit.call_args
            # first arg should be the function _update_user_profile
            self.assertEqual(args[0], brain._update_user_profile)
            # second arg is phone
            self.assertEqual(args[1], "test_phone")

if __name__ == "__main__":
    unittest.main()
