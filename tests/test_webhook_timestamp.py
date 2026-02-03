
import unittest
from unittest.mock import MagicMock, patch
import sys
import time
import json
import os
import importlib

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestMainTimestamp(unittest.TestCase):
    def setUp(self):
        self._original_modules = sys.modules.copy()

        # Mock modules
        sys.modules['functions_framework'] = MagicMock()

        # Mock config
        mock_config = MagicMock()
        mock_config.PHONE_NUMBER_ID = "123"
        mock_config.WHATSAPP_TOKEN = "abc"
        mock_config.VERIFY_TOKEN = "verify"
        mock_config.PUBSUB_TOPIC = "projects/my-project/topics/my-topic"
        mock_config.logger = MagicMock()
        sys.modules['config'] = mock_config

        # Mock PubSub
        mock_pubsub = MagicMock()
        sys.modules['google.cloud'] = MagicMock()
        sys.modules['google.cloud.pubsub_v1'] = mock_pubsub

        # Mock heavy deps
        sys.modules['langchain_google_vertexai'] = MagicMock()
        sys.modules['google.auth'] = MagicMock()
        sys.modules['googleapiclient'] = MagicMock()
        sys.modules['googleapiclient.discovery'] = MagicMock()

        # Now import main
        import main
        importlib.reload(main)
        self.main = main

        # Force publisher to be a fresh MagicMock to ensure isolation between tests
        self.main.publisher = MagicMock()

        # Mock brain inside main instance
        self.main.brain = MagicMock()

        # Setup Flask test client
        self.client = self.main.app.test_client()

    def tearDown(self):
        # Restore sys.modules
        sys.modules.clear()
        sys.modules.update(self._original_modules)

        # Reload main
        try:
            import main
            importlib.reload(main)
        except ImportError:
            pass

    def test_old_message_ignored(self):
        # Setup
        # 20 minutes ago
        old_ts = int(time.time()) - 1200

        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "12345",
                            "id": "wamid.HBgL...",
                            "timestamp": str(old_ts),
                            "type": "text",
                            "text": {"body": "Old message"}
                        }]
                    }
                }]
            }]
        }

        # Act
        response = self.client.post('/webhook', json=payload)

        # Assert
        # Should return "OK", 200 (to stop retries)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode('utf-8'), "OK")

        # Should NOT call publisher.publish
        if self.main.publisher:
            self.main.publisher.publish.assert_not_called()

    def test_new_message_processed(self):
        # Setup
        # 1 minute ago
        recent_ts = int(time.time()) - 60

        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "12345",
                            "id": "wamid.HBgL...",
                            "timestamp": str(recent_ts),
                            "type": "text",
                            "text": {"body": "Recent message"}
                        }]
                    }
                }]
            }]
        }

        # Mock publisher future result
        if self.main.publisher:
            future_mock = MagicMock()
            self.main.publisher.publish.return_value = future_mock
            future_mock.result.return_value = "msg_id"

        # Act
        response = self.client.post('/webhook', json=payload)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode('utf-8'), "OK")

        # Verify publish was called
        if self.main.publisher:
             self.main.publisher.publish.assert_called()
        else:
            self.fail("Publisher should be initialized")

if __name__ == '__main__':
    unittest.main()
