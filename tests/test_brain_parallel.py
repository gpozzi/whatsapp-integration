import unittest
from unittest.mock import MagicMock, patch
import sys
import time
import brain

# Mock imports done in brain.py already via previous test setup? No, this is a new process.
# But brain is already imported.
# We need to ensure we can patch internal functions.

from concurrent.futures import ThreadPoolExecutor

class TestBrainParallel(unittest.TestCase):
    def setUp(self):
        self.original_executor = brain._executor
        brain._executor = ThreadPoolExecutor(max_workers=4)

    def tearDown(self):
        brain._executor.shutdown(wait=True)
        brain._executor = self.original_executor

    @patch('brain._db_client')
    @patch('brain._safety_model')
    @patch('brain._init_services')
    def test_optimistic_search_performance(self, mock_init, mock_safety, mock_db):
        """Test that Intent Analysis and Vector Search run in parallel"""

        # Setup mocks
        mock_init.return_value = MagicMock() # sales_llm
        mock_init.return_value.invoke.return_value.content = "Response"

        # Delays
        INTENT_DELAY = 0.5
        SEARCH_DELAY = 0.5

        def delayed_intent(*args, **kwargs):
            time.sleep(INTENT_DELAY)
            return {"intent": "SALES_QUERY", "style_instruction": "Normal"}

        def delayed_search(*args, **kwargs):
            time.sleep(SEARCH_DELAY)
            return "Search Results"

        with patch('brain._analyze_tone_and_intent', side_effect=delayed_intent) as mock_intent, \
             patch('brain._search_cars', side_effect=delayed_search) as mock_search, \
             patch('brain._audit_response', return_value=True), \
             patch('brain._should_ask_feedback', return_value=False), \
             patch('brain._manage_history', return_value="History"):

            start_time = time.time()
            brain.process_message("User says something", "123")
            end_time = time.time()

            duration = end_time - start_time

            # If sequential: 0.5 + 0.5 = 1.0s
            # If parallel: max(0.5, 0.5) = 0.5s + overhead

            # Allow some overhead, but it should be significantly less than 1.0s
            self.assertLess(duration, INTENT_DELAY + SEARCH_DELAY - 0.2, "Execution time indicates sequential processing")

            # Ensure both were called
            mock_intent.assert_called()
            mock_search.assert_called()

if __name__ == '__main__':
    unittest.main()
