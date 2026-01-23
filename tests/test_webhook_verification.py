import unittest
from unittest.mock import MagicMock, patch
import sys
import importlib

class TestWebhookVerification(unittest.TestCase):

    def setUp(self):
        # Create patches for dependencies that trigger GCP calls
        self.patches = [
            patch.dict(sys.modules, {
                'brain': MagicMock(),
                'ingestor': MagicMock(),
                'google.cloud': MagicMock(), # This might be aggressive, but main imports pubsub_v1
                'google.cloud.pubsub_v1': MagicMock()
            })
        ]

        for p in self.patches:
            p.start()

        # Reload main to ensure it picks up mocks if needed,
        # but mainly to get a fresh app instance if we wanted.
        # However, main.app is global.

        # If main is already loaded, we might need to reload it to ensure
        # module-level code runs with mocks (like publisher client),
        # though main catches that exception.

        # Simple approach: just import main.
        # If it's already in sys.modules, fine.
        # If we patch config.VERIFY_TOKEN, main.whatsapp_webhook will see it
        # because it accesses config.VERIFY_TOKEN at runtime.

        import main
        self.app = main.app.test_client()
        self.app.testing = True

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_verify_token_success(self):
        """Test that correct token returns challenge and 200 OK."""
        with patch('config.VERIFY_TOKEN', "my-secret-token"):
            response = self.app.get('/webhook', query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "my-secret-token",
                "hub.challenge": "1234567890"
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data.decode('utf-8'), "1234567890")

    def test_verify_token_failure(self):
        """Test that incorrect token returns 403 Forbidden."""
        with patch('config.VERIFY_TOKEN', "my-secret-token"):
            response = self.app.get('/webhook', query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "1234567890"
            })
            self.assertEqual(response.status_code, 403)

    def test_verify_token_none_bypass(self):
        """
        Test the vulnerability where if config.VERIFY_TOKEN is None,
        a request with no token might pass verification.
        """
        with patch('config.VERIFY_TOKEN', None):
            # Request without hub.verify_token
            response = self.app.get('/webhook', query_string={
                "hub.mode": "subscribe",
                "hub.challenge": "bypass-attempt"
            })

            # Should be 403 now
            self.assertEqual(response.status_code, 403)
