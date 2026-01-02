import unittest
from unittest.mock import MagicMock, patch, ANY
import sys

# --- MOCK DEPENDENCIES BEFORE IMPORTING BRAIN ---
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
    "langchain_experimental.agents",
    "langchain_experimental.tools.python.tool",
    "langchain_core",
    "langchain_core.messages"
]

for mod_name in mock_modules:
    sys.modules[mod_name] = MagicMock()

import brain
import config
from google.cloud import firestore

class TestFeedbackLoop(unittest.TestCase):
    def setUp(self):
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()
        brain._sales_agent = MagicMock()
        brain._df_inventory = MagicMock()

        brain._check_is_duplicate = MagicMock(return_value=False)
        brain._manage_history = MagicMock(return_value="User: Hello\nBot: Hi")
        brain._audit_response = MagicMock(return_value=True)

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

        brain._safety_model.invoke.side_effect = [
            MagicMock(content="CATEGORY: FEEDBACK_NEG | TONE: CASUAL"),
            MagicMock(content='{"insight": "fail", "user_explanation": "Sorry"}')
        ]

        # NOTE: We need to patch services inside process_message because it re-calls _init_services
        with patch("brain._init_services", return_value=MagicMock()), \
             patch("brain._load_inventory", return_value=True), \
             patch("brain._manage_history", return_value="Historial"):

            result = brain.process_message("No", "12345")

        self.assertIn("Sorry", result)
        brain._sales_agent.invoke.assert_not_called()

    def test_process_message_flow_sales_query_with_feedback_request(self):
        """Integration test: process_message with query + feedback request."""
        brain._sales_agent.invoke.return_value = {"output": "Here is a car"}

        # Sequence:
        # 1. _analyze_tone_and_intent -> SALES_QUERY
        # 2. _should_ask_feedback -> SI

        brain._safety_model.invoke.side_effect = [
            MagicMock(content="CATEGORY: SALES_QUERY | TONE: DIRECTO"),
            MagicMock(content="SI")
        ]

        with patch("brain._init_services", return_value=MagicMock()), \
             patch("brain._load_inventory", return_value=True), \
             patch("brain._manage_history", return_value="Historial"):

            result = brain.process_message("Price of Toyota?", "12345")

        self.assertIn("Here is a car", result)
        self.assertIn("(¿Te sirvió esta info? Responde SÍ o NO)", result)

if __name__ == '__main__':
    unittest.main()
