import unittest
import hmac
import hashlib
import json
import base64
from unittest.mock import patch, MagicMock
import sys

# Mock google modules before importing main
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['brain'] = MagicMock()
sys.modules['ingestor'] = MagicMock()

import main
import config

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        self.app = main.app.test_client()
        self.app.testing = True
        self.secret = "my_secret_token"

        # Patch APP_SECRET in config
        self.patcher = patch('config.APP_SECRET', self.secret)
        self.mock_secret = self.patcher.start()

        # Patch brain logic to avoid errors
        self.process_patcher = patch('main._process_message_logic')
        self.mock_process = self.process_patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.process_patcher.stop()

    def generate_signature(self, payload):
        return 'sha256=' + hmac.new(
            self.secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

    def test_webhook_valid_signature(self):
        payload = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": "12345", "id": "wamid.123"}]}}]}]}).encode('utf-8')
        signature = self.generate_signature(payload)

        response = self.app.post(
            '/webhook',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'X-Hub-Signature-256': signature
            }
        )
        self.assertEqual(response.status_code, 200)

    def test_webhook_invalid_signature(self):
        payload = json.dumps({"entry": []}).encode('utf-8')
        signature = "sha256=invalidsignature"

        response = self.app.post(
            '/webhook',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'X-Hub-Signature-256': signature
            }
        )
        self.assertEqual(response.status_code, 403)

    def test_webhook_missing_signature(self):
        payload = json.dumps({"entry": []}).encode('utf-8')

        response = self.app.post(
            '/webhook',
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(response.status_code, 403)

    def test_pubsub_bypass(self):
        # Pub/Sub payload structure
        inner_data = json.dumps({"msg": {"id": "123"}, "phone": "555"}).encode('utf-8')
        b64_data = base64.b64encode(inner_data).decode('utf-8')

        pubsub_payload = json.dumps({
            "message": {
                "data": b64_data
            }
        }).encode('utf-8')

        # Should succeed WITHOUT signature because it hits the Pub/Sub block first
        response = self.app.post(
            '/webhook',
            data=pubsub_payload,
            headers={'Content-Type': 'application/json'}
        )
        self.assertEqual(response.status_code, 200)
        self.mock_process.assert_called_once()

if __name__ == '__main__':
    unittest.main()
