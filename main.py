import functions_framework
import requests
import time
import config
import brain  # Importamos nuestro módulo de lógica

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

@functions_framework.http
def whatsapp_webhook(request):
    """Entry Point de Google Cloud Functions."""
    
    # 1. Verificación (Handshake con Meta)
    if request.method == "GET":
        if request.args.get("hub.verify_token") == config.VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Forbidden", 403

    # 2. Recepción de Mensajes
    if request.method == "POST":
        try:
            data = request.get_json()
            entry = data.get('entry', [])[0]
            changes = entry.get('changes', [])[0]
            value = changes.get('value', {})
            
            if 'messages' in value:
                msg = value['messages'][0]
                phone = msg['from']

                # Verificar antigüedad del mensaje (evitar procesar reintentos de hace horas)
                # Timestamp de WhatsApp viene en segundos (str)
                msg_ts = int(msg.get('timestamp', 0))
                now_ts = int(time.time())

                # Si el mensaje tiene más de 5 minutos de antigüedad, lo ignoramos (retornando 200 para frenar el reintento)
                if now_ts - msg_ts > 300:
                    config.logger.warning(f"⏳ Mensaje descartado por antigüedad ({now_ts - msg_ts}s). ID: {msg.get('id')}")
                    return "OK", 200

                # Marcar como leído inmediatamente para evitar sensación de "colgado"
                message_id = msg.get('id')
                if message_id:
                    mark_as_read(message_id)
                
                # Extracción de texto segura y Multimedia
                text = ""
                image_data = None

                if msg['type'] == 'text':
                    text = msg['text']['body']
                elif msg['type'] == 'interactive':
                    text = msg['interactive']['button_reply']['title']
                elif msg['type'] == 'image':
                    text = msg['image'].get('caption', "")  # Usar el caption como texto si existe
                    media_id = msg['image']['id']

                    # Descargar imagen
                    media_url = get_media_url(media_id)
                    if media_url:
                        image_data = download_media(media_url)
                else:
                    text = "[Multimedia no soportado]"

                # Security enhancement: Input length validation
                if text and len(text) > 1000:
                    text = text[:1000] + "..."
                
                # Lógica de Reset manual
                if text and "reset" in text.lower():
                    # Usamos una función privada del brain solo para borrar
                    brain._manage_history(phone, clear=True)
                    send_whatsapp(phone, "♻️ Memoria reiniciada.")
                    return "OK", 200

                # --- LLAMADA AL CEREBRO ---
                response = brain.process_message(text, phone, message_id, image_data=image_data)
                if response:
                    send_whatsapp(phone, response)
                else:
                    config.logger.info(f"Mensaje duplicado o ignorado: {message_id}")
                
            return "OK", 200

        except Exception as e:
            config.logger.error(f"Error en Webhook: {e}", exc_info=True)
            return "Error", 500
