
import unittest
import sys
from unittest.mock import patch, MagicMock

# Mock functions_framework and requests
mock_ff = MagicMock()
mock_ff.http.side_effect = lambda f: f
sys.modules['functions_framework'] = mock_ff
sys.modules['requests'] = MagicMock()

import main
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
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "123456789",
                            "type": "text",
                            "timestamp": str(int(time.time())),
                            "text": {"body": large_text}
                        }]
                    }
                }]
            }]
        }

        # Create a mock request object
        request = MagicMock()
        request.method = "POST"
        request.get_json.return_value = payload

        # Call the webhook
        response = main.whatsapp_webhook(request)

        # Verify response
        self.assertEqual(response, ("OK", 200))

        # Check if brain.process_message was called with TRUNCATED text
        expected_text = "A" * 1000 + "..."
        mock_brain.process_message.assert_called_with(expected_text, "123456789", None)

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
