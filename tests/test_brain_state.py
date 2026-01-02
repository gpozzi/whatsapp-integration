import unittest
from unittest.mock import MagicMock, patch, ANY
import sys
import datetime
import pandas as pd

# Mock heavy dependencies
sys.modules['google'] = MagicMock() # Ensure google is mocked
sys.modules['google.auth'] = MagicMock() # Ensure google.auth is mocked
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.texttospeech'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
# sys.modules['langchain_core.messages'] = MagicMock() # Removed to fix Pydantic schema generation error

# Import after mocking
import brain
import config

class TestBrainState(unittest.TestCase):
    def setUp(self):
        # Reset global state before each test
        brain._df_inventory = None
        brain._inventory_timestamp = None
        brain._db_client = None

        # Re-bind imports to ensure we are using the current mocks
        brain.google = sys.modules['google']
        brain.build = sys.modules['googleapiclient.discovery'].build
        brain.create_pandas_dataframe_agent = sys.modules['langchain_experimental.agents'].create_pandas_dataframe_agent

        # Mock external calls
        self.mock_llm = MagicMock()

    @patch('brain.build')
    @patch('brain.google')
    def test_load_inventory_success(self, mock_google, mock_build):
        # Setup mock for sheets
        mock_google.auth.default.return_value = (MagicMock(), "project_id")

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock spreadsheet response
        mock_service.spreadsheets().get().execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}]
        }

        mock_service.spreadsheets().values().get().execute.return_value = {
            'values': [
                ['Marca', 'Modelo', 'Precio'],
                ['Toyota', 'Corolla', '20000']
            ]
        }

        result = brain._load_inventory()

        self.assertTrue(result)
        self.assertIsNotNone(brain._df_inventory)
        self.assertIsNotNone(brain._inventory_timestamp)
        self.assertEqual(len(brain._df_inventory), 1)

    @patch('brain.create_pandas_dataframe_agent')
    @patch('brain.google')
    @patch('brain.build')
    def test_get_sales_agent_fresh_inventory(self, mock_build, mock_google, mock_create_agent):
        # Pre-load inventory manually
        brain._df_inventory = pd.DataFrame({'col': [1]})
        brain._inventory_timestamp = datetime.datetime.now(datetime.timezone.utc)

        agent = brain._get_sales_agent(self.mock_llm)

        # Should create agent
        mock_create_agent.assert_called_once()
        # Should NOT call build/sheets (inventory is fresh)
        mock_build.assert_not_called()
        self.assertIsNotNone(agent)

    @patch('brain.create_pandas_dataframe_agent')
    @patch('brain.google')
    @patch('brain.build')
    def test_get_sales_agent_stale_inventory(self, mock_build, mock_google, mock_create_agent):
        # Pre-load STALE inventory
        brain._df_inventory = pd.DataFrame({'col': [1]})
        # Make it older than default 60 mins
        brain._inventory_timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=61)

        # Setup mock for sheets (reloading)
        mock_google.auth.default.return_value = (MagicMock(), "project_id")

        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.spreadsheets().get().execute.return_value = {'sheets': [{'properties': {'title': 'Sheet1'}}]}
        mock_service.spreadsheets().values().get().execute.return_value = {
            'values': [['Marca'], ['Toyota']]
        }

        agent = brain._get_sales_agent(self.mock_llm)

        # Should create agent
        mock_create_agent.assert_called_once()
        # Should call build/sheets because inventory was stale
        mock_build.assert_called_once()
        self.assertIsNotNone(agent)

    @patch('brain._get_sales_agent')
    def test_process_message_gets_agent(self, mock_get_agent):
        # Mock dependencies for process_message
        brain._db_client = MagicMock() # Prevent _init_services from failing or running

        # Ensure duplicate check returns False
        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value.exists = False
        brain._db_client.collection.return_value.document.return_value = mock_doc_ref

        mock_agent_instance = MagicMock()
        mock_get_agent.return_value = mock_agent_instance

        # Mock output
        mock_agent_instance.invoke.return_value = {'output': 'Final Answer: Hola'}

        brain.process_message("Hola", "12345")

        # Check that _get_sales_agent was called
        mock_get_agent.assert_called_once()
        # Check that agent was invoked
        mock_agent_instance.invoke.assert_called()

if __name__ == '__main__':
    unittest.main()
