import functions_framework
import requests
import time
import json
import base64
from google.cloud import pubsub_v1
import config
import brain

# Publisher Client (Global to reuse connection)
try:
    publisher = pubsub_v1.PublisherClient()
except Exception as e:
    config.logger.warning(f"Could not initialize PublisherClient (Local env?): {e}")
    publisher = None

# --- Helper Functions (Shared) ---

def send_whatsapp(phone, text):
    """Envío 'low-level' a la API de WhatsApp."""
    try:
        url = f"https://graph.facebook.com/v21.0/{config.PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "text": {"body": text}
        }
        # Security enhancement: Add timeout to prevent hanging
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        config.logger.error(f"Error enviando WhatsApp: {e}")

def mark_as_read(message_id):
    """Marca el mensaje como leído en WhatsApp."""
    try:
        url = f"https://graph.facebook.com/v21.0/{config.PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        config.logger.error(f"Error marcando mensaje como leído: {e}")

def get_media_url(media_id):
    """Obtiene la URL de descarga de un archivo multimedia de WhatsApp."""
    try:
        url = f"https://graph.facebook.com/v21.0/{media_id}"
        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_TOKEN}"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get('url')
    except Exception as e:
        config.logger.error(f"Error obteniendo URL de media {media_id}: {e}")
        return None

def download_media(media_url):
    """Descarga el contenido binario del archivo multimedia."""
    try:
        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_TOKEN}"
        }
        response = requests.get(media_url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.content
    except Exception as e:
        config.logger.error(f"Error descargando media: {e}")
        return None

def upload_media_to_whatsapp(media_bytes, mime_type):
    """Sube un archivo multimedia a WhatsApp y devuelve el ID."""
    try:
        url = f"https://graph.facebook.com/v21.0/{config.PHONE_NUMBER_ID}/media"
        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_TOKEN}"
        }
        files = {
            'file': ('audio.mp3', media_bytes, mime_type),
            'messaging_product': (None, 'whatsapp')
        }
        response = requests.post(url, headers=headers, files=files, timeout=30)
        response.raise_for_status()
        return response.json().get('id')
    except Exception as e:
        config.logger.error(f"Error subiendo media a WhatsApp: {e}")
        return None

def send_whatsapp_audio(phone, media_id):
    """Envía un mensaje de audio a WhatsApp."""
    try:
        url = f"https://graph.facebook.com/v21.0/{config.PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "audio",
            "audio": {"id": media_id}
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        config.logger.error(f"Error enviando Audio WhatsApp: {e}")


# --- WEBHOOK (Publisher) ---

@functions_framework.http
def whatsapp_webhook(request):
    """
    Entrada Síncrona: Valida el mensaje, lo pone en Pub/Sub y responde 200 OK.
    """
    # 1. Verificación (Handshake con Meta)
    if request.method == "GET":
        if request.args.get("hub.verify_token") == config.VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Forbidden", 403

    # 2. Recepción de Mensajes (POST)
    if request.method == "POST":
        try:
            data = request.get_json()
            entry = data.get('entry', [])[0]
            changes = entry.get('changes', [])[0]
            value = changes.get('value', {})
            
            if 'messages' in value:
                msg = value['messages'][0]
                phone = msg['from']
                message_id = msg.get('id')

                # Verificar antigüedad
                msg_ts = int(msg.get('timestamp', 0))
                now_ts = int(time.time())
                if now_ts - msg_ts > 300:
                    config.logger.warning(f"⏳ Mensaje descartado por antigüedad ({now_ts - msg_ts}s). ID: {message_id}")
                    return "OK", 200

                # Ack inmediato al usuario (Check azul)
                if message_id:
                    mark_as_read(message_id)

                # Publicar a Pub/Sub
                if config.PUBSUB_TOPIC and publisher:
                    payload_data = {
                        "msg": msg,
                        "phone": phone,
                        "timestamp": now_ts
                    }
                    data_str = json.dumps(payload_data)
                    data_bytes = data_str.encode("utf-8")

                    future = publisher.publish(config.PUBSUB_TOPIC, data_bytes)
                    future.result() # Esperar confirmación de publicación (rápido)
                    config.logger.info(f"Published message {message_id} to {config.PUBSUB_TOPIC}")
                else:
                    config.logger.error("PUBSUB_TOPIC not set or Publisher failed. Falling back to sync (not recommended).")
                    # Fallback (optional, mostly for dev/debug if no PubSub)
                    # _process_message_logic(msg, phone)
                    # Preferible fallar o loggear para forzar configuración correcta en prod.

            return "OK", 200

        except Exception as e:
            config.logger.error(f"Error en Webhook: {e}", exc_info=True)
            return "Error", 500


# --- WORKER (Subscriber) ---

@functions_framework.http
def whatsapp_worker(request):
    """
    Proceso Asíncrono: Recibe el Push de Pub/Sub y procesa el mensaje con Gemini.
    """
    if request.method != "POST":
        return "Method Not Allowed", 405

    try:
        envelope = request.get_json()
        if not envelope:
            msg = "no Pub/Sub message received"
            config.logger.error(f"error: {msg}")
            return f"Bad Request: {msg}", 400

        if not isinstance(envelope, dict) or "message" not in envelope:
            msg = "invalid Pub/Sub message format"
            config.logger.error(f"error: {msg}")
            return f"Bad Request: {msg}", 400

        pubsub_message = envelope["message"]

        if isinstance(pubsub_message, dict) and "data" in pubsub_message:
            # Decodificar datos
            data_str = base64.b64decode(pubsub_message["data"]).decode("utf-8")
            payload = json.loads(data_str)

            msg = payload.get("msg")
            phone = payload.get("phone")

            if msg and phone:
                _process_message_logic(msg, phone)
            else:
                config.logger.warning("Payload incompleto en Worker.")

        return "OK", 200

    except Exception as e:
        config.logger.error(f"Error en Worker: {e}", exc_info=True)
        return "Internal Server Error", 500


def _process_message_logic(msg, phone):
    """Lógica central de procesamiento (extraída para ser usada por el Worker)."""
    try:
        message_id = msg.get('id')

        # Extracción de texto y Multimedia
        text = ""
        image_data = None
        audio_data = None

        if msg['type'] == 'text':
            text = msg['text']['body']
        elif msg['type'] == 'interactive':
            text = msg['interactive']['button_reply']['title']
        elif msg['type'] == 'image':
            text = msg['image'].get('caption', "")
            media_id = msg['image']['id']
            media_url = get_media_url(media_id)
            if media_url:
                image_data = download_media(media_url)
        elif msg['type'] == 'audio':
            media_id = msg['audio']['id']
            media_url = get_media_url(media_id)
            if media_url:
                audio_data = download_media(media_url)
            if not audio_data:
                text = "[Audio no descargado]"
        else:
            text = "[Multimedia no soportado]"

        # Security check
        if text and len(text) > 1000:
            text = text[:1000] + "..."

        # Reset manual
        if text and "reset" in text.lower():
            brain._manage_history(phone, clear=True)
            send_whatsapp(phone, "♻️ Memoria reiniciada.")
            return

        # --- LLAMADA AL CEREBRO ---
        response = brain.process_message(text, phone, message_id, image_data=image_data, audio_data=audio_data)

        if response:
            if isinstance(response, bytes):
                media_id = upload_media_to_whatsapp(response, "audio/mpeg")
                if media_id:
                    send_whatsapp_audio(phone, media_id)
                else:
                    send_whatsapp(phone, "Tuve un problema generando mi respuesta de voz. 🎤")
            else:
                send_whatsapp(phone, response)
        else:
            config.logger.info(f"Mensaje duplicado o ignorado: {message_id}")

    except Exception as e:
        config.logger.error(f"Error procesando lógica de mensaje: {e}", exc_info=True)
