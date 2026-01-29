from flask import Flask, request, jsonify
import requests
import time
import json
import base64
import urllib.parse
import gunicorn
import hmac
import hashlib
import secrets
from google.cloud import pubsub_v1
import config
import brain
import ingestor

# --- FLASK APP INITIALIZATION ---
app = Flask(__name__)

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
    """Descarga el contenido binario del archivo multimedia con validación de seguridad."""
    try:
        # Security: Validate URL to prevent SSRF
        parsed = urllib.parse.urlparse(media_url)
        if parsed.scheme != "https":
            config.logger.error(f"Security: Non-HTTPS media URL blocked: {media_url}")
            return None

        allowed_domains = [
            "graph.facebook.com",
            "lookaside.fbsbx.com",
            "cdn.fbsbx.com",
            "www.facebook.com",
            "whatsapp.net",
            "mmg.whatsapp.net"
        ]

        # Check if domain is exactly the allowed domain or a subdomain (e.g., .facebook.com)
        if not any(parsed.netloc == d or parsed.netloc.endswith("." + d) for d in allowed_domains):
             config.logger.error(f"Security: Untrusted media domain blocked: {parsed.netloc}")
             return None

        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_TOKEN}"
        }
        # Security: Disable redirects to prevent SSRF bypass
        response = requests.get(media_url, headers=headers, timeout=20, allow_redirects=False)
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


# --- WEBHOOK ROUTES ---

def verify_signature(req):
    """
    Verifica la firma HMAC SHA256 de WhatsApp (X-Hub-Signature-256).
    Retorna True si la firma es válida o si no se ha configurado APP_SECRET (fallback).
    """
    # Si no hay secreto configurado, permitimos el paso (legacy mode)
    # pero logueamos advertencia.
    if not config.APP_SECRET:
        config.logger.warning("⚠️ APP_SECRET no configurado. Saltando verificación de firma.")
        return True

    signature = req.headers.get("X-Hub-Signature-256")
    if not signature:
        config.logger.warning("⛔ Request sin firma X-Hub-Signature-256.")
        return False

    # Formato: sha256=<hash>
    parts = signature.split('=')
    if len(parts) != 2 or parts[0] != 'sha256':
        config.logger.warning("⛔ Formato de firma inválido.")
        return False

    sig_hash = parts[1]

    # Calcular HMAC usando el payload raw
    try:
        payload = req.get_data()
        expected_hash = hmac.new(
            config.APP_SECRET.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        if not secrets.compare_digest(sig_hash, expected_hash):
            config.logger.warning("⛔ Firma inválida.")
            return False

        return True
    except Exception as e:
        config.logger.error(f"Error verificando firma: {e}")
        return False

@app.route('/webhook', methods=['GET', 'POST'])
@app.route("/", methods=["GET", "POST"])
def whatsapp_webhook():
    """
    Entrada Híbrida: Maneja verificación, mensajes de WhatsApp y mensajes de Pub/Sub.
    """
    # 1. Verificación (Handshake con Meta)
    if request.method == "GET":
        verify_token = request.args.get("hub.verify_token")
        if verify_token and config.VERIFY_TOKEN and secrets.compare_digest(verify_token, config.VERIFY_TOKEN):
            return request.args.get("hub.challenge"), 200
        return "Forbidden", 403

    # 2. Recepción de Mensajes (POST)
    if request.method == "POST":
        # Security: Verificar firma HMAC si está configurada
        if not verify_signature(request):
            return "Forbidden", 403

        try:
            data = request.get_json()

            # Lógica original para mensajes directos de WhatsApp
            entries = data.get('entry', [])
            if not entries:
                config.logger.info("Webhook recibido sin 'entry' (Ignorado).")
                return "OK", 200

            entry = entries[0]
            changes_list = entry.get('changes', [])
            if not changes_list:
                return "OK", 200

            changes = changes_list[0]
            value = changes.get('value', {})
            
            if 'messages' in value:
                msg = value['messages'][0]
                phone = msg['from']
                message_id = msg.get('id')
                msg_ts = int(msg.get('timestamp', 0))
                now_ts = int(time.time())

                # Verificar antigüedad (Evitar bucles de reintentos infinitos)
                if now_ts - msg_ts > 300:
                    config.logger.warning(f"⏳ Mensaje descartado por antigüedad ({now_ts - msg_ts}s). ID: {message_id}")
                    return "OK", 200

                # Ack inmediato (Check azul)
                if message_id:
                    mark_as_read(message_id)

                # Publicar a Pub/Sub (Empaquetar para envío)
                if config.PUBSUB_TOPIC and publisher:
                    payload_data = {
                        "msg": msg,
                        "phone": phone,
                        "timestamp": now_ts
                    }
                    data_str = json.dumps(payload_data)
                    data_bytes = data_str.encode("utf-8")

                    future = publisher.publish(config.PUBSUB_TOPIC, data_bytes)
                    # Optimization: Async publish to avoid blocking webhook response
                    # future.result() removed to prevent waiting for ACK
                    future.add_done_callback(
                        lambda f: config.logger.info(f"📤 Mensaje enviado a Pub/Sub: {message_id}")
                        if not f.exception() else config.logger.error(f"❌ Error Pub/Sub: {f.exception()}")
                    )
                else:
                    # Fallback si no hay Pub/Sub
                    _process_message_logic(msg, phone)

            return "OK", 200

        except Exception as e:
            config.logger.error(f"Error en Webhook: {e}", exc_info=True)
            return "Error", 500

@app.route('/sync-inventory', methods=['POST'])
def sync_inventory():
    """
    Ruta para recibir actualizaciones desde Google Sheets.
    Requiere Header: Authorization: <SYNC_API_KEY>
    """
    # En la versión Vector Search, ingestor.sync_inventory maneja la autenticación y la lógica.
    # Pero ingestor espera X-API-KEY, mientras que main usaba Authorization.
    # Ajustamos para compatibilidad o delegamos totalmente.
    # El código actual de ingestor.py usa request.headers.get("X-API-KEY").
    # Si el cliente envía 'Authorization', necesitamos adaptarlo o cambiar ingestor.
    # Como el usuario pidió "llamar a ingestor.sync_inventory(request)", lo hacemos directo.

    return ingestor.sync_inventory(request)

@app.route('/worker', methods=['POST'])
def whatsapp_worker():
    """
    Proceso Asíncrono: Recibe el Push de Pub/Sub y procesa el mensaje con Gemini.
    """
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
