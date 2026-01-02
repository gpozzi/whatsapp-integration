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
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
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
                
                # Extracción de texto segura
                text = ""
                if msg['type'] == 'text':
                    text = msg['text']['body']
                elif msg['type'] == 'interactive':
                    text = msg['interactive']['button_reply']['title']
                else:
                    text = "[Multimedia no soportado]"
                
                # Lógica de Reset manual
                if "reset" in text.lower():
                    # Usamos una función privada del brain solo para borrar
                    brain._manage_history(phone, clear=True)
                    send_whatsapp(phone, "♻️ Memoria reiniciada.")
                    return "OK", 200

                # --- LLAMADA AL CEREBRO ---
                response = brain.process_message(text, phone, message_id)
                if response:
                    send_whatsapp(phone, response)
                else:
                    config.logger.info(f"Mensaje duplicado o ignorado: {message_id}")
                
            return "OK", 200

        except Exception as e:
            config.logger.error(f"Error en Webhook: {e}", exc_info=True)
            return "Error", 500
