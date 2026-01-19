import unittest
import sys
from unittest.mock import patch, MagicMock
import secrets

# --- MOCK HEAVY DEPENDENCIES BEFORE IMPORTS ---
# We need to mock these because main.py imports brain.py which imports these
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
sys.modules['functions_framework'] = MagicMock()

# Ensure functions_framework.http decorator works
sys.modules['functions_framework'].http = lambda f: f

import main

class TestWebhookVerification(unittest.TestCase):

    def setUp(self):
        self.app = main.app.test_client()
        self.app.testing = True

    @patch('main.config')
    def test_verify_token_success(self, mock_config):
        """Test that correct token returns challenge."""
        mock_config.VERIFY_TOKEN = "my_secret_token"

        response = self.app.get('/webhook', query_string={
            "hub.verify_token": "my_secret_token",
            "hub.challenge": "12345"
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode(), "12345")

    @patch('main.config')
    def test_verify_token_failure(self, mock_config):
        """Test that incorrect token returns 403."""
        mock_config.VERIFY_TOKEN = "my_secret_token"

        response = self.app.get('/webhook', query_string={
            "hub.verify_token": "wrong_token",
            "hub.challenge": "12345"
        })

        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_verify_token_none_config(self, mock_config):
        """Test behavior when config token is None (should fail safe)."""
        mock_config.VERIFY_TOKEN = None

        response = self.app.get('/webhook', query_string={
            "hub.verify_token": "any_token",
            "hub.challenge": "12345"
        })

        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_verify_token_none_request(self, mock_config):
        """Test behavior when request token is missing."""
        mock_config.VERIFY_TOKEN = "secret"

        response = self.app.get('/webhook', query_string={
            "hub.challenge": "12345"
        })

        self.assertEqual(response.status_code, 403)

    @patch('main.secrets.compare_digest')
    @patch('main.config')
    def test_uses_secure_compare(self, mock_config, mock_compare):
        """Verify that secrets.compare_digest is actually used."""
        mock_config.VERIFY_TOKEN = "my_secret_token"
        mock_compare.return_value = True # Pretend it matches

        self.app.get('/webhook', query_string={
            "hub.verify_token": "my_secret_token",
            "hub.challenge": "12345"
        })

        # This assertion is expected to fail initially because main.py uses ==
        mock_compare.assert_called()

if __name__ == '__main__':
    unittest.main()
