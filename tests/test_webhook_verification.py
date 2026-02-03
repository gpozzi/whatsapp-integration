import unittest
import sys
import json
import hashlib
import hmac
import importlib
from unittest.mock import patch, MagicMock

# Mock dependencies
sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()

# Re-import main to apply mocks
import main
import config

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        # Ensure config is loaded and fresh
        if 'config' not in sys.modules:
            import config
        elif isinstance(sys.modules['config'], MagicMock):
            del sys.modules['config']
            import config
        else:
            importlib.reload(sys.modules['config'])

        # Ensure main is loaded and fresh
        if 'main' not in sys.modules:
            import main
        else:
            importlib.reload(sys.modules['main'])

        self.app = sys.modules['main'].app.test_client()
        self.app.testing = True

        # Reset config for each test
        self.original_app_secret = getattr(sys.modules['config'], 'APP_SECRET', None)

    def tearDown(self):
        sys.modules['config'].APP_SECRET = self.original_app_secret

    @patch('main.brain')
    def test_webhook_rejects_missing_signature(self, mock_brain):
        """
        Verify that requests without signature are rejected (403) when APP_SECRET is set.
        """
        sys.modules['config'].APP_SECRET = "test_secret"

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"value": {"messages": [{"from": "123", "id": "msg1", "timestamp": "123456"}]}}]}]
        }

        response = self.app.post('/webhook',
                                 data=json.dumps(payload),
                                 content_type='application/json')

        # BEFORE FIX: This will return 200 (fail this test)
        # AFTER FIX: This should return 403
        self.assertEqual(response.status_code, 403)

    @patch('main.brain')
    def test_webhook_valid_signature(self, mock_brain):
        """
        Test that a valid signature passes.
        """
        mock_brain.process_message.return_value = "OK"
        sys.modules['config'].APP_SECRET = "test_secret"
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"value": {"messages": [{"from": "123", "id": "msg1", "timestamp": "123456"}]}}]}]
        }
        data = json.dumps(payload).encode('utf-8')

        # Calculate signature
        signature = hmac.new(
            key="test_secret".encode('utf-8'),
            msg=data,
            digestmod=hashlib.sha256
        ).hexdigest()

        response = self.app.post('/webhook',
                                 data=data,
                                 content_type='application/json',
                                 headers={'X-Hub-Signature-256': f'sha256={signature}'})

        self.assertEqual(response.status_code, 200)

    @patch('main.brain')
    def test_webhook_invalid_signature(self, mock_brain):
        """
        Test that an invalid signature fails.
        """
        sys.modules['config'].APP_SECRET = "test_secret"
        payload = {"foo": "bar"}
        data = json.dumps(payload).encode('utf-8')

        response = self.app.post('/webhook',
                                 data=data,
                                 content_type='application/json',
                                 headers={'X-Hub-Signature-256': 'sha256=invalid'})

        self.assertEqual(response.status_code, 403)

    @patch('main.brain')
    def test_pubsub_bypass(self, mock_brain):
        """
        Test that Pub/Sub messages bypass verification.
        """
        sys.modules['config'].APP_SECRET = "test_secret"
        # Pub/Sub payload structure
        # Base64 for {"msg": {"id": "foo", "type": "text", "text": {"body": "hi"}}, "phone": "123"}
        # We need a valid msg structure so _process_message_logic doesn't crash or return 400 from inside logic?
        # Actually _process_message_logic catches exceptions and logs them, main returns 200 if logic called.

        inner_json = json.dumps({"msg": {"id": "foo", "type": "text", "text": {"body": "hi"}}, "phone": "123"})
        import base64
        b64_data = base64.b64encode(inner_json.encode('utf-8')).decode('utf-8')

        payload = {
            "message": {
                "data": b64_data,
                "messageId": "123"
            },
            "subscription": "projects/..."
        }

        response = self.app.post('/webhook',
                                 data=json.dumps(payload),
                                 content_type='application/json')

        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
