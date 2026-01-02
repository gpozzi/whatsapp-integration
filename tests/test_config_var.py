import unittest
import config

class TestConfig(unittest.TestCase):
    def test_pubsub_topic_exists(self):
        """Test that PUBSUB_TOPIC attribute exists in config module."""
        self.assertTrue(hasattr(config, 'PUBSUB_TOPIC'), "config module missing PUBSUB_TOPIC attribute")

if __name__ == '__main__':
    unittest.main()
