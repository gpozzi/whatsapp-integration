import unittest
from unittest.mock import MagicMock, patch
import brain
import concurrent.futures

class TestBrainParallel(unittest.TestCase):
    def setUp(self):
        # Mock dependencies to avoid external calls
        self.mock_db = patch('brain._db_client').start()
        self.mock_safety = patch('brain._safety_model').start()
        self.mock_embeddings = patch('brain._embeddings_service').start()

        # Mock helper functions to simplify test flow
        self.mock_init = patch('brain._init_services').start()
        self.mock_check_duplicate = patch('brain._check_is_duplicate').start()
        self.mock_manage_history = patch('brain._manage_history').start()
        self.mock_analyze_audio = patch('brain._analyze_audio').start()
        self.mock_analyze_image = patch('brain._analyze_image').start()
        self.mock_audit = patch('brain._audit_response').start()
        self.mock_ask_feedback = patch('brain._should_ask_feedback').start()
        self.mock_tts = patch('brain._text_to_speech').start()

        # Setup default return values
        self.mock_check_duplicate.return_value = False
        self.mock_manage_history.return_value = "Mock History"
        self.mock_audit.return_value = True
        self.mock_ask_feedback.return_value = False
        self.mock_init.return_value = MagicMock() # sales_llm
        self.mock_init.return_value.invoke.return_value.content = "Sales Response"

        # Mock the executor
        self.executor_patcher = patch('brain._executor', autospec=True)
        self.mock_executor = self.executor_patcher.start()

        # Configure the mock executor to return a mock future
        self.mock_future_intent = MagicMock()
        self.mock_future_intent.result.return_value = {"intent": "SALES_QUERY", "style_instruction": "Normal"}

        self.mock_future_search = MagicMock()
        self.mock_future_search.result.return_value = "Car Inventory"

        # Side effect to return different futures based on the function called
        def submit_side_effect(fn, *args, **kwargs):
            if fn == brain._analyze_tone_and_intent:
                return self.mock_future_intent
            elif fn == brain._search_cars:
                return self.mock_future_search
            elif fn == brain._update_user_profile:
                 # Background task
                 f = MagicMock()
                 return f
            return MagicMock()

        self.mock_executor.submit.side_effect = submit_side_effect

    def tearDown(self):
        patch.stopall()

    def test_process_message_parallel_execution(self):
        """Test that intent analysis and search are submitted to executor."""
        user_text = "I want a car"
        phone = "1234567890"

        brain.process_message(user_text, phone)

        # Verify submit was called for intent analysis
        submit_calls = self.mock_executor.submit.call_args_list

        intent_called = False
        search_called = False

        for call in submit_calls:
            args, _ = call
            fn = args[0]
            if fn == brain._analyze_tone_and_intent:
                intent_called = True
            if fn == brain._search_cars:
                search_called = True

        self.assertTrue(intent_called, "Intent analysis should be submitted")
        self.assertTrue(search_called, "Search cars should be submitted")

        # Verify results were used in the prompt
        sales_llm = self.mock_init.return_value
        call_args = sales_llm.invoke.call_args
        prompt = call_args[0][0] # First arg is prompt string
        self.assertIn("Car Inventory", prompt)

    def test_process_message_feedback_intent_ignores_search(self):
        """Test that if intent is FEEDBACK, search result is ignored (or search happens but unused)."""
        # Set intent to FEEDBACK_POS
        self.mock_future_intent.result.return_value = {"intent": "FEEDBACK_POS", "style_instruction": "Happy"}

        brain.process_message("Thanks", "123")

        # Verify search WAS submitted (optimistic)
        search_submitted = any(call[0][0] == brain._search_cars for call in self.mock_executor.submit.call_args_list)
        self.assertTrue(search_submitted, "Search should be submitted optimally even for feedback")

        # Verify sales_llm was NOT called (process_message returns early for feedback)
        sales_llm = self.mock_init.return_value
        sales_llm.invoke.assert_not_called()
