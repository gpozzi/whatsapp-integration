import sys
from unittest.mock import MagicMock

# Mock heavy dependencies before importing brain
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.texttospeech'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_core'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()

import unittest
from unittest.mock import patch
# Now import brain
import brain

class TestBrainParallel(unittest.TestCase):
    def setUp(self):
        # Reset services mocks to prevent errors during execution
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()
        brain._embeddings_service = MagicMock()

    @patch('brain._executor')
    @patch('brain._analyze_tone_and_intent')
    @patch('brain._search_cars')
    @patch('brain._init_services')
    @patch('brain._manage_history')
    @patch('brain._audit_response')
    @patch('brain._should_ask_feedback')
    def test_optimistic_search_execution(self, mock_should_ask, mock_audit, mock_manage, mock_init, mock_search, mock_intent, mock_executor):
        """Test that intent analysis and vector search are submitted to executor in parallel."""
        # Setup
        mock_init.return_value = MagicMock() # Sales LLM
        mock_manage.return_value = "History"
        mock_audit.return_value = True
        mock_should_ask.return_value = False

        # Mocks for futures
        future_intent = MagicMock()
        future_intent.result.return_value = {"intent": "SALES_QUERY", "style_instruction": "Neutral"}

        future_search = MagicMock()
        future_search.result.return_value = "Inventory Context"

        # Configure executor submit to return these futures
        def side_effect_submit(func, *args, **kwargs):
            if func == brain._analyze_tone_and_intent: # Using the patched object reference
                return future_intent
            if func == brain._search_cars:
                return future_search
            # For other background tasks like profile update
            return MagicMock()

        mock_executor.submit.side_effect = side_effect_submit

        # Execute
        brain.process_message("Quiero un auto", "123456789")

        # Verify both were submitted
        # We verify that submit was called with the mock objects representing the functions

        submitted_funcs = [call.args[0] for call in mock_executor.submit.call_args_list]

        self.assertIn(mock_intent, submitted_funcs, "Intent analysis should be submitted to executor")
        self.assertIn(mock_search, submitted_funcs, "Vector search should be submitted to executor")

        # Verify results were retrieved
        future_intent.result.assert_called()
        future_search.result.assert_called()

if __name__ == '__main__':
    unittest.main()
