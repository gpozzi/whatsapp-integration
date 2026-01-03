import unittest
from unittest.mock import MagicMock, patch
import json
import sys

# Mock modules to avoid needing actual GCP credentials or dependencies during test import
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()

# Now import ingestor, which uses the mocks
import ingestor
import config

class TestIngestor(unittest.TestCase):

    def setUp(self):
        # Configure the Sync API Key for testing
        self.original_api_key = config.SYNC_API_KEY
        config.SYNC_API_KEY = "test-secret-key"

    def tearDown(self):
        config.SYNC_API_KEY = self.original_api_key

    @patch('ingestor.VertexAIEmbeddings')
    @patch('ingestor.firestore.Client')
    def test_sync_inventory_success(self, mock_firestore_cls, mock_vertex_embeddings_cls):
        # Setup Mocks
        mock_request = MagicMock()
        mock_request.method = "POST"
        mock_request.headers = {"X-API-KEY": "test-secret-key"}
        mock_request.path = "/sync-inventory"

        car_data = {
            "id": "car-123",
            "make": "Toyota",
            "model": "Corolla",
            "year": 2020,
            "price": 20000
        }
        mock_request.get_json.return_value = car_data

        # Mock Vertex AI
        mock_embeddings_instance = mock_vertex_embeddings_cls.return_value
        mock_embeddings_instance.embed_query.return_value = [0.1, 0.2, 0.3] # Fake vector

        # Mock Firestore
        mock_db = mock_firestore_cls.return_value
        mock_collection = mock_db.collection.return_value
        mock_doc_ref = mock_collection.document.return_value

        # Execute
        response = ingestor.sync_inventory(mock_request)

        # Assertions
        self.assertEqual(response, ("Inventory Synced", 200))

        # Check Embedding Generation
        expected_text = "Toyota Corolla 2020 20000" # Based on order of keys in dict iteration (standard in Py3.7+)
        # Note: Since dict order is preserved, this should be consistent.
        # But to be safe, we just check that embed_query was called with a string containing the values
        call_args = mock_embeddings_instance.embed_query.call_args
        self.assertIsNotNone(call_args)
        text_passed = call_args[0][0]
        self.assertIn("Toyota", text_passed)
        self.assertIn("Corolla", text_passed)
        self.assertIn("20000", text_passed)

        # Check Firestore Write
        mock_db.collection.assert_called_with("inventory_vectors")
        mock_collection.document.assert_called_with("car-123")

        # Check set data
        set_args = mock_doc_ref.set.call_args
        self.assertIsNotNone(set_args)
        saved_data = set_args[0][0]
        self.assertEqual(saved_data['id'], 'car-123')
        self.assertIn('embedding_field', saved_data)
        self.assertIn('text_representation', saved_data)

    def test_sync_inventory_unauthorized(self):
        mock_request = MagicMock()
        mock_request.method = "POST"
        mock_request.headers = {"X-API-KEY": "wrong-key"}

        response = ingestor.sync_inventory(mock_request)
        self.assertEqual(response, ("Unauthorized", 401))

    def test_sync_inventory_bad_method(self):
        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_request.headers = {"X-API-KEY": "test-secret-key"}

        response = ingestor.sync_inventory(mock_request)
        self.assertEqual(response, ("Method Not Allowed", 405))
