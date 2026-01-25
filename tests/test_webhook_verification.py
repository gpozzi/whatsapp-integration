import unittest
import sys
from unittest.mock import patch, MagicMock
import secrets

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

# Mock publisher client in main
with patch('google.cloud.pubsub_v1.PublisherClient'):
    import main

class TestWebhookVerification(unittest.TestCase):

    def setUp(self):
        self.app = main.app.test_client()
        self.app.testing = True

    @patch('main.config')
    @patch('secrets.compare_digest')
    def test_verify_token_success(self, mock_compare, mock_config):
        """Test successful verification."""
        mock_config.VERIFY_TOKEN = "valid_token"
        # Since we haven't implemented secrets.compare_digest yet, this mock might not be called in the fail state,
        # but once fixed it should be. For now, let's simulate the CURRENT behavior which is direct comparison.
        # Wait, I want to verify the fix uses secrets.compare_digest.

        # If I mock secrets.compare_digest, the real function won't be called.
        # But currently the code doesn't call it.
        # So I will test that it IS called.

        mock_compare.return_value = True

        response = self.app.get('/webhook', query_string={
            "hub.verify_token": "valid_token",
            "hub.challenge": "12345"
        })

        # If the code hasn't been fixed, this will pass purely on string equality if I don't mock it?
        # No, currently the code does `if token == config.VERIFY_TOKEN`.
        # So mocks on secrets.compare_digest won't affect current code.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode(), "12345")

    @patch('main.config')
    def test_verify_token_failure(self, mock_config):
        """Test failure with wrong token."""
        mock_config.VERIFY_TOKEN = "valid_token"

        response = self.app.get('/webhook', query_string={
            "hub.verify_token": "wrong_token",
            "hub.challenge": "12345"
        })

        self.assertEqual(response.status_code, 403)

    @patch('main.config')
    def test_verify_token_none_bypass_attempt(self, mock_config):
        """
        CRITICAL: Test that if config.VERIFY_TOKEN is None (misconfigured),
        an attacker cannot bypass auth by sending no token.

        Current behavior prediction:
        If VERIFY_TOKEN is None, and hub.verify_token is missing (None).
        None == None is True.
        So this should return 200 (VULNERABLE).
        """
        mock_config.VERIFY_TOKEN = None

        # Attacker sends no token
        response = self.app.get('/webhook', query_string={
            "hub.challenge": "12345"
        })

        # We WANT 403. If we get 200, it's vulnerable.
        # I will assert 403 to demonstrate failure.
        self.assertEqual(response.status_code, 403, "Vulnerability: None == None bypass allowed!")

    @patch('main.config')
    @patch('secrets.compare_digest')
    def test_uses_constant_time_comparison(self, mock_compare, mock_config):
        """Test that secrets.compare_digest is actually used."""
        mock_config.VERIFY_TOKEN = "valid_token"
        mock_compare.return_value = True

        self.app.get('/webhook', query_string={
            "hub.verify_token": "valid_token",
            "hub.challenge": "12345"
        })

        mock_compare.assert_called_once()
