import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor

# Mock dependencies before importing brain
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
sys.modules['langchain_core'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()

# Ensure we can import brain
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import brain

class TestPerformanceArchitecture(unittest.TestCase):
    def setUp(self):
        # Reset Global State
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()
        brain._embeddings_service = MagicMock()

        # Ensure we use a real executor for this test, or a controlled one.
        # Since we modified the code to use a global _executor, we can use it.
        # But for tests, we might want to ensure it's clean.
        # brain._executor = ThreadPoolExecutor(max_workers=4)
        pass

    @patch('brain._manage_history')
    @patch('brain._search_cars')
    @patch('brain._analyze_tone_and_intent')
    @patch('brain._init_services')
    @patch('brain._check_is_duplicate')
    @patch('brain._audit_response')
    @patch('brain._should_ask_feedback')
    def test_optimistic_search_parallelism(
        self,
        mock_should_ask, mock_audit, mock_duplicate, mock_init,
        mock_analyze_intent, mock_search_cars, mock_manage_history
    ):
        """
        Verify that _manage_history and _search_cars run in parallel.
        """
        # Setup Mocks
        mock_init.return_value = MagicMock() # Mock LLM
        mock_duplicate.return_value = False
        mock_audit.return_value = True
        mock_should_ask.return_value = False

        # Delays
        DELAY_HISTORY = 0.2
        DELAY_SEARCH = 0.2
        DELAY_INTENT = 0.1

        def history_side_effect(*args, **kwargs):
            time.sleep(DELAY_HISTORY)
            return "Mock History"

        def search_side_effect(*args, **kwargs):
            time.sleep(DELAY_SEARCH)
            return "Mock Inventory"

        def intent_side_effect(*args, **kwargs):
            time.sleep(DELAY_INTENT)
            return {"intent": "SALES_QUERY", "style_instruction": "Normal"}

        mock_manage_history.side_effect = history_side_effect
        mock_search_cars.side_effect = search_side_effect
        mock_analyze_intent.side_effect = intent_side_effect

        # Mock LLM invoke for the final response generation
        mock_init.return_value.invoke.return_value.content = "Final Response"

        # Measure Time
        start_time = time.time()

        response = brain.process_message("Quiero un auto", "123456")

        end_time = time.time()
        duration = end_time - start_time

        # Calculations
        # Sequential: History(Read) + Search + Intent + History(Write)
        sequential_time = DELAY_HISTORY + DELAY_SEARCH + DELAY_INTENT + DELAY_HISTORY

        # Parallel: max(HistoryRead, Search) + Intent + HistoryWrite
        # We expect to save roughly min(DELAY_HISTORY, DELAY_SEARCH)

        print(f"\n⚡ Performance Test Results:")
        print(f"   Sequential Logic would take: {sequential_time:.4f}s")
        print(f"   Actual Execution took:       {duration:.4f}s")

        # We expect significant saving (at least 0.15s given 0.2s overlap)
        self.assertLess(duration, sequential_time - 0.15, "Execution time should be significantly less than sequential sum")
        self.assertEqual(response, "Final Response")

        # Verify calls
        self.assertEqual(mock_manage_history.call_count, 2)
        mock_search_cars.assert_called()

if __name__ == '__main__':
    unittest.main()
