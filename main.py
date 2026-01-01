import functions_framework
import requests
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
                
                # Extracción de texto segura
                text = ""
                if msg['type'] == 'text':
                    text = msg['text']['body']
                elif msg['type'] == 'interactive':
                    text = msg['interactive']['button_reply']['title']
                else:
                    text = "[Multimedia no soportado]"

                # Security enhancement: Input length validation
                # Prevent DoS/Token exhaustion by limiting input size
                if len(text) > 1000:
                    text = text[:1000] + "..."
                
                # Lógica de Reset manual
                if "reset" in text.lower():
                    # Usamos una función privada del brain solo para borrar
                    brain._manage_history(phone, clear=True)
                    send_whatsapp(phone, "♻️ Memoria reiniciada.")
                    return "OK", 200

                # --- LLAMADA AL CEREBRO ---
                response = brain.process_message(text, phone)
                send_whatsapp(phone, response)
                
            return "OK", 200

        except Exception as e:
            config.logger.error(f"Error en Webhook: {e}", exc_info=True)
            return "Error", 500
