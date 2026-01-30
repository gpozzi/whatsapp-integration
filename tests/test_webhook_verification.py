import unittest
from unittest.mock import MagicMock, patch
import sys
import json
import os
import hashlib
import hmac
import importlib

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules to prevent import errors
sys.modules['functions_framework'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()

# Mock config initially
sys.modules['config'] = MagicMock()
sys.modules['config'].VERIFY_TOKEN = "test_verify_token"
sys.modules['config'].APP_SECRET = None # Default state
sys.modules['config'].logger = MagicMock()

import main

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        # Reload main to ensure clean state and fresh config mock usage
        importlib.reload(main)
        # Mock dependencies in main
        main.publisher = MagicMock()
        main.brain = MagicMock()
        self.client = main.app.test_client()
        self.app_secret = "secret123"

    def test_missing_app_secret_allows_request(self):
        # When APP_SECRET is None, it should allow requests (log warning)
        main.config.APP_SECRET = None

        # We use a valid JSON payload that would normally pass
        payload = json.dumps({"entry": []}).encode('utf-8')
        headers = {"Content-Type": "application/json"}

        response = self.client.post('/webhook', data=payload, headers=headers)

        self.assertEqual(response.status_code, 200)

    def test_app_secret_set_pubsub_bypass_returns_200(self):
        main.config.APP_SECRET = self.app_secret

        payload = json.dumps({"entry": []}).encode('utf-8')
        # No signature, but User-Agent is PubSub
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Google-Cloud-PubSub"
        }

        response = self.client.post('/webhook', data=payload, headers=headers)

        # Should be allowed (200 OK because empty entry returns OK)
        self.assertEqual(response.status_code, 200)

    def test_app_secret_set_missing_signature_returns_403(self):
        main.config.APP_SECRET = self.app_secret

        payload = json.dumps({"entry": []}).encode('utf-8')
        headers = {"Content-Type": "application/json"}

        response = self.client.post('/webhook', data=payload, headers=headers)

        self.assertEqual(response.status_code, 403)

    def test_app_secret_set_invalid_signature_returns_403(self):
        main.config.APP_SECRET = self.app_secret

        payload = json.dumps({"entry": []}).encode('utf-8')
        # Generate signature with wrong secret
        signature = hmac.new(b"wrong_secret", payload, hashlib.sha256).hexdigest()

        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json"
        }

        response = self.client.post('/webhook', data=payload, headers=headers)

        self.assertEqual(response.status_code, 403)

    def test_app_secret_set_valid_signature_returns_200(self):
        main.config.APP_SECRET = self.app_secret

        payload = json.dumps({"entry": []}).encode('utf-8')
        # Generate valid signature
        signature = hmac.new(self.app_secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()

        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json"
        }

        response = self.client.post('/webhook', data=payload, headers=headers)

        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
