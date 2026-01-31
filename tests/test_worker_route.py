
import unittest
from unittest.mock import MagicMock, patch
import sys
import json
import base64
import os
import importlib

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules
mock_ff = MagicMock()
mock_ff.http.side_effect = lambda f: f
sys.modules['functions_framework'] = mock_ff

sys.modules['config'] = MagicMock()
sys.modules['config'].PHONE_NUMBER_ID = "123"
sys.modules['config'].WHATSAPP_TOKEN = "abc"
sys.modules['config'].VERIFY_TOKEN = "verify"
sys.modules['config'].PUBSUB_TOPIC = "projects/my-project/topics/my-topic"
sys.modules['config'].logger = MagicMock()

# Mock PubSub
mock_pubsub = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = mock_pubsub
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.texttospeech'] = MagicMock()

# Mock heavy deps
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()

import main

class TestWorkerRoute(unittest.TestCase):
    def setUp(self):
        # Reload main to ensure it uses the mocked configuration
        importlib.reload(main)

        # Setup Flask test client
        self.client = main.app.test_client()

    @patch('main._process_message_logic')
    def test_worker_processed(self, mock_process):
        # Setup
        msg_payload = {"msg": {"id": "123", "text": "Hello"}, "phone": "555"}
        data_str = json.dumps(msg_payload)
        data_b64 = base64.b64encode(data_str.encode("utf-8")).decode("utf-8")

        pubsub_payload = {
            "message": {
                "data": data_b64
            }
        }

        # Act
        response = self.client.post('/worker', json=pubsub_payload)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode('utf-8'), "OK")
        mock_process.assert_called_with({"id": "123", "text": "Hello"}, "555")

if __name__ == '__main__':
    unittest.main()
