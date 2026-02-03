import unittest
from unittest.mock import MagicMock, patch, ANY
import sys
import concurrent.futures
import importlib

class TestAsyncBrain(unittest.TestCase):
    def setUp(self):
        self._original_modules = sys.modules.copy()

        # Mock dependencies BEFORE importing/reloading brain
        # We need to mock 'config' carefully because other tests might need the real one.
        # But for this test, we want to mock it to avoid side effects.
        # Since we restore sys.modules in tearDown, this is safe for subsequent tests.

        self.mock_config = MagicMock()
        sys.modules["config"] = self.mock_config

        sys.modules["google"] = MagicMock()
        sys.modules["google.cloud"] = MagicMock()
        sys.modules["google.cloud.firestore"] = MagicMock()
        sys.modules["google.auth"] = MagicMock()
        sys.modules["google.cloud.texttospeech"] = MagicMock()
        sys.modules["langchain_google_vertexai"] = MagicMock()
        sys.modules["langchain_core"] = MagicMock()
        sys.modules["langchain_core.messages"] = MagicMock()

        # Import brain (or get it if already imported)
        import brain
        # Force reload to pick up mocked dependencies
        importlib.reload(brain)
        self.brain = brain

        # Reset services
        self.brain._db_client = MagicMock()
        self.brain._safety_model = MagicMock()
        self.brain._embeddings_service = MagicMock()

        # Mock specific internal methods we want to track
        self.mock_history = patch("brain._manage_history").start()
        self.mock_search = patch("brain._search_cars").start()
        self.mock_intent = patch("brain._analyze_tone_and_intent").start()
        self.mock_image = patch("brain._analyze_image").start()
        self.mock_audit = patch("brain._audit_response").start()
        self.mock_check_duplicate = patch("brain._check_is_duplicate").start()
        self.mock_init = patch("brain._init_services").start()

        # Setup default returns
        self.mock_check_duplicate.return_value = False
        self.mock_history.return_value = "Mock History"
        self.mock_search.return_value = "Mock Inventory"
        self.mock_intent.return_value = {"intent": "SALES_QUERY", "style_instruction": "Normal"}
        self.mock_image.return_value = "Image Description"
        self.mock_audit.return_value = True

        # Mock LLM response
        self.mock_llm = MagicMock()
        self.mock_llm.invoke.return_value.content = "Final Answer"
        self.mock_init.return_value = self.mock_llm

    def tearDown(self):
        patch.stopall()
        # Restore sys.modules to prevent pollution
        # We must update the existing dictionary object, not replace the reference
        sys.modules.clear()
        sys.modules.update(self._original_modules)

        # Reload brain again to restore it to original state (using real dependencies if they were real)
        # We wrap this in try-except in case brain or dependencies are broken
        try:
            import brain
            importlib.reload(brain)
        except ImportError:
            pass

    def test_optimistic_search_no_image(self):
        """Test that search starts immediately if no image is present."""

        # Synchronous Mock Executor
        class SynchronousExecutor:
            def submit(self, fn, *args, **kwargs):
                future = concurrent.futures.Future()
                try:
                    result = fn(*args, **kwargs)
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
                return future

        # Patch the global executor in brain
        with patch("brain._executor", new=SynchronousExecutor()):
            result = self.brain.process_message("I want a red car", "123")

        # Assertions
        self.assertEqual(result, "Final Answer")

        # Verify call order/presence
        # Should be called twice: once for read, once for write
        self.assertEqual(self.mock_history.call_count, 2)

        # Verify first call was read-only (parallel)
        self.mock_history.assert_any_call("123")

        self.mock_search.assert_called_with("I want a red car")
        self.mock_intent.assert_called_once()

        # Verify Intent called with History (result of _manage_history)
        self.mock_intent.assert_called_with("I want a red car", "Mock History")

    def test_search_waits_for_image(self):
        """Test that search waits for image analysis if image is present."""

        class SynchronousExecutor:
            def submit(self, fn, *args, **kwargs):
                future = concurrent.futures.Future()
                result = fn(*args, **kwargs)
                future.set_result(result)
                return future

        image_data = b"fake_image_bytes"

        with patch("brain._executor", new=SynchronousExecutor()):
            result = self.brain.process_message("Look at this car", "123", image_data=image_data)

        self.assertEqual(result, "Final Answer")

        # Verify Image Analysis called
        self.mock_image.assert_called_once()

        # Verify Search called with enriched query
        expected_query = "Look at this car \n[INFO IMAGEN: El usuario envió una foto. Análisis: Image Description]"
        self.mock_search.assert_called_with(expected_query)

if __name__ == "__main__":
    unittest.main()
