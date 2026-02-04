import unittest
from unittest.mock import MagicMock, patch
import sys
import json
import os
import hmac
import hashlib
import importlib

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules to prevent import errors or side effects
sys.modules['functions_framework'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()

# Mock config
sys.modules['config'] = MagicMock()
sys.modules['config'].PHONE_NUMBER_ID = "123"
sys.modules['config'].WHATSAPP_TOKEN = "abc"
sys.modules['config'].VERIFY_TOKEN = "verify"
sys.modules['config'].PUBSUB_TOPIC = "topic"
sys.modules['config'].logger = MagicMock()
# Default APP_SECRET to None for safety, override in tests
sys.modules['config'].APP_SECRET = None

import main

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        # Reload main to ensure it picks up config changes if any (though we mock config attributes)
        importlib.reload(main)
        # Mock brain to avoid real logic
        main.brain = MagicMock()
        main.publisher = MagicMock()

        self.client = main.app.test_client()
        self.secret = "my_secret_key"

    def generate_signature(self, payload, secret):
        return 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    def test_valid_signature(self):
        # Setup
        sys.modules['config'].APP_SECRET = self.secret
        payload = json.dumps({"entry": []}).encode('utf-8')
        signature = self.generate_signature(payload, self.secret)

        # Act
        response = self.client.post('/webhook',
                                    data=payload,
                                    headers={'X-Hub-Signature-256': signature, 'Content-Type': 'application/json'})

        # Assert
        self.assertEqual(response.status_code, 200)

    def test_invalid_signature(self):
        # Setup
        sys.modules['config'].APP_SECRET = self.secret
        payload = json.dumps({"entry": []}).encode('utf-8')
        signature = "sha256=invalid_signature"

        # Act
        response = self.client.post('/webhook',
                                    data=payload,
                                    headers={'X-Hub-Signature-256': signature, 'Content-Type': 'application/json'})

        # Assert
        self.assertEqual(response.status_code, 403)

    def test_missing_signature_blocked(self):
        # Setup
        sys.modules['config'].APP_SECRET = self.secret
        payload = json.dumps({"entry": []}).encode('utf-8')

        # Act
        response = self.client.post('/webhook',
                                    data=payload,
                                    headers={'Content-Type': 'application/json'})

        # Assert
        self.assertEqual(response.status_code, 403)

    def test_pubsub_bypass(self):
        # Setup
        sys.modules['config'].APP_SECRET = self.secret
        # Construct a Pub/Sub like payload
        # It needs 'message' and 'data'
        import base64
        inner_data = json.dumps({"msg": "hi", "phone": "123"}).encode('utf-8')
        b64_data = base64.b64encode(inner_data).decode('utf-8')

        payload_dict = {
            "message": {
                "data": b64_data,
                "messageId": "123"
            },
            "subscription": "projects/x/subscriptions/y"
        }
        payload = json.dumps(payload_dict).encode('utf-8')

        # Act - No Signature provided
        response = self.client.post('/webhook',
                                    data=payload,
                                    headers={'Content-Type': 'application/json'})

        # Assert
        self.assertEqual(response.status_code, 200)

    def test_no_secret_legacy(self):
        # Setup
        sys.modules['config'].APP_SECRET = None
        payload = json.dumps({"entry": []}).encode('utf-8')

        # Act
        response = self.client.post('/webhook',
                                    data=payload,
                                    headers={'Content-Type': 'application/json'})

        # Assert
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
