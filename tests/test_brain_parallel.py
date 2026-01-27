import unittest
from unittest.mock import MagicMock, patch
import brain

class TestBrainParallel(unittest.TestCase):
    def setUp(self):
        # Reset globals
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()
        brain._embeddings_service = MagicMock()

    def test_optimistic_search_parallelism(self):
        """Verify that analysis and search are submitted to executor."""

        # Mock the global executor
        with patch('brain._executor') as mock_executor:
            # Setup futures
            future_analysis = MagicMock()
            future_analysis.result.return_value = {
                "intent": "SALES_QUERY",
                "style_instruction": "Neutral"
            }

            future_search = MagicMock()
            future_search.result.return_value = "Inventory Context"

            # Configure submit to return our futures
            # In code:
            # future_analysis = _executor.submit(...)
            # future_search = _executor.submit(...)
            mock_executor.submit.side_effect = [future_analysis, future_search]

            # Mock other dependencies to avoid errors
            # We mock _manage_history to avoid side effects and additional executor calls
            with patch('brain._manage_history', return_value="history"), \
                 patch('brain._audit_response', return_value=True), \
                 patch('brain._should_ask_feedback', return_value=False), \
                 patch('brain._init_services', return_value=MagicMock()) as mock_init:

                mock_llm = mock_init.return_value
                mock_llm.invoke.return_value.content = "Response"

                # Execute
                brain.process_message("I want a car", "123")

                # Verify executor usage
                self.assertEqual(mock_executor.submit.call_count, 2)

                # Verify arguments of submit
                # args[0] is function, args[1:] are args
                call1 = mock_executor.submit.call_args_list[0]
                call2 = mock_executor.submit.call_args_list[1]

                # We expect _analyze_tone_and_intent first
                self.assertEqual(call1[0][0], brain._analyze_tone_and_intent)

                # Then _search_cars
                self.assertEqual(call2[0][0], brain._search_cars)
                self.assertEqual(call2[0][1], "I want a car")

                # Verify results were awaited
                future_analysis.result.assert_called()
                future_search.result.assert_called()

if __name__ == '__main__':
    unittest.main()
