import unittest
from unittest.mock import MagicMock, patch
import brain
from concurrent.futures import Future

class TestBrainParallel(unittest.TestCase):
    def setUp(self):
        # Mock services to avoid real calls
        self.mock_db = MagicMock()
        self.mock_llm = MagicMock()
        brain._db_client = self.mock_db
        brain._safety_model = self.mock_llm
        brain._embeddings_service = MagicMock()

        # Patch init services to avoid re-init
        self.patcher_init = patch('brain._init_services', return_value=self.mock_llm)
        self.patcher_init.start()

        # Patch other db dependent functions
        self.patcher_dup = patch('brain._check_is_duplicate', return_value=False)
        self.patcher_hist = patch('brain._manage_history', return_value="History")
        self.patcher_dup.start()
        self.patcher_hist.start()

    def tearDown(self):
        self.patcher_init.stop()
        self.patcher_dup.stop()
        self.patcher_hist.stop()

        # Clean global state
        brain._db_client = None
        brain._safety_model = None
        brain._embeddings_service = None

    def test_optimistic_search_execution(self):
        """Verify that search is submitted to executor and result is used."""

        # Mock executor in brain
        mock_executor = MagicMock()
        original_executor = brain._executor
        brain._executor = mock_executor

        try:
            # Setup Future mock
            mock_future = MagicMock(spec=Future)
            mock_future.result.return_value = "Optimistic Search Results"
            mock_executor.submit.return_value = mock_future

            # Mock Intent Analysis to be "SALES_QUERY"
            # Note: _analyze_tone_and_intent calls _safety_model.invoke
            # process_message also calls sales_llm.invoke later
            # We need to sequence the mock responses or use different mocks if possible.
            # In setUp we set _safety_model = self.mock_llm and _init_services returns self.mock_llm
            # So they are the same object.

            # 1. _analyze_tone_and_intent -> returns "SALES_QUERY"
            # 2. sales_llm.invoke (RAG) -> returns "Response"
            # 3. _audit_response -> returns "SAFE" (implicit if not "PELIGRO")
            # 4. _should_ask_feedback -> returns "NO"

            self.mock_llm.invoke.side_effect = [
                MagicMock(content="CATEGORY: SALES_QUERY | TONE: CASUAL"), # Tone/Intent
                MagicMock(content="Here is the car"),                      # Sales Response
                MagicMock(content="SAFE"),                                 # Audit
                MagicMock(content="NO")                                    # Feedback Decision
            ]

            # Run
            brain.process_message("Show me cars", "123")

            # Verify submit was called
            self.assertTrue(mock_executor.submit.called)
            args, _ = mock_executor.submit.call_args
            self.assertEqual(args[0], brain._search_cars)
            self.assertIn("Show me cars", args[1])

            # Verify result was called (because it was SALES_QUERY)
            mock_future.result.assert_called()

        finally:
            brain._executor = original_executor

    def test_optimistic_search_ignored_on_feedback(self):
        """Verify that search result is NOT awaited if intent is feedback."""

        mock_executor = MagicMock()
        original_executor = brain._executor
        brain._executor = mock_executor

        try:
            mock_future = MagicMock(spec=Future)
            mock_executor.submit.return_value = mock_future

            # Mock Intent as FEEDBACK_POS
            # 1. _analyze_tone_and_intent -> FEEDBACK_POS
            self.mock_llm.invoke.side_effect = [
                MagicMock(content="CATEGORY: FEEDBACK_POS"),
            ]

            brain.process_message("Good job", "123")

            # Verify submit was still called (optimistic)
            self.assertTrue(mock_executor.submit.called)

            # Verify result was NOT called (we didn't need it)
            mock_future.result.assert_not_called()

        finally:
            brain._executor = original_executor

if __name__ == '__main__':
    unittest.main()
