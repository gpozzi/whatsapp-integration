import unittest
from unittest.mock import MagicMock, patch, ANY
import sys

# --- MOCK DEPENDENCIES BEFORE IMPORTING BRAIN ---
# We must mock the top-level packages and their submodules to avoid ImportErrors
# in an environment where they might not be installed.

mock_modules = [
    "google",
    "google.auth",
    "googleapiclient",
    "googleapiclient.discovery",
    "google.cloud",
    "google.cloud.firestore",
    "pandas",
    "langchain_google_vertexai",
    "langchain_experimental",
    "langchain_experimental.agents"
]

for mod_name in mock_modules:
    sys.modules[mod_name] = MagicMock()

import brain
import config
from google.cloud import firestore # Now this is a mock

class TestFeedbackLoop(unittest.TestCase):
    def setUp(self):
        # Reset global state in brain.py
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()
        brain._sales_agent = MagicMock()
        brain._df_inventory = MagicMock()

        # Setup common mocks
        brain._check_is_duplicate = MagicMock(return_value=False)
        brain._manage_history = MagicMock(return_value="User: Hello\nBot: Hi")
        brain._audit_response = MagicMock(return_value=True)

    def test_classify_intent_positive_feedback(self):
        """Test that _classify_intent correctly identifies positive feedback."""
        brain._safety_model.invoke.return_value.content = "FEEDBACK_POS"

        intent = brain._classify_intent("Sí", "History")
        self.assertEqual(intent, "FEEDBACK_POS")

        expected_prompt = config.INTENT_CLASSIFIER_PROMPT.format(history="History", user_input="Sí")
        brain._safety_model.invoke.assert_called_with(expected_prompt)

    def test_classify_intent_negative_feedback(self):
        """Test that _classify_intent correctly identifies negative feedback."""
        brain._safety_model.invoke.return_value.content = "FEEDBACK_NEG"

        intent = brain._classify_intent("No", "History")
        self.assertEqual(intent, "FEEDBACK_NEG")

    def test_classify_intent_sales_query(self):
        """Test fallback to SALES_QUERY."""
        brain._safety_model.invoke.return_value.content = "SALES_QUERY"
        intent = brain._classify_intent("Quiero un auto", "History")
        self.assertEqual(intent, "SALES_QUERY")

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
        # Mock LLM response with JSON
        json_response = """
        ```json
        {
            "insight": "User wanted financing info.",
            "user_explanation": "Entiendo, quizás no fui claro con la financiación."
        }
        ```
        """
        brain._safety_model.invoke.return_value.content = json_response

        # Mock Firestore
        # brain._db_client is a MagicMock.
        # We need to ensure .collection("bot_insights").add(...) is trackable.
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
        # Setup mocks for this specific flow
        # 1. _classify_intent -> FEEDBACK_NEG
        # 2. _handle_negative_feedback -> (mocked inside function or by mocking the model)

        # We'll rely on the real functions calling the mocked model
        # Sequence of model calls:
        # 1. _classify_intent
        # 2. _handle_negative_feedback (inside the if block)

        brain._safety_model.invoke.side_effect = [
            MagicMock(content="FEEDBACK_NEG"),
            MagicMock(content='{"insight": "fail", "user_explanation": "Sorry"}')
        ]

        result = brain.process_message("No", "12345")

        self.assertIn("Sorry", result)
        brain._sales_agent.invoke.assert_not_called()

    def test_process_message_flow_sales_query_with_feedback_request(self):
        """Integration test: process_message with query + feedback request."""
        brain._sales_agent.invoke.return_value = {"output": "Here is a car"}

        # Sequence:
        # 1. _classify_intent -> SALES_QUERY
        # 2. _should_ask_feedback -> SI
        # Note: _audit_response is mocked in setUp, so it doesn't call the model.

        brain._safety_model.invoke.side_effect = [
            MagicMock(content="SALES_QUERY"),
            MagicMock(content="SI")
        ]

        result = brain.process_message("Price of Toyota?", "12345")

        self.assertIn("Here is a car", result)
        self.assertIn("(¿Te sirvió esta info? Responde SÍ o NO)", result)

if __name__ == '__main__':
    unittest.main()
