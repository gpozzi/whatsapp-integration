
import unittest
from unittest.mock import MagicMock, patch
import sys
import time
import json
import os

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock brain ONLY to isolate main logic and avoid brain's complex deps
sys.modules['brain'] = MagicMock()
sys.modules['config'] = MagicMock()
sys.modules['config'].PHONE_NUMBER_ID = "123"
sys.modules['config'].WHATSAPP_TOKEN = "abc"
sys.modules['config'].VERIFY_TOKEN = "verify"
sys.modules['config'].logger = MagicMock()

import main

class TestMainTimestamp(unittest.TestCase):
    def setUp(self):
        main.brain.reset_mock()

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

        # Should NOT call brain.process_message
        main.brain.process_message.assert_not_called()

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

        # Mock brain response
        main.brain.process_message.return_value = "Response"

        # Mock requests
        with patch('main.requests.post') as mock_post:
             mock_post.return_value.status_code = 200

             # Act
             response = main.whatsapp_webhook(mock_req)

             # Assert
             self.assertEqual(response, ("OK", 200))
             main.brain.process_message.assert_called()

if __name__ == '__main__':
    unittest.main()
