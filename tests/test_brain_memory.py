import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# --- MOCK DEPENDENCIES BEFORE IMPORTING BRAIN ---
sys.modules['pandas'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['langchain_google_vertexai'] = MagicMock()
sys.modules['langchain_experimental'] = MagicMock()
sys.modules['langchain_experimental.agents'] = MagicMock()

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import brain

class TestBrainMemory(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        brain._db_client = self.mock_db

    def test_manage_history_limit_and_hygiene(self):
        # Setup mock doc
        mock_doc_ref = MagicMock()
        self.mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Create a history with:
        # 1. Technical errors (to be filtered)
        # 2. Old messages (to be cut off by limit)
        # 3. Valid recent messages

        # Let's say limit is 4000 chars.
        # We create messages to test boundary.

        msg_1k = "A" * 1000

        messages = [
            f"Usuario: Oldest {msg_1k}", # Should be cut (idx 0)
            "Bot: Error processing request", # Should be filtered (idx 1)
            f"Usuario: Middle1 {msg_1k}", # (idx 2)
            "Bot: Agent stopped due to iteration limit", # Should be filtered (idx 3)
            f"Bot: Middle2 {msg_1k}", # (idx 4)
            f"Usuario: Recent1 {msg_1k}", # (idx 5)
            f"Bot: Recent2 {msg_1k}", # Most recent (idx 6)
        ]

        # Mock get()
        mock_doc_snapshot = MagicMock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = {"mensajes": messages}
        mock_doc_ref.get.return_value = mock_doc_snapshot

        # Call _manage_history (read only mode)
        history_str = brain._manage_history("123456789")

        print(f"DEBUG: History length: {len(history_str)}")

        # Assertions
        self.assertNotIn("Error processing", history_str, "Should filter technical errors")
        self.assertNotIn("Agent stopped", history_str, "Should filter technical errors")

        # Check limit (approx 4000)
        self.assertLessEqual(len(history_str), 4200, "Should respect character limit")

        # Check content
        self.assertIn("Recent2", history_str, "Should contain recent messages")
        self.assertIn("Recent1", history_str, "Should contain recent messages")
        self.assertIn("Middle2", history_str, "Should contain middle messages")

        # "Oldest" is at index 0.
        # Valid messages: Middle1 (1000+), Middle2 (1000+), Recent1 (1000+), Recent2 (1000+).
        # Total valid chars > 4000.
        # The loop traverses backwards:
        # 1. Recent2 (adds ~1000) -> total 1000
        # 2. Recent1 (adds ~1000) -> total 2000
        # 3. Middle2 (adds ~1000) -> total 3000
        # 4. Middle1 (adds ~1000) -> total 4000
        # Next would be Oldest. It should be skipped or break the loop.
        # Wait, if limit is 4000, adding Middle1 might make it exactly 4000 or slightly over if we check before adding.
        # Logic: if current_chars + msg_len > LIMIT: break.
        # So if we are at 3000, and next is 1000, it fits.
        # If we are at 4000, and next is Oldest (1000), it breaks.
        # So Middle1 might be included. Oldest definitely not.

        self.assertNotIn("Oldest", history_str, "Should truncate old messages")

if __name__ == '__main__':
    unittest.main()
