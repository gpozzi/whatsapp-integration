import unittest
from unittest.mock import MagicMock, patch
import brain

class TestBrainParallel(unittest.TestCase):
    @patch('brain.ChatVertexAI')
    def test_process_message_parallel_execution(self, mock_chat_cls):
        # Setup globals to skip initialization logic
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()
        brain._embeddings_service = MagicMock()

        # Mock the sales LLM instance
        mock_sales_llm = mock_chat_cls.return_value
        mock_sales_llm.invoke.return_value.content = "Respuesta del bot"

        # Patch executor on the module
        original_executor = brain._executor
        mock_executor = MagicMock()
        brain._executor = mock_executor

        try:
            # Setup futures
            mock_intent_future = MagicMock()
            mock_intent_future.result.return_value = {
                "intent": "SALES_QUERY",
                "style_instruction": "Normal"
            }

            mock_search_future = MagicMock()
            mock_search_future.result.return_value = "Inventory Context"

            # Future for background task (profile update)
            mock_background_future = MagicMock()

            # Side effect: submit returns futures.
            # Sequence:
            # 1. Intent Analysis
            # 2. Search
            # 3. Background Profile Update (in _manage_history)
            # Use iterator to handle side_effect safely
            mock_executor.submit.side_effect = [mock_intent_future, mock_search_future, mock_background_future, MagicMock(), MagicMock()]

            # Call
            brain.process_message("Quiero un auto", "123")

            # Verify submit calls
            # We expect at least 2 calls (intent + search).
            self.assertGreaterEqual(mock_executor.submit.call_count, 2)

            # Check calls
            calls = mock_executor.submit.call_args_list

            # 1st call: Intent
            self.assertEqual(calls[0][0][0], brain._analyze_tone_and_intent)

            # 2nd call: Search
            self.assertEqual(calls[1][0][0], brain._search_cars)

            # Verify we waited for results
            mock_intent_future.result.assert_called()
            mock_search_future.result.assert_called()

        finally:
            brain._executor = original_executor

if __name__ == '__main__':
    unittest.main()
