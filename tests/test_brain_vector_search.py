import unittest
from unittest.mock import MagicMock, patch, ANY
import sys

# Mock libraries to avoid installation
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.texttospeech'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_core'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()

# Re-import brain after mocking
import brain
import config

class TestBrainVectorSearch(unittest.TestCase):
    def setUp(self):
        # Reset global state in brain
        brain._db_client = None
        brain._safety_model = None

        # Setup mocks
        self.mock_firestore_client = MagicMock()
        self.mock_sales_llm = MagicMock()
        self.mock_safety_model = MagicMock()
        self.mock_embeddings_service = MagicMock()

        # Patch classes in brain
        self.patcher_firestore = patch('brain.firestore.Client', return_value=self.mock_firestore_client)
        self.patcher_chat_vertex_ai = patch('brain.ChatVertexAI')
        self.patcher_vertex_embeddings = patch('brain.VertexAIEmbeddings', return_value=self.mock_embeddings_service)

        self.mock_firestore_cls = self.patcher_firestore.start()
        self.mock_chat_vertex_ai_cls = self.patcher_chat_vertex_ai.start()
        self.mock_vertex_embeddings_cls = self.patcher_vertex_embeddings.start()

        # Configure ChatVertexAI mock to return different models based on model_name
        def side_effect_chat(*args, **kwargs):
            if kwargs.get('model_name') == brain.MODEL_SALES:
                return self.mock_sales_llm
            elif kwargs.get('model_name') == brain.MODEL_SAFETY:
                return self.mock_safety_model
            return MagicMock()

        self.mock_chat_vertex_ai_cls.side_effect = side_effect_chat

    def tearDown(self):
        self.patcher_firestore.stop()
        self.patcher_chat_vertex_ai.stop()
        self.patcher_vertex_embeddings.stop()

    def test_search_cars(self):
        # Setup Vector Search Mock
        mock_collection = self.mock_firestore_client.collection.return_value
        mock_find_nearest = mock_collection.find_nearest.return_value

        # Mock results
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {"make": "Toyota", "model": "Corolla", "year": 2020, "embedding_field": "..."}
        mock_find_nearest.get.return_value = [mock_doc]

        # Initialize services to set _db_client
        brain._init_services()

        # Run search
        result = brain._search_cars("Toyota Corolla")

        # Verification
        self.mock_embeddings_service.embed_query.assert_called_with("Toyota Corolla")
        mock_collection.find_nearest.assert_called()
        self.assertIn("Toyota", result)
        self.assertIn("Corolla", result)

    def test_process_message_rag_flow(self):
        # Setup Mocks
        brain._init_services()

        # Mock Safety (Intent)
        self.mock_safety_model.invoke.return_value.content = "CATEGORY: SALES_QUERY | TONE: CASUAL"

        # Mock Vector Search (via _search_cars internal call or mocking _search_cars directly)
        # We'll mock _search_cars to simplify
        with patch('brain._search_cars', return_value="[Inventory Context: Toyota Corolla Available]") as mock_search:
            # Mock Sales LLM response
            self.mock_sales_llm.invoke.return_value.content = "Tenemos un Toyota Corolla disponible."

            # Run process_message
            response = brain.process_message("Busco un auto", "123456789")

            # Assertions
            mock_search.assert_called()
            self.mock_sales_llm.invoke.assert_called()
            # Check prompt contained context
            call_args = self.mock_sales_llm.invoke.call_args
            prompt_sent = call_args[0][0]
            self.assertIn("Toyota Corolla Available", prompt_sent)
            self.assertEqual(response, "Tenemos un Toyota Corolla disponible.")

if __name__ == '__main__':
    unittest.main()
