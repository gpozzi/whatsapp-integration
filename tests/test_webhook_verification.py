import unittest
import sys
from unittest.mock import patch, MagicMock
import hmac
import hashlib
import json

# --- MOCK HEAVY DEPENDENCIES BEFORE IMPORTS ---
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
sys.modules['functions_framework'].http = lambda f: f

import main

class TestWebhookVerification(unittest.TestCase):

    def setUp(self):
        self.app = main.app.test_client()
        self.secret = "test_secret"

    def _calculate_signature(self, body, secret):
        return hmac.new(
            secret.encode('utf-8'),
            msg=body.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

    @patch('main.config')
    def test_missing_signature(self, mock_config):
        mock_config.APP_SECRET = self.secret
        mock_config.VERIFY_TOKEN = "token"

        response = self.app.post('/webhook', json={"entry": []})
        # Expect 403 Forbidden because signature is missing but APP_SECRET is set
        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_invalid_signature(self, mock_config):
        mock_config.APP_SECRET = self.secret

        body = json.dumps({"entry": []})
        headers = {
            "X-Hub-Signature-256": "sha256=invalid_signature"
        }

        response = self.app.post('/webhook', data=body, headers=headers, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_valid_signature(self, mock_config):
        mock_config.APP_SECRET = self.secret

        body = json.dumps({"entry": []})
        signature = self._calculate_signature(body, self.secret)
        headers = {
            "X-Hub-Signature-256": f"sha256={signature}"
        }

        response = self.app.post('/webhook', data=body, headers=headers, content_type='application/json')
        self.assertEqual(response.status_code, 200)

    @patch('main.config')
    def test_pubsub_bypass(self, mock_config):
        mock_config.APP_SECRET = self.secret

        # Pub/Sub payload structure
        payload = {
            "message": {
                "data": "eyJtc2ciOiB7ImlkIjogIjEifSwgInBob25lIjogIjEyMzQ1In0=" # base64 of valid inner payload
            }
        }
        body = json.dumps(payload)

        # No signature provided
        response = self.app.post('/webhook', data=body, content_type='application/json')

        # Should pass (200) because it looks like Pub/Sub
        self.assertEqual(response.status_code, 200)

    @patch('main.config')
    def test_no_secret_configured(self, mock_config):
        mock_config.APP_SECRET = None

        # No signature, no secret in config -> Should allow
        response = self.app.post('/webhook', json={"entry": []})
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
