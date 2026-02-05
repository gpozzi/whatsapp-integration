import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import hmac
import hashlib
import json
import importlib

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules to avoid loading them
sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['functions_framework'] = MagicMock()
sys.modules['functions_framework'].http = lambda f: f

# Mock config
sys.modules['config'] = MagicMock()
sys.modules['config'].VERIFY_TOKEN = "test_verify"
sys.modules['config'].APP_SECRET = "secret123"
sys.modules['config'].logger = MagicMock()

import main
import security

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        # Reload main to ensure clean state
        importlib.reload(main)
        self.client = main.app.test_client()

        # Reset APP_SECRET for each test (default to set)
        main.config.APP_SECRET = "secret123"

    def calculate_signature(self, payload, secret):
        return hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

    def test_valid_signature(self):
        payload = json.dumps({"entry": []}).encode('utf-8')
        signature = self.calculate_signature(payload, "secret123")
        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json"
        }

        response = self.client.post('/webhook', data=payload, headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_invalid_signature(self):
        payload = json.dumps({"entry": []}).encode('utf-8')
        signature = self.calculate_signature(payload, "wrong_secret")
        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json"
        }

        response = self.client.post('/webhook', data=payload, headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_missing_signature_when_secret_configured(self):
        payload = json.dumps({"entry": []}).encode('utf-8')
        headers = {
            "Content-Type": "application/json"
        }

        response = self.client.post('/webhook', data=payload, headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_pubsub_bypass(self):
        # Pub/Sub payload structure
        payload_dict = {
            "message": {
                "data": "eyJmb28iOiJiYXIifQ==", # {"foo":"bar"} base64
                "messageId": "123"
            },
            "subscription": "projects/my-project/subscriptions/my-sub"
        }
        payload = json.dumps(payload_dict).encode('utf-8')

        # No signature provided
        headers = {
            "Content-Type": "application/json"
        }

        # Should be allowed (200 or 400 depending on inner logic, but NOT 403)
        # In main.py, it calls _process_message_logic or fails decoding.
        # But it should pass the verification check.

        # Since the payload doesn't match the specific Pub/Sub format expected by the inner logic
        # (payload['msg'] and payload['phone']), it might log error or return something else.
        # But the point is to bypass 403 Forbidden.

        response = self.client.post('/webhook', data=payload, headers=headers)

        # If it returns 400 "Bad Request" (from inner Pub/Sub logic exception), it means it PASSED the 403 check.
        # If it returns 200 "OK", it passed.
        # If it returns 403, it failed the bypass.
        self.assertNotEqual(response.status_code, 403)

    def test_no_secret_configured(self):
        # Unset APP_SECRET
        main.config.APP_SECRET = None

        payload = json.dumps({"entry": []}).encode('utf-8')
        headers = {
            "Content-Type": "application/json"
        }

        # Should pass (legacy mode)
        response = self.client.post('/webhook', data=payload, headers=headers)
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
