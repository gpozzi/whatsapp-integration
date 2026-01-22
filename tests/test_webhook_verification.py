import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add root directory to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
import config

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        self.app = main.app.test_client()
        self.app.testing = True

    def test_valid_token(self):
        with patch('config.VERIFY_TOKEN', 'my-secret-token'):
            response = self.app.get('/webhook', query_string={
                'hub.verify_token': 'my-secret-token',
                'hub.challenge': '12345'
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data.decode(), '12345')

    def test_invalid_token(self):
        with patch('config.VERIFY_TOKEN', 'my-secret-token'):
            response = self.app.get('/webhook', query_string={
                'hub.verify_token': 'wrong-token',
                'hub.challenge': '12345'
            })
            self.assertEqual(response.status_code, 403)

    def test_none_config_bypass(self):
        """
        Demonstrates the vulnerability: if config.VERIFY_TOKEN is None,
        and request sends no token, it matches (None == None).
        """
        # We patch config.VERIFY_TOKEN to be None
        with patch('config.VERIFY_TOKEN', None):
            # We send a request with NO verify_token
            response = self.app.get('/webhook', query_string={
                'hub.challenge': '12345'
            })
            # It should now return 403 because we fixed the vulnerability
            self.assertEqual(response.status_code, 403)

if __name__ == '__main__':
    unittest.main()
