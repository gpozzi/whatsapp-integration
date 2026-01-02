
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
sys.modules['requests'] = MagicMock()
# DO NOT mock 'brain' here globally, as it breaks other tests that need real brain module.
# sys.modules['brain'] = MagicMock()

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

# Import main (will use real brain if available, or fail if deps missing)
# To avoid failure if real brain deps are missing/mocked inconsistently,
# we might need to mock brain's deps or mock brain in sys.modules TEMPORARILY.
# But simpler: assume dependencies are mocked enough or present.
# Since we mock google.cloud, brain import might succeed if it only imports that.
# brain imports pandas, langchain, etc.
# We should mock those too if we want to import main safely without real env.

sys.modules['pandas'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()
sys.modules['langchain_experimental.tools.python.tool'] = MagicMock()
sys.modules['langchain_core'] = MagicMock()
sys.modules['langchain_core.messages'] = MagicMock()
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
        response = main.whatsapp_webhook(mock_req)

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
        response = main.whatsapp_webhook(mock_req)

        # Assert
        self.assertEqual(response, ("OK", 200))

        # Verify publish was called
        if main.publisher:
             main.publisher.publish.assert_called()
        else:
            self.fail("Publisher should be initialized")

if __name__ == '__main__':
    unittest.main()
