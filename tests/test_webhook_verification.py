import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import importlib

# Mock dependencies to avoid import errors
sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()

import main
import config

class TestWebhookVerification(unittest.TestCase):

    def setUp(self):
        # Ensure we have a clean state by reloading config and main
        # This fixes issues where other tests (like test_webhook_timestamp)
        # mock config globally in sys.modules

        # If config in sys.modules is a Mock, remove it so we can import the real one
        if 'config' in sys.modules and isinstance(sys.modules['config'], MagicMock):
            del sys.modules['config']

        # Re-import config to get the real module
        global config
        import config
        importlib.reload(config)

        # Reload main to use the real config
        importlib.reload(main)

        self.app = main.app.test_client()
        self.app.testing = True

    def test_verify_token_success(self):
        """Test that correct token returns challenge."""
        # Now main.config and config are the same, so we can patch config
        with patch.object(config, 'VERIFY_TOKEN', 'correct_token'):
            response = self.app.get('/webhook', query_string={
                'hub.verify_token': 'correct_token',
                'hub.challenge': 'challenge_123'
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data.decode(), 'challenge_123')

    def test_verify_token_failure(self):
        """Test that incorrect token returns 403."""
        with patch.object(config, 'VERIFY_TOKEN', 'correct_token'):
            response = self.app.get('/webhook', query_string={
                'hub.verify_token': 'wrong_token',
                'hub.challenge': 'challenge_123'
            })
            self.assertEqual(response.status_code, 403)

    def test_verify_token_missing_config(self):
        """Test that if config.VERIFY_TOKEN is None, access is denied."""
        with patch.object(config, 'VERIFY_TOKEN', None):
            # Case A: Attacker sends nothing
            response = self.app.get('/webhook', query_string={
                'hub.challenge': 'challenge_123'
            })
            self.assertEqual(response.status_code, 403)

    def test_verify_token_none_vs_none_bypass(self):
        """Specific test for the None == None vulnerability."""
        with patch.object(config, 'VERIFY_TOKEN', None):
            response = self.app.get('/webhook', query_string={
                'hub.challenge': 'I_AM_IN'
            })
            self.assertEqual(response.status_code, 403, "Should fail even if both are None")

if __name__ == '__main__':
    unittest.main()
