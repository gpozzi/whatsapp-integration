import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock imports before importing brain
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.texttospeech'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()

import brain
from concurrent.futures import ThreadPoolExecutor

class TestBrainCrash(unittest.TestCase):
    def setUp(self):
        self.original_executor = brain._executor
        brain._executor = ThreadPoolExecutor(max_workers=4)

    def tearDown(self):
        brain._executor.shutdown(wait=True)
        brain._executor = self.original_executor

    @patch('brain._db_client')
    @patch('brain._safety_model')
    @patch('brain._init_services')
    def test_executor_fix(self, mock_init, mock_safety, mock_db):
        """Test that _executor is present and process_message works"""
        # Setup mocks
        mock_init.return_value = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value.exists = False

        # Ensure _executor exists
        self.assertTrue(hasattr(brain, '_executor'), "brain._executor should be defined")

        # Run process_message
        with patch('brain._analyze_tone_and_intent') as mock_intent, \
             patch('brain._search_cars') as mock_search, \
             patch('brain._audit_response') as mock_audit, \
             patch('brain._should_ask_feedback') as mock_feedback:

            mock_intent.return_value = {"intent": "SALES_QUERY", "style_instruction": "Normal"}
            mock_search.return_value = "Auto 1"
            mock_audit.return_value = True
            mock_feedback.return_value = False

            # The sales_llm.invoke is called on the result of _init_services
            mock_init.return_value.invoke.return_value.content = "Response"

            # Execute
            response = brain.process_message("Hola", "123456")

            # Should succeed
            self.assertEqual(response, "Response")

if __name__ == '__main__':
    unittest.main()
