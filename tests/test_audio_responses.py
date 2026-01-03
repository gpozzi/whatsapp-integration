import unittest
from unittest.mock import MagicMock, patch, ANY
import sys

# --- MOCKING STRATEGY ---
mock_firestore = MagicMock()
mock_texttospeech = MagicMock()
mock_vertexai = MagicMock()
mock_pandas = MagicMock()
mock_google_auth = MagicMock()
mock_discovery = MagicMock()

sys.modules["google"] = MagicMock()
sys.modules["google.cloud"] = MagicMock()
sys.modules["google.cloud.firestore"] = mock_firestore
sys.modules["google.cloud.texttospeech"] = mock_texttospeech
sys.modules["langchain_google_vertexai"] = mock_vertexai
sys.modules["google.auth"] = mock_google_auth
sys.modules["googleapiclient.discovery"] = mock_discovery

import brain
import config
import importlib

class TestAudioResponses(unittest.TestCase):

    def setUp(self):
        brain._db_client = MagicMock()
        brain._safety_model = MagicMock()
        brain._df_inventory = MagicMock()
        brain._inventory_timestamp = brain.datetime.datetime.now(brain.datetime.timezone.utc)

    def test_config_values(self):
        self.assertEqual(config.TTS_VOICE_FEMALE, "es-US-Neural2-C", "Female voice should be Neural2-C")

    @patch('brain._get_sales_agent')
    def test_audio_input_female_response(self, mock_get_agent):
        """Test that if the user is FEMALE, the bot responds with AUDIO (bytes)."""

        original_analyze = brain._analyze_audio
        original_tts = brain._text_to_speech
        original_tone = brain._analyze_tone_and_intent
        original_audit = brain._audit_response

        try:
            # 1. Simulate Audio Input + Gender Detection = FEMALE
            brain._analyze_audio = MagicMock(return_value={"text": "Hola, soy mujer", "gender": "FEMALE"})

            # 2. Simulate TTS working returning bytes
            brain._text_to_speech = MagicMock(return_value=b"female_audio_bytes")

            # 3. Normal flow mocks
            brain._analyze_tone_and_intent = MagicMock(return_value={"intent": "SALES_QUERY", "style_instruction": "Normal"})
            brain._audit_response = MagicMock(return_value=True)

            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {'output': 'Respuesta texto.'}
            mock_get_agent.return_value = mock_agent

            mock_doc_ref = MagicMock()
            mock_doc_ref.get.return_value.exists = False
            brain._db_client.collection.return_value.document.return_value = mock_doc_ref

            result = brain.process_message(
                user_text="",
                phone_number="123",
                message_id="msg_female_audio",
                audio_data=b"audio_input"
            )

            # EXPECT: AUDIO (bytes) because gender is FEMALE and audio_data is present
            self.assertIsInstance(result, bytes, "Expected audio bytes for female user")
            self.assertEqual(result, b"female_audio_bytes")

            # Ensure TTS WAS called with FEMALE
            brain._text_to_speech.assert_called_with('Respuesta texto.', 'FEMALE')

        finally:
            brain._analyze_audio = original_analyze
            brain._text_to_speech = original_tts
            brain._analyze_tone_and_intent = original_tone
            brain._audit_response = original_audit

    @patch('brain._get_sales_agent')
    def test_audio_input_male_response(self, mock_get_agent):
        """Test that if the user is MALE, the bot responds with AUDIO (bytes)."""

        original_analyze = brain._analyze_audio
        original_tts = brain._text_to_speech
        original_tone = brain._analyze_tone_and_intent
        original_audit = brain._audit_response

        try:
            # 1. Simulate Audio Input + Gender Detection = MALE
            brain._analyze_audio = MagicMock(return_value={"text": "Hola, soy hombre", "gender": "MALE"})

            # 2. Simulate TTS working returning bytes
            brain._text_to_speech = MagicMock(return_value=b"male_audio_bytes")

            # 3. Normal flow mocks
            brain._analyze_tone_and_intent = MagicMock(return_value={"intent": "SALES_QUERY", "style_instruction": "Normal"})
            brain._audit_response = MagicMock(return_value=True)

            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {'output': 'Respuesta texto.'}
            mock_get_agent.return_value = mock_agent

            mock_doc_ref = MagicMock()
            mock_doc_ref.get.return_value.exists = False
            brain._db_client.collection.return_value.document.return_value = mock_doc_ref

            result = brain.process_message(
                user_text="",
                phone_number="456",
                message_id="msg_male_audio",
                audio_data=b"audio_input"
            )

            # EXPECT: AUDIO (bytes)
            self.assertIsInstance(result, bytes, "Expected audio bytes for male user")
            self.assertEqual(result, b"male_audio_bytes")

            # Ensure TTS WAS called with MALE
            brain._text_to_speech.assert_called_with('Respuesta texto.', 'MALE')

        finally:
            brain._analyze_audio = original_analyze
            brain._text_to_speech = original_tts
            brain._analyze_tone_and_intent = original_tone
            brain._audit_response = original_audit

if __name__ == '__main__':
    unittest.main()
