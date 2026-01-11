import unittest
from unittest.mock import MagicMock, patch
import sys
import secrets

# Mock modules to avoid needing actual GCP credentials
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()

import main
import config

class TestWebhookTimingAttack(unittest.TestCase):
    def setUp(self):
        self.original_verify_token = config.VERIFY_TOKEN
        config.VERIFY_TOKEN = "secure-token-123"

    def tearDown(self):
        config.VERIFY_TOKEN = self.original_verify_token

    def test_webhook_verification_uses_compare_digest(self):
        """
        Verify that the webhook verification logic uses secrets.compare_digest
        to prevent timing attacks.
        """
        with patch('secrets.compare_digest', side_effect=secrets.compare_digest) as mock_compare:
            with main.app.test_request_context('/webhook?hub.verify_token=secure-token-123&hub.challenge=12345', method='GET'):
                response = main.whatsapp_webhook()
                # Should match and return challenge
                self.assertEqual(response, ("12345", 200))

                # MUST call secrets.compare_digest
                mock_compare.assert_called_once()
                args, _ = mock_compare.call_args
                self.assertEqual(args[0], "secure-token-123")
                self.assertEqual(args[1], "secure-token-123")

    def test_webhook_verification_handles_none(self):
        """
        Verify logic is robust when token is None (e.g. missing param).
        secrets.compare_digest throws TypeError if args are not strings.
        We must handle this gracefully.
        """
        # Case 1: hub.verify_token is missing (None)
        with main.app.test_request_context('/webhook?hub.challenge=12345', method='GET'):
            response = main.whatsapp_webhook()
            self.assertEqual(response, ("Forbidden", 403))

    def test_webhook_verification_handles_config_none(self):
        """
        Verify logic is robust when config.VERIFY_TOKEN is None (misconfiguration).
        """
        config.VERIFY_TOKEN = None
        with main.app.test_request_context('/webhook?hub.verify_token=any&hub.challenge=12345', method='GET'):
             response = main.whatsapp_webhook()
             self.assertEqual(response, ("Forbidden", 403))

if __name__ == '__main__':
    unittest.main()
