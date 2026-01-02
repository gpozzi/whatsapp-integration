import unittest
from unittest.mock import MagicMock, patch
import sys
import datetime
import json

# --- MOCKING MODULES ---
mock_google = MagicMock()
sys.modules["google"] = mock_google
sys.modules["google.auth"] = mock_google.auth
sys.modules["google.oauth2"] = mock_google.oauth2
sys.modules["google.cloud"] = mock_google.cloud
sys.modules["google.cloud.firestore"] = mock_google.cloud.firestore
sys.modules["google.cloud.texttospeech"] = MagicMock()
sys.modules["googleapiclient"] = MagicMock()
sys.modules["googleapiclient.discovery"] = MagicMock()
sys.modules["langchain_google_vertexai"] = MagicMock()
sys.modules["langchain_core"] = MagicMock()
sys.modules["langchain_core.messages"] = MagicMock()
sys.modules["langchain_experimental"] = MagicMock()
sys.modules["langchain_experimental.agents"] = MagicMock()
sys.modules["langchain_experimental.tools.python.tool"] = MagicMock()
sys.modules["pandas"] = MagicMock()

# --- IMPORT APP ---
import brain
import config

class TestBrainFeatures(unittest.TestCase):

    def setUp(self):
        # Reset globals
        brain._db_client = MagicMock()
        brain._df_inventory = MagicMock()
        brain._sales_agent = MagicMock()
        brain._safety_model = MagicMock()

    def test_tone_and_intent_analysis(self):
        """Test parsing of intent and tone from the safety model."""
        brain._safety_model.invoke.return_value.content = "CATEGORY: SALES_QUERY | TONE: DIRECTO"

        result = brain._analyze_tone_and_intent("Precio Corolla", "Historial...")

        self.assertEqual(result["intent"], "SALES_QUERY")
        self.assertIn("directo", result["style_instruction"])

    def test_image_analysis_car(self):
        """Test image analysis when it IS a car."""
        brain._safety_model.invoke.return_value.content = "SI. Es un Toyota rojo."

        # Mock base64 encoding or just pass dummy bytes
        result = brain._analyze_image(b"fake_image_bytes", "texto usuario")

        self.assertIn("Toyota rojo", result)

    def test_image_analysis_not_car(self):
        """Test image analysis when it IS NOT a car."""
        brain._safety_model.invoke.return_value.content = "NO_AUTO"

        result = brain._analyze_image(b"fake_bytes", "texto usuario")

        self.assertEqual(result, "NO_AUTO")

    def test_cross_selling_trigger(self):
        """Test that similar cars are searched if agent returns 'no tengo'."""

        # 1. Setup Intent/Tone
        brain._safety_model.invoke.return_value.content = "CATEGORY: SALES_QUERY | TONE: CASUAL"

        # 2. Setup Sales Agent Response (No stock)
        brain._sales_agent.invoke.side_effect = [
            {"output": "Lo siento, no tengo ese auto."},  # Primera llamada (Query normal)
            {"output": "Tengo un Honda Civic similar."}   # Segunda llamada (Cross-selling)
        ]

        # 3. Setup Inventory (Make it not None so it doesn't fail)
        brain._df_inventory = MagicMock()
        brain._df_inventory.empty = False

        # Run process_message
        with patch("brain._init_services") as mock_init, \
             patch("brain._load_inventory") as mock_load, \
             patch("brain._check_is_duplicate", return_value=False), \
             patch("brain._manage_history", return_value=""), \
             patch("brain._audit_response", return_value=True), \
             patch("brain._should_ask_feedback", return_value=False):

            mock_init.return_value = MagicMock()
            mock_load.return_value = True

            response = brain.process_message("Busco un auto raro", "123", "msg1")

            self.assertIsNotNone(response)
            self.assertIn("Honda Civic", response)
            self.assertIn("Sugerencia", response)

if __name__ == "__main__":
    unittest.main()
