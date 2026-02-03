import unittest
from unittest.mock import MagicMock, patch, ANY
import sys
import json
import base64
import importlib

class TestAudioFeatures(unittest.TestCase):

    def setUp(self):
        self._original_modules = sys.modules.copy()

        # --- MOCKING STRATEGY ---
        # Mock dependencies in sys.modules
        mock_firestore = MagicMock()
        mock_texttospeech = MagicMock()
        mock_vertexai = MagicMock()
        mock_google_auth = MagicMock()
        mock_discovery = MagicMock()

        sys.modules["google"] = MagicMock()
        sys.modules["google.cloud"] = MagicMock()
        sys.modules["google.cloud.firestore"] = mock_firestore
        sys.modules["google.cloud.texttospeech"] = mock_texttospeech
        sys.modules["langchain_google_vertexai"] = mock_vertexai
        sys.modules["google.auth"] = mock_google_auth
        sys.modules["googleapiclient.discovery"] = mock_discovery
        sys.modules["langchain_core"] = MagicMock()
        sys.modules["langchain_core.messages"] = MagicMock()

        # Import and reload brain
        import brain
        import config
        importlib.reload(brain)
        self.brain = brain
        self.config = config

        # Set mocked clients
        self.brain._db_client = MagicMock()
        self.brain._safety_model = MagicMock()

        # We need to ensure dependencies used inside brain are consistent with our mocks
        # If brain does `from google.cloud import texttospeech`, it uses the mock we put in sys.modules

        # Mock config values using patch
        self.config_patcher = patch.multiple(config, TTS_VOICE_MALE="male-voice", TTS_VOICE_FEMALE="female-voice")
        self.config_patcher.start()

        def voice_params_side_effect(name=None, language_code=None):
            m = MagicMock()
            m.name = name
            return m

        # Depending on how brain imports, we might need to set side_effect on the module attribute
        if hasattr(self.brain, 'texttospeech'):
             self.brain.texttospeech.VoiceSelectionParams.side_effect = voice_params_side_effect

    def tearDown(self):
        self.config_patcher.stop()
        sys.modules.clear()
        sys.modules.update(self._original_modules)
        try:
            import brain
            importlib.reload(brain)
        except ImportError:
            pass

    def test_analyze_audio_male(self):
        # We patch HumanMessage dynamically on self.brain
        # But brain.HumanMessage is imported.

        mock_human_message = MagicMock()
        self.brain.HumanMessage = mock_human_message

        # Setup mock return from Gemini
        mock_response_content = '```json\n{"text": "Hola busco un auto", "gender": "MALE"}\n```'
        self.brain._safety_model.invoke.return_value.content = mock_response_content

        audio_bytes = b"fake_audio_bytes"
        result = self.brain._analyze_audio(audio_bytes)

        # Verify calls
        call_args = mock_human_message.call_args
        self.assertIsNotNone(call_args, "HumanMessage should have been instantiated")

        kwargs = call_args[1]
        content_list = kwargs.get('content')

        # If not passed as kwarg, check positional args
        if not content_list and call_args[0]:
            content_list = call_args[0][0]

        self.assertIsNotNone(content_list, "HumanMessage instantiated without content")
        self.assertEqual(len(content_list), 2)

        # Check content
        self.assertEqual(result["text"], "Hola busco un auto")
        self.assertEqual(result["gender"], "MALE")

    def test_text_to_speech_male(self):
        mock_client_instance = MagicMock()
        self.brain.texttospeech.TextToSpeechClient.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.audio_content = b"generated_mp3"
        mock_client_instance.synthesize_speech.return_value = mock_response

        result = self.brain._text_to_speech("Hola", "MALE")

        self.assertEqual(result, b"generated_mp3")
        _, kwargs = mock_client_instance.synthesize_speech.call_args
        self.assertEqual(kwargs['voice'].name, "male-voice")

    def test_text_to_speech_female(self):
        mock_client_instance = MagicMock()
        self.brain.texttospeech.TextToSpeechClient.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.audio_content = b"generated_mp3_female"
        mock_client_instance.synthesize_speech.return_value = mock_response

        result = self.brain._text_to_speech("Hola", "FEMALE")

        self.assertEqual(result, b"generated_mp3_female")
        _, kwargs = mock_client_instance.synthesize_speech.call_args
        self.assertEqual(kwargs['voice'].name, "female-voice")

    def test_process_message_audio_flow(self):
        # Setup
        original_analyze = self.brain._analyze_audio
        original_tts = self.brain._text_to_speech
        original_tone = self.brain._analyze_tone_and_intent
        original_audit = self.brain._audit_response
        original_search = self.brain._search_cars
        original_init = self.brain._init_services

        # Patch HumanMessage and ChatVertexAI on self.brain
        mock_human_message = MagicMock()
        self.brain.HumanMessage = mock_human_message

        mock_llm_constructor = MagicMock()
        self.brain.ChatVertexAI = mock_llm_constructor

        try:
            self.brain._analyze_audio = MagicMock(return_value={"text": "Quiero un Toyota", "gender": "MALE"})
            self.brain._text_to_speech = MagicMock(return_value=b"audio_response_bytes")
            self.brain._analyze_tone_and_intent = MagicMock(return_value={"intent": "SALES_QUERY", "style_instruction": "Normal"})
            self.brain._audit_response = MagicMock(return_value=True)
            self.brain._search_cars = MagicMock(return_value="Inventory Info")

            # Since we modify global executor in other tests, let's patch it here to be synchronous just in case
            # Actually, self.brain._executor IS the global executor.
            # We should patch it to be Synchronous to make this test simpler.

            import concurrent.futures
            class SynchronousExecutor:
                def submit(self, fn, *args, **kwargs):
                    future = concurrent.futures.Future()
                    try:
                        result = fn(*args, **kwargs)
                        future.set_result(result)
                    except Exception as e:
                        future.set_exception(e)
                    return future

            self.brain._executor = SynchronousExecutor()

            mock_llm_instance = MagicMock()
            mock_llm_instance.invoke.return_value.content = 'Tenemos un Toyota Corolla.'
            mock_llm_constructor.return_value = mock_llm_instance

            # Mock brain._init_services to return mock_llm_instance
            self.brain._init_services = MagicMock(return_value=mock_llm_instance)

            mock_doc_ref = MagicMock()
            mock_doc_ref.get.return_value.exists = False
            self.brain._db_client.collection.return_value.document.return_value = mock_doc_ref

            result = self.brain.process_message(
                user_text="",
                phone_number="123",
                message_id="msg_1",
                audio_data=b"raw_audio_input"
            )

            self.brain._analyze_audio.assert_called_once_with(b"raw_audio_input")
            self.brain._text_to_speech.assert_called_once()
            self.assertEqual(result, b"audio_response_bytes")

        finally:
            self.brain._analyze_audio = original_analyze
            self.brain._text_to_speech = original_tts
            self.brain._analyze_tone_and_intent = original_tone
            self.brain._audit_response = original_audit
            self.brain._search_cars = original_search
            self.brain._init_services = original_init

    def test_process_message_text_fallback(self):
        original_analyze = self.brain._analyze_audio
        original_tts = self.brain._text_to_speech
        original_tone = self.brain._analyze_tone_and_intent
        original_search = self.brain._search_cars
        original_init = self.brain._init_services

        mock_human_message = MagicMock()
        self.brain.HumanMessage = mock_human_message

        mock_llm_constructor = MagicMock()
        self.brain.ChatVertexAI = mock_llm_constructor

        try:
            self.brain._analyze_audio = MagicMock(return_value={"text": "Hola", "gender": "FEMALE"})
            self.brain._text_to_speech = MagicMock(return_value=None)
            self.brain._analyze_tone_and_intent = MagicMock(return_value={"intent": "SALES_QUERY", "style_instruction": "Normal"})
            self.brain._search_cars = MagicMock(return_value="Inventory Info")

            # Patch Executor
            import concurrent.futures
            class SynchronousExecutor:
                def submit(self, fn, *args, **kwargs):
                    future = concurrent.futures.Future()
                    try:
                        result = fn(*args, **kwargs)
                        future.set_result(result)
                    except Exception as e:
                        future.set_exception(e)
                    return future
            self.brain._executor = SynchronousExecutor()

            mock_llm_instance = MagicMock()
            mock_llm_instance.invoke.return_value.content = 'Respuesta texto fallback.'
            mock_llm_constructor.return_value = mock_llm_instance

            self.brain._init_services = MagicMock(return_value=mock_llm_instance)

            mock_doc_ref = MagicMock()
            mock_doc_ref.get.return_value.exists = False
            self.brain._db_client.collection.return_value.document.return_value = mock_doc_ref

            result = self.brain.process_message(
                user_text="",
                phone_number="123",
                audio_data=b"audio"
            )

            self.assertEqual(result, "Respuesta texto fallback.")

        finally:
            self.brain._analyze_audio = original_analyze
            self.brain._text_to_speech = original_tts
            self.brain._analyze_tone_and_intent = original_tone
            self.brain._search_cars = original_search
            self.brain._init_services = original_init

if __name__ == '__main__':
    unittest.main()
