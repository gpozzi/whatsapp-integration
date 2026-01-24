import unittest
import sys
from unittest.mock import patch, MagicMock

# --- MOCK HEAVY DEPENDENCIES BEFORE IMPORTS ---
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
sys.modules['functions_framework'] = MagicMock()
sys.modules['functions_framework'].http = lambda f: f

import main

class TestWebhookVerification(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    @patch('main.config')
    def test_verify_token_success(self, mock_config):
        mock_config.VERIFY_TOKEN = "correct_token"
        response = self.client.get('/webhook?hub.verify_token=correct_token&hub.challenge=123')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode(), "123")

    @patch('main.config')
    def test_verify_token_fail(self, mock_config):
        mock_config.VERIFY_TOKEN = "correct_token"
        response = self.client.get('/webhook?hub.verify_token=wrong_token&hub.challenge=123')
        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_verify_token_config_none(self, mock_config):
        """
        CRITICAL SECURITY TEST:
        If config.VERIFY_TOKEN is missing (None), the system MUST NOT allow access.
        Old behavior: None == None -> True (Vulnerable)
        New behavior: Should fail secure (403).
        """
        mock_config.VERIFY_TOKEN = None

        # Scenario: Attacker sends no token.
        # request.args.get('hub.verify_token') is None.
        # config.VERIFY_TOKEN is None.
        response = self.client.get('/webhook?hub.challenge=123')

        self.assertEqual(response.status_code, 403, "VULNERABILITY: Config bypass enabled if VERIFY_TOKEN is None")

    @patch('main.config')
    def test_verify_token_request_none(self, mock_config):
        mock_config.VERIFY_TOKEN = "correct_token"
        # Attacker sends no token
        response = self.client.get('/webhook?hub.challenge=123')
        self.assertEqual(response.status_code, 403)

if __name__ == '__main__':
    unittest.main()
