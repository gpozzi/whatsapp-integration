import unittest
import sys
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock

# --- MOCK HEAVY DEPENDENCIES BEFORE IMPORTS ---
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()

import main
import config

class TestWebhookSignature(unittest.TestCase):

    def setUp(self):
        self.app = main.app.test_client()
        self.app_secret = "secret123"

        # Valid Payload
        self.payload = {
            "object": "whatsapp_business_account",
            "entry": [{"id": "123", "changes": [{"value": {
                "messages": [{
                    "from": "123456789",
                    "id": "wamid.HBgLM...",
                    "timestamp": "1700000000",
                    "type": "text",
                    "text": {"body": "Hello"}
                }]
            }}]}]
        }
        self.payload_bytes = json.dumps(self.payload).encode('utf-8')

    @patch('main.config')
    def test_webhook_no_signature_no_config(self, mock_config):
        """Should ALLOW requests if APP_SECRET is not configured (Fail Open)."""
        # Ensure APP_SECRET is None
        mock_config.APP_SECRET = None
        mock_config.VERIFY_TOKEN = "token"

        response = self.app.post('/webhook', json=self.payload)
        self.assertEqual(response.status_code, 200)

    @patch('main.config')
    def test_webhook_no_signature_with_config(self, mock_config):
        """Should REJECT requests if APP_SECRET is configured but signature missing."""
        mock_config.APP_SECRET = self.app_secret

        # Send without X-Hub-Signature-256
        response = self.app.post('/webhook', data=self.payload_bytes, content_type='application/json')
        # CURRENTLY: It returns 200 because logic isn't implemented.
        # Once implemented, this assertion will need to be status_code 403.
        # For TDD, I assert 200 now, and will change to 403 after implementation to verify fix.
        # But wait, Sentinel instruction says "Verify the vulnerability is actually fixed".
        # So I will write the test to expect 403, and it should FAIL now.

        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_webhook_bad_signature(self, mock_config):
        """Should REJECT requests with invalid signature."""
        mock_config.APP_SECRET = self.app_secret

        # Generate BAD signature
        signature = "sha256=badsignature"

        headers = {
            "X-Hub-Signature-256": signature
        }

        response = self.app.post('/webhook', data=self.payload_bytes, headers=headers, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_webhook_valid_signature(self, mock_config):
        """Should ALLOW requests with valid signature."""
        mock_config.APP_SECRET = self.app_secret
        mock_config.PUBSUB_TOPIC = None # Disable Pub/Sub logic for this test

        # Generate VALID signature
        # HMAC-SHA256
        sig = hmac.new(
            self.app_secret.encode('utf-8'),
            self.payload_bytes,
            hashlib.sha256
        ).hexdigest()
        signature = f"sha256={sig}"

        headers = {
            "X-Hub-Signature-256": signature
        }

        response = self.app.post('/webhook', data=self.payload_bytes, headers=headers, content_type='application/json')
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
