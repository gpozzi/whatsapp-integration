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
sys.modules["langchain_experimental.agents"] = MagicMock()

# --- IMPORT APP ---
import brain
import config

class TestBrainFeatures(unittest.TestCase):

    def setUp(self):
        # Reset globals
        brain._db_client = MagicMock()
        brain._df_inventory = MagicMock()
        brain._inventory_timestamp = datetime.datetime.now(datetime.timezone.utc)
        # brain._sales_agent = MagicMock() # Removed
        brain._safety_model = MagicMock()

        # Re-bind
        brain.create_pandas_dataframe_agent = sys.modules["langchain_experimental.agents"].create_pandas_dataframe_agent

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

        # 3. Setup Inventory (Make it not None so it doesn't fail)
        brain._df_inventory = MagicMock()
        brain._df_inventory.empty = False

        # Run process_message
        with patch("brain._init_services") as mock_init, \
             patch("brain._load_inventory") as mock_load, \
             patch("brain._check_is_duplicate", return_value=False), \
             patch("brain._manage_history", return_value=""), \
             patch("brain._audit_response", return_value=True), \
             patch("brain._should_ask_feedback", return_value=False), \
             patch("brain._get_sales_agent") as mock_get_agent:

            mock_init.return_value = MagicMock()
            mock_load.return_value = True

            # 2. Setup Sales Agent Response (No stock)
            # Create a mock agent instance
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            mock_agent.invoke.side_effect = [
                {"output": "Lo siento, no tengo ese auto."},  # Primera llamada (Query normal)
                {"output": "Tengo un Honda Civic similar."}   # Segunda llamada (Cross-selling)
            ]

            # Fallback
            mock_create = sys.modules["langchain_experimental.agents"].create_pandas_dataframe_agent
            mock_create.return_value = mock_agent

            response = brain.process_message("Busco un auto raro", "123", "msg1")

            self.assertIsNotNone(response)
            self.assertIn("Honda Civic", response)
            self.assertIn("Sugerencia", response)

if __name__ == "__main__":
    unittest.main()
