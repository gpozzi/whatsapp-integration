import unittest
from unittest.mock import MagicMock, patch
import sys
import datetime

# --- MOCKING MODULES ---
# Important: We must mock the entire module namespace BEFORE importing brain.
# This prevents it from trying to load real google modules that are half-installed or conflicting.
mock_google = MagicMock()
sys.modules["google"] = mock_google
sys.modules["google.auth"] = mock_google.auth
sys.modules["google.oauth2"] = mock_google.oauth2
sys.modules["google.cloud"] = mock_google.cloud
sys.modules["google.cloud.firestore"] = mock_google.cloud.firestore
sys.modules["googleapiclient"] = MagicMock()
sys.modules["googleapiclient.discovery"] = MagicMock()
sys.modules["langchain_google_vertexai"] = MagicMock()
sys.modules["langchain_experimental"] = MagicMock()
sys.modules["langchain_experimental.agents"] = MagicMock()
sys.modules["pandas"] = MagicMock()

# --- IMPORT APP ---
import brain
import config

class TestBrainRepro(unittest.TestCase):

    def setUp(self):
        # Reset globals
        brain._db_client = MagicMock()
        brain._df_inventory = MagicMock()
        brain._sales_agent = MagicMock()
        brain._safety_model = MagicMock()

    def test_process_message_flow(self):
        """Test basic flow: User sends message -> Agent responds."""

        # Mock Firestore Document for History
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "mensajes": ["Usuario: Hola", "Bot: Hola"],
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        }
        mock_doc_ref.get.return_value = mock_doc
        brain._db_client.collection.return_value.document.return_value = mock_doc_ref

        # Mock Safety/Intent Model
        mock_safety_resp = MagicMock()
        mock_safety_resp.content = "SALES_QUERY"
        brain._safety_model.invoke.return_value = mock_safety_resp

        # Mock Sales Agent
        mock_agent_resp = {"output": "Final Answer: Tenemos un Toyota Corolla disponible."}
        brain._sales_agent.invoke.return_value = mock_agent_resp

        # Run process_message
        with patch("brain._init_services") as mock_init, \
             patch("brain._load_inventory") as mock_load, \
             patch("brain._check_is_duplicate", return_value=False):

            mock_init.return_value = MagicMock() # Returns primary model
            mock_load.return_value = True

            response = brain.process_message("Busco un auto", "123456", "msg_id_1")

            self.assertIn("Toyota Corolla", response)
            print(f"\nResponse: {response}")

if __name__ == "__main__":
    unittest.main()
