import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import importlib

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules before importing main
mock_ff = MagicMock()
mock_ff.http.side_effect = lambda f: f
sys.modules['functions_framework'] = mock_ff

sys.modules['config'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()

import main

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        # Default config
        sys.modules['config'].VERIFY_TOKEN = "secret_token"
        importlib.reload(main)
        self.client = main.app.test_client()

    def test_verify_token_success(self):
        """Test that correct token returns challenge and 200."""
        response = self.client.get('/webhook', query_string={
            "hub.verify_token": "secret_token",
            "hub.challenge": "12345"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode('utf-8'), "12345")

    def test_verify_token_failure(self):
        """Test that incorrect token returns 403."""
        response = self.client.get('/webhook', query_string={
            "hub.verify_token": "wrong_token",
            "hub.challenge": "12345"
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.decode('utf-8'), "Forbidden")

    def test_verify_token_none_config(self):
        """Test that if config.VERIFY_TOKEN is None, access is denied."""
        sys.modules['config'].VERIFY_TOKEN = None
        importlib.reload(main)
        client = main.app.test_client()

        # Even if we send None, it should fail (or strict string comparison)
        response = client.get('/webhook', query_string={
            # No hub.verify_token sent, so it will be None in request.args
            "hub.challenge": "12345"
        })
        self.assertEqual(response.status_code, 403)

    def test_verify_token_missing_in_request(self):
        """Test that missing token in request returns 403."""
        response = self.client.get('/webhook', query_string={
            "hub.challenge": "12345"
        })
        self.assertEqual(response.status_code, 403)

if __name__ == '__main__':
    unittest.main()
