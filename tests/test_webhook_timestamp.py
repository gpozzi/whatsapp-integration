
import unittest
from unittest.mock import MagicMock, patch
import sys
import time
import json
import os
import importlib

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules
mock_ff = MagicMock()
mock_ff.http.side_effect = lambda f: f
sys.modules['functions_framework'] = mock_ff

# CAUTION: We should not mock 'requests' entire package if libraries need it.
# Instead of mocking requests, we can patch it inside the test methods if needed.
# But main.py imports requests.
# If we mock sys.modules['requests'], it breaks other libs like requests_toolbelt.
# So we remove: sys.modules['requests'] = MagicMock()

sys.modules['config'] = MagicMock()
sys.modules['config'].PHONE_NUMBER_ID = "123"
sys.modules['config'].WHATSAPP_TOKEN = "abc"
sys.modules['config'].VERIFY_TOKEN = "verify"
sys.modules['config'].PUBSUB_TOPIC = "projects/my-project/topics/my-topic"
sys.modules['config'].logger = MagicMock()

# Mock PubSub
mock_pubsub = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = mock_pubsub

# Mock heavy deps
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()

import main

class TestMainTimestamp(unittest.TestCase):
    def setUp(self):
        # Reload main to ensure it uses the mocked configuration
        importlib.reload(main)

        # Force publisher to be a fresh MagicMock to ensure isolation between tests
        main.publisher = MagicMock()

        # Mock brain inside main instance
        main.brain = MagicMock()

    def test_old_message_ignored(self):
        # Setup
        mock_req = MagicMock()
        mock_req.method = "POST"

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
        mock_req.get_json.return_value = payload

        # Act
        with main.app.test_request_context(method="POST", json=payload):
            response = main.whatsapp_webhook()

        # Assert
        # Should return "OK", 200 (to stop retries)
        self.assertEqual(response, ("OK", 200))

        # Should NOT call publisher.publish
        if main.publisher:
            main.publisher.publish.assert_not_called()

    def test_new_message_processed(self):
        # Setup
        mock_req = MagicMock()
        mock_req.method = "POST"

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
        mock_req.get_json.return_value = payload

        # Mock publisher future result
        if main.publisher:
            future_mock = MagicMock()
            main.publisher.publish.return_value = future_mock
            future_mock.result.return_value = "msg_id"

        # Act
        with main.app.test_request_context(method="POST", json=payload):
            response = main.whatsapp_webhook()

        # Assert
        self.assertEqual(response, ("OK", 200))

        # Verify publish was called
        if main.publisher:
             main.publisher.publish.assert_called()
        else:
            self.fail("Publisher should be initialized")

if __name__ == '__main__':
    unittest.main()
