import unittest
from unittest.mock import MagicMock, patch, ANY
import sys
import brain
import config
from google.cloud import firestore
import concurrent.futures

class TestFeedbackLoop(unittest.TestCase):
    def setUp(self):
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()

        # Override dependency checks
        brain._check_is_duplicate = MagicMock(return_value=False)
        brain._manage_history = MagicMock(return_value="User: Hello\nBot: Hi")
        brain._audit_response = MagicMock(return_value=True)

        # Patch Executor to be Synchronous for predictable testing
        class SynchronousExecutor:
            def submit(self, fn, *args, **kwargs):
                future = concurrent.futures.Future()
                try:
                    result = fn(*args, **kwargs)
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
                return future

        self.patcher_executor = patch("brain._executor", new=SynchronousExecutor())
        self.patcher_executor.start()

    def tearDown(self):
        self.patcher_executor.stop()

    def test_classify_intent_positive_feedback(self):
        """Test that _analyze_tone_and_intent correctly identifies positive feedback."""
        brain._safety_model.invoke.return_value.content = "CATEGORY: FEEDBACK_POS | TONE: CASUAL"

        result = brain._analyze_tone_and_intent("Sí", "History")
        self.assertEqual(result["intent"], "FEEDBACK_POS")

        expected_prompt = config.INTENT_AND_TONE_PROMPT.format(history="History", user_input="Sí")
        brain._safety_model.invoke.assert_called_with(expected_prompt)

    def test_classify_intent_negative_feedback(self):
        """Test that _analyze_tone_and_intent correctly identifies negative feedback."""
        brain._safety_model.invoke.return_value.content = "CATEGORY: FEEDBACK_NEG | TONE: ENFADADO"

        result = brain._analyze_tone_and_intent("No", "History")
        self.assertEqual(result["intent"], "FEEDBACK_NEG")

    def test_classify_intent_sales_query(self):
        """Test fallback to SALES_QUERY."""
        brain._safety_model.invoke.return_value.content = "CATEGORY: SALES_QUERY | TONE: DIRECTO"
        result = brain._analyze_tone_and_intent("Quiero un auto", "History")
        self.assertEqual(result["intent"], "SALES_QUERY")

    def test_should_ask_feedback_yes(self):
        """Test _should_ask_feedback returns True when model says YES."""
        brain._safety_model.invoke.return_value.content = "SI"
        result = brain._should_ask_feedback("Here is a list of cars...")
        self.assertTrue(result)

    def test_should_ask_feedback_no(self):
        """Test _should_ask_feedback returns False when model says NO."""
        brain._safety_model.invoke.return_value.content = "NO"
        result = brain._should_ask_feedback("Hello!")
        self.assertFalse(result)

    def test_handle_negative_feedback(self):
        """Test _handle_negative_feedback parses JSON and saves to Firestore."""
        json_response = """
        ```json
        {
            "insight": "User wanted financing info.",
            "user_explanation": "Entiendo, quizás no fui claro con la financiación."
        }
        ```
        """
        brain._safety_model.invoke.return_value.content = json_response

        mock_collection = MagicMock()
        brain._db_client.collection.side_effect = lambda name: mock_collection if name == "bot_insights" else MagicMock()

        response = brain._handle_negative_feedback("12345", "History")

        self.assertIn("Entiendo, quizás no fui claro con la financiación.", response)

        brain._db_client.collection.assert_called_with("bot_insights")
        mock_collection.add.assert_called_once()
        args, _ = mock_collection.add.call_args
        payload = args[0]
        self.assertEqual(payload["insight"], "User wanted financing info.")
        self.assertEqual(payload["user_phone"], "12345")

    def test_process_message_flow_negative_feedback(self):
        """Integration test: process_message with negative feedback intent."""
        # 1. _analyze_tone_and_intent -> FEEDBACK_NEG
        # 2. _handle_negative_feedback -> JSON Response

        # Mock LLM instance
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.side_effect = [
            MagicMock(content="CATEGORY: FEEDBACK_NEG | TONE: CASUAL"), # Intent analysis
            MagicMock(content='{"insight": "fail", "user_explanation": "Sorry"}') # Failure analysis
        ]

        # Patch dependencies
        # Also patch _search_cars because optimistic search will trigger it, and we want to avoid side effects or crashes
        with patch("brain._init_services", return_value=mock_llm_instance), \
             patch("brain._manage_history", return_value="Historial"), \
             patch("brain._search_cars", return_value="Ignored"):

            # Inject mocks into brain
            brain._safety_model = mock_llm_instance
            brain._db_client = MagicMock()

            result = brain.process_message("No", "12345")

        self.assertIn("Sorry", result)
        # Verify Sales LLM logic was NOT triggered (implicit by flow)

    def test_process_message_flow_sales_query_with_feedback_request(self):
        """Integration test: process_message with query + feedback request."""

        # Sequence:
        # 1. _analyze_tone_and_intent -> SALES_QUERY
        # 2. _search_cars (RAG)
        # 3. Sales LLM Response
        # 4. _audit_response
        # 5. _should_ask_feedback -> SI

        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.side_effect = [
            MagicMock(content="CATEGORY: SALES_QUERY | TONE: DIRECTO"), # Intent
            MagicMock(content="Here is a car"), # Sales Agent
            MagicMock(content="SI"), # Feedback
            MagicMock(content="EXTRA_CALL") # Safety buffer
        ]

        with patch("brain._init_services", return_value=mock_llm_instance), \
             patch("brain._manage_history", return_value="Historial"), \
             patch("brain._search_cars", return_value="Inventory Context"):

            brain._safety_model = mock_llm_instance
            brain._db_client = MagicMock()

            result = brain.process_message("Price of Toyota?", "12345")

        self.assertIn("Here is a car", result)
        self.assertIn("(¿Te sirvió esta info? Responde SÍ o NO)", result)

if __name__ == '__main__':
    unittest.main()
