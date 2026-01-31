import unittest
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock
import sys

# Import main and config
# We assume dependencies are installed or handled by other tests/environment
import main
import config
import importlib

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        # Restore config in sys.modules if it was mocked by other tests
        if isinstance(sys.modules.get('config'), MagicMock):
             sys.modules['config'] = config

        # Reload main to ensure it uses the real config and fresh state
        importlib.reload(main)

        self.app = main.app.test_client()
        self.app.testing = True

        # Save original config
        self._original_app_secret = config.APP_SECRET
        self._original_verify_token = config.VERIFY_TOKEN
        self._original_pubsub_topic = config.PUBSUB_TOPIC

        # Set config for test
        config.APP_SECRET = "secret_key"
        config.VERIFY_TOKEN = "verify_token"
        config.PUBSUB_TOPIC = "projects/test/topics/test"

        # Patch main.brain and main.ingestor to avoid side effects
        self.brain_patcher = patch('main.brain')
        self.ingestor_patcher = patch('main.ingestor')
        self.publisher_patcher = patch('main.publisher')
        self.requests_patcher = patch('main.requests')

        self.mock_brain = self.brain_patcher.start()
        self.mock_ingestor = self.ingestor_patcher.start()
        self.mock_publisher = self.publisher_patcher.start()
        self.mock_requests = self.requests_patcher.start()

    def tearDown(self):
        # Restore config
        config.APP_SECRET = self._original_app_secret
        config.VERIFY_TOKEN = self._original_verify_token
        config.PUBSUB_TOPIC = self._original_pubsub_topic

        # Stop patchers
        self.brain_patcher.stop()
        self.ingestor_patcher.stop()
        self.publisher_patcher.stop()
        self.requests_patcher.stop()

    def calculate_signature(self, payload, secret):
        return 'sha256=' + hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def test_valid_signature(self):
        payload = json.dumps({"entry": []})
        signature = self.calculate_signature(payload, config.APP_SECRET)
        headers = {'X-Hub-Signature-256': signature}

        response = self.app.post('/webhook', data=payload, headers=headers, content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_invalid_signature(self):
        payload = json.dumps({"entry": []})
        signature = self.calculate_signature(payload, "wrong_secret")
        headers = {'X-Hub-Signature-256': signature}

        response = self.app.post('/webhook', data=payload, headers=headers, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_missing_signature(self):
        payload = json.dumps({"entry": []})
        # No signature header
        response = self.app.post('/webhook', data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_pubsub_bypass(self):
        # Pub/Sub payload should bypass check because it is handled by the Pub/Sub block
        payload = json.dumps({"message": {"data": "e30="}}) # {} in base64
        headers = {'User-Agent': 'Google-Cloud-PubSub'}

        response = self.app.post('/webhook', data=payload, headers=headers, content_type='application/json')

        # We only care that it passed the 401/403 checks
        self.assertNotIn(response.status_code, [401, 403])

    def test_bypass_attempt_fails(self):
        # WhatsApp payload with Pub/Sub User-Agent but MISSING signature should FAIL.
        # This verifies that User-Agent alone is not enough to bypass verification for WhatsApp logic.
        payload = json.dumps({"entry": []})
        headers = {'User-Agent': 'Google-Cloud-PubSub'}

        response = self.app.post('/webhook', data=payload, headers=headers, content_type='application/json')

        # Should be forbidden because it falls through Pub/Sub check and hits WhatsApp verification
        self.assertEqual(response.status_code, 403)

    def test_no_app_secret_configured(self):
        # Unset APP_SECRET
        config.APP_SECRET = None
        payload = json.dumps({"entry": []})

        # Should succeed without signature because logic is skipped
        response = self.app.post('/webhook', data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
