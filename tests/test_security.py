import unittest
import sys
from unittest.mock import patch, MagicMock
import ast

# --- MOCK HEAVY DEPENDENCIES BEFORE IMPORTS ---
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
# Mock module where PythonAstREPLTool resides
sys.modules['functions_framework'] = MagicMock()
# sys.modules['requests'] = MagicMock() # DO NOT mock requests if we want to test import validity

# Ensure functions_framework.http decorator works
sys.modules['functions_framework'].http = lambda f: f

import main
import security
import json
import time

class TestSecurity(unittest.TestCase):

    @patch('main.brain')
    @patch('main.requests')
    @patch('main.config')
    def test_webhook_large_input_truncated(self, mock_config, mock_requests, mock_brain):
        # Setup mocks
        mock_config.VERIFY_TOKEN = "test_token"
        mock_config.PHONE_NUMBER_ID = "123456"
        mock_config.WHATSAPP_TOKEN = "token"

        # Create a large payload
        large_text = "A" * 5000
        msg = {
            "from": "123456789",
            "type": "text",
            "id": "msg_id_1",
            "timestamp": str(int(time.time())),
            "text": {"body": large_text}
        }

        # Call the logic directly (worker logic)
        main._process_message_logic(msg, "123456789")

        # Check if brain.process_message was called with TRUNCATED text
        expected_text = "A" * 1000 + "..."
        # Updated assertion to include image_data=None
        mock_brain.process_message.assert_called_with(expected_text, "123456789", "msg_id_1", image_data=None, audio_data=None)

    @patch('main.requests')
    @patch('main.config')
    def test_send_whatsapp_timeout(self, mock_config, mock_requests):
        # Setup mocks
        mock_config.PHONE_NUMBER_ID = "123456"
        mock_config.WHATSAPP_TOKEN = "token"

        # Call send_whatsapp
        main.send_whatsapp("123456789", "Hello")

        # Verify requests.post was called
        args, kwargs = mock_requests.post.call_args

        # Check if timeout is present in kwargs
        self.assertIn('timeout', kwargs)
        self.assertEqual(kwargs['timeout'], 10)

if __name__ == '__main__':
    unittest.main()
