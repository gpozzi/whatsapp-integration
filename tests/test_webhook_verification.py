
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import importlib

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules
sys.modules['functions_framework'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()

# Mock config
sys.modules['config'] = MagicMock()
sys.modules['config'].logger = MagicMock()

import main

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        importlib.reload(main)
        self.client = main.app.test_client()

    def test_verification_success(self):
        """Test successful webhook verification."""
        main.config.VERIFY_TOKEN = "correct-token"
        response = self.client.get('/webhook?hub.verify_token=correct-token&hub.challenge=123')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode('utf-8'), "123")

    def test_verification_failure_incorrect_token(self):
        """Test webhook verification failure with incorrect token."""
        main.config.VERIFY_TOKEN = "correct-token"
        response = self.client.get('/webhook?hub.verify_token=wrong-token&hub.challenge=123')
        self.assertEqual(response.status_code, 403)

    def test_verification_vulnerability_none_config(self):
        """
        Test the configuration bypass vulnerability.
        If config.VERIFY_TOKEN is None and request sends no token,
        request.args.get() returns None. None == None is True.
        """
        main.config.VERIFY_TOKEN = None
        # No hub.verify_token in query params
        response = self.client.get('/webhook?hub.challenge=123')

        # Currently, this returns 200 (VULNERABILITY)
        # We assert what we EXPECT to happen when fixed (403), or what currently happens to demonstrate failure.
        # Since I am creating a reproduction test, I expect this to PASS if I assert 200, proving the bug.
        # But to be clean, I will assert 403 and expect the test to FAIL.
        self.assertEqual(response.status_code, 403, "Vulnerability exposed: None == None bypassed verification")

    @patch('secrets.compare_digest')
    def test_constant_time_comparison(self, mock_compare):
        """Test that secrets.compare_digest is used (Timing Attack prevention)."""
        # Note: main.py currently does NOT import secrets, so this test might fail or error out
        # if I try to patch secrets.compare_digest on a module that doesn't import it?
        # Actually I'm patching 'secrets.compare_digest' globally.
        # But main.py needs to import it.

        main.config.VERIFY_TOKEN = "token"
        mock_compare.return_value = True

        # Since main.py doesn't use it yet, this test will fail to see the call.
        response = self.client.get('/webhook?hub.verify_token=token&hub.challenge=123')

        mock_compare.assert_called()

if __name__ == '__main__':
    unittest.main()
