import unittest
import sys
from unittest.mock import patch, MagicMock

# --- MOCK HEAVY DEPENDENCIES BEFORE IMPORTS ---
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock() # Specific mock for pubsub
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
sys.modules['functions_framework'] = MagicMock()
sys.modules['functions_framework'].http = lambda f: f

import main

class TestWebhookVerification(unittest.TestCase):

    @patch('main.config')
    def test_webhook_verification_success(self, mock_config):
        mock_config.VERIFY_TOKEN = "correct_token"

        with main.app.test_request_context('/webhook?hub.verify_token=correct_token&hub.challenge=12345'):
            response = main.whatsapp_webhook()
            # It returns tuple (body, status) or just body if status is 200 implied?
            # In main.py: return request.args.get("hub.challenge"), 200
            self.assertEqual(response[0], "12345")
            self.assertEqual(response[1], 200)

    @patch('main.config')
    def test_webhook_verification_failure(self, mock_config):
        mock_config.VERIFY_TOKEN = "correct_token"

        with main.app.test_request_context('/webhook?hub.verify_token=wrong_token&hub.challenge=12345'):
            response = main.whatsapp_webhook()
            self.assertEqual(response[0], "Forbidden")
            self.assertEqual(response[1], 403)

    @patch('main.config')
    def test_webhook_verification_none_config(self, mock_config):
        # Case where config.VERIFY_TOKEN is None (not set in env)
        mock_config.VERIFY_TOKEN = None

        # Even if user sends None (or empty), it should fail safe
        # request.args.get returns None if missing
        with main.app.test_request_context('/webhook'): # No params
            response = main.whatsapp_webhook()
            self.assertEqual(response[0], "Forbidden")
            self.assertEqual(response[1], 403)

    @patch('main.config')
    @patch('secrets.compare_digest')
    def test_webhook_uses_secure_comparison(self, mock_compare, mock_config):
        # This test verifies that we are using secrets.compare_digest
        # Note: This will FAIL until we implement the fix
        mock_config.VERIFY_TOKEN = "correct_token"
        mock_compare.return_value = True

        with main.app.test_request_context('/webhook?hub.verify_token=correct_token&hub.challenge=12345'):
            main.whatsapp_webhook()
            mock_compare.assert_called()

if __name__ == '__main__':
    unittest.main()
