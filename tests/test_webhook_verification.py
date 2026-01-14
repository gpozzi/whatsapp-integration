import unittest
import sys
from unittest.mock import patch, MagicMock

# --- MOCK HEAVY DEPENDENCIES BEFORE IMPORTS ---
# We need to mock these to avoid import errors or side effects during testing
# independent of whether the code actually uses them in the path we test.
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_core'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()

# Now we can import main
import main

class TestWebhookVerification(unittest.TestCase):

    def setUp(self):
        self.app = main.app.test_client()
        self.app.testing = True

    @patch('main.config')
    def test_webhook_verify_success(self, mock_config):
        """Test that correct token returns challenge."""
        mock_config.VERIFY_TOKEN = "my_secure_token"

        # We assume the implementation will use secrets.compare_digest,
        # but functionality-wise it should return 200.
        response = self.app.get('/webhook', query_string={
            "hub.verify_token": "my_secure_token",
            "hub.challenge": "12345"
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode('utf-8'), "12345")

    @patch('main.config')
    def test_webhook_verify_failure(self, mock_config):
        """Test that incorrect token returns 403."""
        mock_config.VERIFY_TOKEN = "my_secure_token"

        response = self.app.get('/webhook', query_string={
            "hub.verify_token": "wrong_token",
            "hub.challenge": "12345"
        })

        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_webhook_verify_none_token(self, mock_config):
        """Test handling when config token is None (not set)."""
        mock_config.VERIFY_TOKEN = None

        response = self.app.get('/webhook', query_string={
            "hub.verify_token": "some_token",
            "hub.challenge": "12345"
        })

        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_webhook_verify_missing_param(self, mock_config):
        """Test handling when verify_token param is missing."""
        mock_config.VERIFY_TOKEN = "token"

        response = self.app.get('/webhook', query_string={
            "hub.challenge": "12345"
        })

        self.assertEqual(response.status_code, 403)

if __name__ == '__main__':
    unittest.main()
