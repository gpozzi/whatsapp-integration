import unittest
from unittest.mock import patch, MagicMock
import sys

# Mock dependencies
sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['brain'] = MagicMock()
sys.modules['ingestor'] = MagicMock()

import main
import secrets

class TestWebhookVerification(unittest.TestCase):

    @patch('main.config')
    def test_verify_token_safe_comparison(self, mock_config):
        # Setup
        mock_config.VERIFY_TOKEN = "secure_token"

        # Test 1: Valid token
        with main.app.test_request_context('/webhook?hub.verify_token=secure_token&hub.challenge=123', method='GET'):
            response, status = main.whatsapp_webhook()
            self.assertEqual(status, 200)
            self.assertEqual(response, "123")

        # Test 2: Invalid token
        with main.app.test_request_context('/webhook?hub.verify_token=wrong_token&hub.challenge=123', method='GET'):
            response, status = main.whatsapp_webhook()
            self.assertEqual(status, 403)

        # Test 3: None config token (should fail safely)
        mock_config.VERIFY_TOKEN = None
        with main.app.test_request_context('/webhook?hub.verify_token=None&hub.challenge=123', method='GET'):
            # Current implementation might fail or behave unexpectedly if not handled
            response, status = main.whatsapp_webhook()
            self.assertEqual(status, 403)

        # Test 4: Verify use of secrets.compare_digest
        # We can't easily assert that secrets.compare_digest was called without mocking it inside main.
        # But we can check that we are replacing the logic.

    @patch('main.secrets.compare_digest')
    @patch('main.config')
    def test_verify_token_uses_compare_digest(self, mock_config, mock_compare_digest):
        mock_config.VERIFY_TOKEN = "secure_token"
        mock_compare_digest.return_value = True

        with main.app.test_request_context('/webhook?hub.verify_token=secure_token&hub.challenge=123', method='GET'):
             main.whatsapp_webhook()
             mock_compare_digest.assert_called()

if __name__ == '__main__':
    unittest.main()
