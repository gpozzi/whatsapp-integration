
import unittest
from unittest.mock import MagicMock, patch, ANY
import sys

# Mock everything google related
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.texttospeech'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_core'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()

import brain

class TestAsyncLogic(unittest.TestCase):
    def setUp(self):
        # Reset globals
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()
        brain._embeddings_service = MagicMock()

        self.original_executor = brain._executor
        self.mock_executor = MagicMock()
        # Make submit return a future-like object

        brain._executor = self.mock_executor

    def tearDown(self):
        brain._executor = self.original_executor

    def test_process_message_parallelism_full(self):
        # Setup mocks for dependent functions
        brain._check_is_duplicate = MagicMock(return_value=False)
        brain._manage_history = MagicMock(return_value="history")
        brain._analyze_tone_and_intent = MagicMock(return_value={"intent": "SALES_QUERY", "style_instruction": "style"})
        brain._search_cars = MagicMock(return_value="inventory")
        brain._audit_response = MagicMock(return_value=True)
        brain._should_ask_feedback = MagicMock(return_value=False)

        # Make sure futures return correct types
        future_intent = MagicMock()
        future_intent.result.return_value = {"intent": "SALES_QUERY", "style_instruction": "style"}

        future_search = MagicMock()
        future_search.result.return_value = "inventory"

        future_audit = MagicMock()
        future_audit.result.return_value = True

        future_feedback = MagicMock()
        future_feedback.result.return_value = False

        # Configure executor to return specific futures based on args
        def submit_side_effect(func, *args, **kwargs):
            if func == brain._analyze_tone_and_intent:
                return future_intent
            if func == brain._search_cars:
                return future_search
            if func == brain._audit_response:
                return future_audit
            if func == brain._should_ask_feedback:
                return future_feedback

            # Fallback
            f = MagicMock()
            f.result.return_value = None
            return f

        self.mock_executor.submit.side_effect = submit_side_effect

        # Run process_message
        brain.process_message("Show me cars", "123")

        # Verify parallel calls were submitted
        calls = self.mock_executor.submit.call_args_list

        # Check Step 2 (Analysis)
        intent_submitted = any(call[0][0] == brain._analyze_tone_and_intent for call in calls)
        self.assertTrue(intent_submitted, "Intent analysis should be submitted")

        search_submitted = any(call[0][0] == brain._search_cars for call in calls)
        self.assertTrue(search_submitted, "Search cars should be submitted")

        # Check Step 3 (Post-Processing)
        audit_submitted = any(call[0][0] == brain._audit_response for call in calls)
        self.assertTrue(audit_submitted, "Audit should be submitted")

        feedback_submitted = any(call[0][0] == brain._should_ask_feedback for call in calls)
        self.assertTrue(feedback_submitted, "Feedback check should be submitted")

if __name__ == '__main__':
    unittest.main()
