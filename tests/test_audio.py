import unittest
from unittest.mock import MagicMock, patch, ANY
import sys
import json
import base64

# --- MOCKING STRATEGY ---
mock_firestore = MagicMock()
mock_texttospeech = MagicMock()
mock_vertexai = MagicMock()
mock_pandas = MagicMock()
mock_google_auth = MagicMock()
mock_discovery = MagicMock()
mock_langchain_core = MagicMock()
mock_langchain_experimental = MagicMock()

sys.modules["google"] = MagicMock()
sys.modules["google.cloud"] = MagicMock()
sys.modules["google.cloud.firestore"] = mock_firestore
sys.modules["google.cloud.texttospeech"] = mock_texttospeech
sys.modules["langchain_google_vertexai"] = mock_vertexai
sys.modules["google.auth"] = mock_google_auth
sys.modules["googleapiclient.discovery"] = mock_discovery
sys.modules["langchain_experimental.agents"] = mock_langchain_experimental

import brain
import config

class TestAudioFeatures(unittest.TestCase):

    def setUp(self):
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()
        # brain._sales_agent is removed, so we don't mock it here
        brain._df_inventory = MagicMock()
        brain._inventory_timestamp = brain.datetime.datetime.now(brain.datetime.timezone.utc)

        # Re-bind brain imports to current mocks (fix for discover stale mocks)
        brain.create_pandas_dataframe_agent = sys.modules["langchain_experimental.agents"].create_pandas_dataframe_agent
        brain.ChatVertexAI = sys.modules["langchain_google_vertexai"].ChatVertexAI
        brain.build = sys.modules["googleapiclient.discovery"].build
        brain.HumanMessage = sys.modules["langchain_core.messages"].HumanMessage

        # Mock config values using patch to avoid polluting global state
        self.config_patcher = patch.multiple(config, TTS_VOICE_MALE="male-voice", TTS_VOICE_FEMALE="female-voice")
        self.config_patcher.start()

        def voice_params_side_effect(name=None, language_code=None):
            m = MagicMock()
            m.name = name
            return m

        brain.texttospeech.VoiceSelectionParams.side_effect = voice_params_side_effect

    def test_analyze_audio_male(self):
        # Setup mock return from Gemini
        mock_response_content = '```json\n{"text": "Hola busco un auto", "gender": "MALE"}\n```'
        # Important: brain._safety_model is a mock, invoke returns a mock which has a content attribute.
        brain._safety_model.invoke.return_value.content = mock_response_content

        audio_bytes = b"fake_audio_bytes"
        result = brain._analyze_audio(audio_bytes)

        # Verify calls
        # Check that HumanMessage was initialized with correct content
        # Because HumanMessage is a Mock class, we check its constructor call args
        call_args = brain.HumanMessage.call_args
        self.assertIsNotNone(call_args, "HumanMessage should have been instantiated")

        kwargs = call_args[1]
        content_list = kwargs.get('content')

        # If not passed as kwarg, check positional args
        if not content_list and call_args[0]:
            content_list = call_args[0][0]

        self.assertIsNotNone(content_list, "HumanMessage instantiated without content")
        self.assertEqual(len(content_list), 2)

        text_part = content_list[0]
        file_part = content_list[1]

        self.assertEqual(text_part["type"], "text")
        self.assertEqual(file_part["type"], "media")
        self.assertEqual(file_part["mime_type"], "audio/ogg")
        # Ensure raw bytes are passed
        self.assertEqual(file_part["data"], audio_bytes)

        self.assertEqual(result["text"], "Hola busco un auto")
        self.assertEqual(result["gender"], "MALE")

    def test_text_to_speech_male(self):
        mock_client_instance = MagicMock()
        brain.texttospeech.TextToSpeechClient.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.audio_content = b"generated_mp3"
        mock_client_instance.synthesize_speech.return_value = mock_response

        result = brain._text_to_speech("Hola", "MALE")

        self.assertEqual(result, b"generated_mp3")
        _, kwargs = mock_client_instance.synthesize_speech.call_args
        self.assertEqual(kwargs['voice'].name, "male-voice")

    def test_text_to_speech_female(self):
        mock_client_instance = MagicMock()
        brain.texttospeech.TextToSpeechClient.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.audio_content = b"generated_mp3_female"
        mock_client_instance.synthesize_speech.return_value = mock_response

        result = brain._text_to_speech("Hola", "FEMALE")

        self.assertEqual(result, b"generated_mp3_female")
        _, kwargs = mock_client_instance.synthesize_speech.call_args
        self.assertEqual(kwargs['voice'].name, "female-voice")

    @patch('brain._get_sales_agent')
    def test_process_message_audio_flow(self, mock_get_agent):
        # We need to ensure that the mocked functions in `process_message` actually return what we expect.
        # Since we cannot easily patch internal calls when functions are in the same module without some effort,
        # let's mock the return values of the helper functions by replacing them temporarily in the module.

        original_analyze = brain._analyze_audio
        original_tts = brain._text_to_speech
        original_tone = brain._analyze_tone_and_intent
        original_audit = brain._audit_response

        try:
            brain._analyze_audio = MagicMock(return_value={"text": "Quiero un Toyota", "gender": "MALE"})
            brain._text_to_speech = MagicMock(return_value=b"audio_response_bytes")
            brain._analyze_tone_and_intent = MagicMock(return_value={"intent": "SALES_QUERY", "style_instruction": "Normal"})
            brain._audit_response = MagicMock(return_value=True)

            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {'output': 'Tenemos un Toyota Corolla.'}
            mock_get_agent.return_value = mock_agent

            mock_doc_ref = MagicMock()
            mock_doc_ref.get.return_value.exists = False
            brain._db_client.collection.return_value.document.return_value = mock_doc_ref

            result = brain.process_message(
                user_text="",
                phone_number="123",
                message_id="msg_1",
                audio_data=b"raw_audio_input"
            )

            brain._analyze_audio.assert_called_once_with(b"raw_audio_input")
            brain._text_to_speech.assert_called_once()
            self.assertEqual(result, b"audio_response_bytes")

        finally:
            brain._analyze_audio = original_analyze
            brain._text_to_speech = original_tts
            brain._analyze_tone_and_intent = original_tone
            brain._audit_response = original_audit

    @patch('brain._get_sales_agent')
    def test_process_message_text_fallback(self, mock_get_agent):
        original_analyze = brain._analyze_audio
        original_tts = brain._text_to_speech
        original_tone = brain._analyze_tone_and_intent

        try:
            brain._analyze_audio = MagicMock(return_value={"text": "Hola", "gender": "FEMALE"})
            brain._text_to_speech = MagicMock(return_value=None)
            brain._analyze_tone_and_intent = MagicMock(return_value={"intent": "SALES_QUERY", "style_instruction": "Normal"})

            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {'output': 'Respuesta texto fallback.'}
            mock_get_agent.return_value = mock_agent

            # Fallback configuration if patch fails (Mock the underlying call)
            mock_create = sys.modules["langchain_experimental.agents"].create_pandas_dataframe_agent
            mock_create.return_value = mock_agent

            mock_doc_ref = MagicMock()
            mock_doc_ref.get.return_value.exists = False
            brain._db_client.collection.return_value.document.return_value = mock_doc_ref

            result = brain.process_message(
                user_text="",
                phone_number="123",
                audio_data=b"audio"
            )

            self.assertEqual(result, "Respuesta texto fallback.")

        finally:
            brain._analyze_audio = original_analyze
            brain._text_to_speech = original_tts
            brain._analyze_tone_and_intent = original_tone

    def tearDown(self):
        self.config_patcher.stop()

if __name__ == '__main__':
    unittest.main()
