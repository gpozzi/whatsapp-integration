import unittest
import sys
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock

# --- MOCK HEAVY DEPENDENCIES ---
# We verify these are mocked to prevent import errors or side effects
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
sys.modules['brain'] = MagicMock()
# Do not mock ingestor globally to avoid breaking test_ingestor.py
# sys.modules['ingestor'] = MagicMock()

import main

class TestWebhookSignature(unittest.TestCase):

    def setUp(self):
        self.app = main.app.test_client()
        self.app.testing = True

    def calculate_signature(self, payload, secret):
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    @patch('main.config')
    @patch('main.brain')
    def test_webhook_valid_signature(self, mock_brain, mock_config):
        mock_config.APP_SECRET = "secret123"
        mock_config.VERIFY_TOKEN = "token"
        # Mock pubsub topic to avoid trying to publish
        mock_config.PUBSUB_TOPIC = None

        payload = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": "123", "id": "1", "timestamp": "12345"}]}}]}]})
        signature = self.calculate_signature(payload, "secret123")

        headers = {'X-Hub-Signature-256': signature}
        response = self.app.post('/webhook', data=payload, headers=headers, content_type='application/json')

        self.assertEqual(response.status_code, 200)

    @patch('main.config')
    def test_webhook_invalid_signature(self, mock_config):
        mock_config.APP_SECRET = "secret123"

        payload = json.dumps({"foo": "bar"})
        signature = self.calculate_signature(payload, "wrong_secret")

        headers = {'X-Hub-Signature-256': signature}
        response = self.app.post('/webhook', data=payload, headers=headers, content_type='application/json')

        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_webhook_missing_signature_header(self, mock_config):
        mock_config.APP_SECRET = "secret123"

        payload = json.dumps({"foo": "bar"})
        # No header
        response = self.app.post('/webhook', data=payload, content_type='application/json')

        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    @patch('main.brain')
    def test_webhook_no_secret_configured_bypass(self, mock_brain, mock_config):
        mock_config.APP_SECRET = None # Not configured
        mock_config.PUBSUB_TOPIC = None

        payload = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": "123", "id": "1", "timestamp": "12345"}]}}]}]})

        # Should pass even without signature
        response = self.app.post('/webhook', data=payload, content_type='application/json')

        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
