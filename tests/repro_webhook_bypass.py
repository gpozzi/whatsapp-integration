import unittest
from unittest.mock import patch, MagicMock
import main
import config

class TestWebhookSecurity(unittest.TestCase):
    def setUp(self):
        self.app = main.app.test_client()
        self.app.testing = True

    def test_bypass_when_token_is_missing(self):
        """
        Verify that if config.VERIFY_TOKEN is None (env var missing),
        an attacker CANNOT verify the webhook.
        """
        # Patch config.VERIFY_TOKEN to be None
        with patch.object(config, 'VERIFY_TOKEN', None):
            # Send GET request with NO hub.verify_token
            response = self.app.get('/webhook?hub.challenge=123')

            # Secure behavior: Should return 403 Forbidden
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.data.decode(), 'Forbidden')

    def test_timing_attack_prevention(self):
        """
        Verify that secrets.compare_digest IS used.
        """
        with patch('secrets.compare_digest', return_value=True) as mock_compare:
             with patch.object(config, 'VERIFY_TOKEN', 'secret123'):
                self.app.get('/webhook?hub.verify_token=secret123&hub.challenge=123')
                # Now it should be called
                mock_compare.assert_called_once()

if __name__ == '__main__':
    unittest.main()
