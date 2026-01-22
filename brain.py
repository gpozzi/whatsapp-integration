import datetime
import logging
import json
from typing import Optional, List, Union
from concurrent.futures import ThreadPoolExecutor

import google.auth
from google.cloud import firestore
try:
    from google.cloud.firestore import Vector
except ImportError:
    # Fallback for environments where Vector is not available or older library versions
    Vector = lambda x: x

from google.cloud import texttospeech
import base64

# AI Integrations
from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings
from langchain_core.messages import HumanMessage
import config

# --- ESTADO GLOBAL ---
_db_client: Optional[firestore.Client] = None
_safety_model: Optional[ChatVertexAI] = None
_embeddings_service: Optional[VertexAIEmbeddings] = None
_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=4)

# --- CONSTANTES ---
MODEL_SALES = "gemini-2.5-flash"
MODEL_SAFETY = "gemini-2.5-flash-lite"
MODEL_LOCATION = "us-central1"
MODEL_TEMP = 0.0
CONTEXT_CHAR_LIMIT = 4000
CONTEXT_TIMEOUT_HOURS = 6
BAD_WORDS = ["Error", "Processing", "Agent stopped"]

def _init_services() -> ChatVertexAI:
    """Inicializa los servicios de Google Cloud y los modelos de IA.

    Inicializa el cliente de Firestore, el LLM de Ventas (Gemini 2.5 Flash),
    el Juez de Seguridad (Gemini 2.5 Flash Lite) y el servicio de Embeddings.
    Fuerza la ejecución en 'us-central1' con temperatura 0.0 para garantizar consistencia.

    Returns:
        ChatVertexAI: La instancia inicializada del LLM principal de Ventas.

    Raises:
        Exception: Si falla la inicialización de algún servicio.
    """
    global _db_client, _safety_model, _embeddings_service
    if _db_client and _safety_model and _embeddings_service:
        # Si ya están inicializados, retornamos una nueva instancia del modelo de ventas
        # para asegurar frescura o reutilizar si se prefiere.
        # En este diseño, retornamos una nueva instancia para el agente principal.
        return ChatVertexAI(
            model_name=MODEL_SALES,
            project=config.PROJECT_ID,
            location=MODEL_LOCATION,
            temperature=MODEL_TEMP,
        )

    try:
        config.logger.info("🔌 Conectando servicios...")

        # Modelo de Ventas (Alta capacidad de razonamiento)
        llm = ChatVertexAI(
            model_name=MODEL_SALES,
            project=config.PROJECT_ID,
            location=MODEL_LOCATION,
            temperature=MODEL_TEMP,
        )

        # Juez de Seguridad (Rápido y económico)
        _safety_model = ChatVertexAI(
            model_name=MODEL_SAFETY,
            project=config.PROJECT_ID,
            location=MODEL_LOCATION,
            temperature=MODEL_TEMP,
        )

        # Servicio de Embeddings (Optimización: Instancia única)
        _embeddings_service = VertexAIEmbeddings(
            model_name="text-embedding-004",
            project=config.PROJECT_ID,
            location=MODEL_LOCATION
        )

        _db_client = firestore.Client(project=config.PROJECT_ID, database=config.DATABASE_NAME)
        return llm
    except Exception as e:
        config.logger.critical(f"Error fatal inicializando servicios: {e}")
        raise

def _update_user_profile(phone: str, history: str):
    """Extrae preferencias clave del usuario y actualiza su perfil a largo plazo.

    Args:
        phone (str): ID del usuario.
        history (str): Historial de la conversación reciente.
    """
    if not _db_client or not _safety_model:
        return

    try:
        # Usamos el modelo ligero para extraer datos estructurados
        # No bloqueamos el hilo principal, esto podría ser asíncrono en un sistema mayor.
        prompt = (
            f"Analiza esta conversación y extrae preferencias del usuario (si las hay).\n"
            f"HISTORIAL:\n{history}\n\n"
            "Busca: 1. Presupuesto (ej: 15k). 2. Modelo/Marca de interés. 3. Nombre (si lo dijo).\n"
            "Responde en JSON: {\"budget\": \"...\", \"model\": \"...\", \"name\": \"...\"}\n"
            "Si no hay dato, pon null."
        )

        response = _safety_model.invoke(prompt).content.strip()
        response = response.replace("```json", "").replace("```", "").strip()

        data = json.loads(response)

        # Solo actualizamos si hay datos relevantes
        updates = {}
        if data.get("budget"): updates["budget"] = data["budget"]
        if data.get("model"): updates["last_interest"] = data["model"]
        if data.get("name"): updates["name"] = data["name"]

        if updates:
            updates["last_updated"] = firestore.SERVER_TIMESTAMP
            _db_client.collection("user_profiles").document(phone).set(updates, merge=True)
            config.logger.info(f"Perfil actualizado para {phone}: {updates}")

    except Exception as e:
        # Fallo silencioso, no es crítico
        config.logger.warning(f"Error actualizando perfil: {e}")

def _manage_history(phone: str, user_text: Optional[str] = None, bot_text: Optional[str] = None, clear: bool = False) -> str:
    """Gestiona el historial del chat con ventana de contexto inteligente y filtrado de higiene.

    Recupera, actualiza y formatea el historial del chat. Implementa una ventana deslizante
    basada en caracteres (~4000) y filtra mensajes de error técnico para
    mantener la pureza del contexto para el LLM.

    Además, inyecta memoria a largo plazo (User Profile) si la sesión es nueva.

    Args:
        phone (str): El número de teléfono del usuario (ID del documento).
        user_text (Optional[str]): Nuevo mensaje del usuario para agregar.
        bot_text (Optional[str]): Nuevo mensaje del bot para agregar.
        clear (bool): Si es True, elimina el historial de este usuario.

    Returns:
        str: Una cadena formateada del historial relevante (orden cronológico).
    """
    if not _db_client:
        return ""
    
    doc_ref = _db_client.collection("chats_whatsapp").document(phone)

    if clear:
        doc_ref.delete()
        return ""

    history_list = []
    is_new_session = False

    try:
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            raw = data.get('mensajes', [])
            stored_ts = data.get('timestamp')

            # Verificar caducidad del contexto (TTL)
            is_expired = False
            if stored_ts:
                now = datetime.datetime.now(datetime.timezone.utc)
                # Manejar compatibilidad de zonas horarias si Firestore devuelve naive o aware
                if stored_ts.tzinfo is None:
                    stored_ts = stored_ts.replace(tzinfo=datetime.timezone.utc)

                if (now - stored_ts) > datetime.timedelta(hours=CONTEXT_TIMEOUT_HOURS):
                    is_expired = True
                    is_new_session = True
                    config.logger.info(f"🧹 Contexto expirado para {phone}. Reiniciando conversación.")
            else:
                is_new_session = True

            if not is_expired:
                # Validación básica para asegurar lista de cadenas
                history_list = [m for m in raw if isinstance(m, str)]
        else:
            is_new_session = True

    except Exception as e:
        config.logger.warning(f"Error leyendo historial: {e}")

    # Actualizar historial si hay nuevos mensajes
    if user_text:
        history_list.append(f"Usuario: {user_text}")
        if bot_text:
            history_list.append(f"Bot: {bot_text}")
            # Si el bot respondió, actualizamos el perfil ASÍNCRONAMENTE para no bloquear la respuesta.
            # ⚡ Performance: Movemos esta tarea lenta (~1-2s) a un hilo de fondo.
            _executor.submit(_update_user_profile, phone, "\n".join(history_list[-4:]))
        
        # Mantener un límite de almacenamiento razonable (ej. últimos 20 mensajes) para ahorrar espacio/costo,
        # mientras la lógica de ventana de contexto abajo maneja el límite "inteligente" de tokens.
        if len(history_list) > 20:
            history_list = history_list[-20:]

        doc_ref.set({
            "mensajes": history_list,
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })

    # Construcción de Contexto Inteligente
    # Recorrer hacia atrás para llenar la cuota de caracteres
    selected_messages = []
    current_chars = 0

    # Inyectar Perfil de Usuario si es sesión nueva o contexto vacío
    profile_context = ""
    if is_new_session:
        try:
            profile_doc = _db_client.collection("user_profiles").document(phone).get()
            if profile_doc.exists:
                p_data = profile_doc.to_dict()
                profile_context = f"[MEMORIA A LARGO PLAZO: Usuario {p_data.get('name', 'Anónimo')}. Interés previo: {p_data.get('last_interest')}. Presupuesto: {p_data.get('budget')}.]\n"
        except Exception as e:
            config.logger.warning(f"Error leyendo perfil usuario: {e}")

    for msg in reversed(history_list):
        # Higiene: Omitir mensajes que contengan errores técnicos
        if any(bad in msg for bad in BAD_WORDS):
            continue

        msg_len = len(msg)
        if current_chars + msg_len > CONTEXT_CHAR_LIMIT:
            break

        selected_messages.append(msg)
        current_chars += msg_len

    final_history = "\n".join(reversed(selected_messages))
    if profile_context:
        final_history = profile_context + final_history

    return final_history

def _audit_response(candidate_text: str) -> bool:
    """Evalúa la seguridad de la respuesta del bot usando el modelo Juez.

    Args:
        candidate_text (str): El texto de respuesta generado por el agente de Ventas.

    Returns:
        bool: True si la respuesta es segura, False en caso contrario.
    """
    try:
        prompt = config.SAFETY_AUDITOR_PROMPT.format(candidate_response=candidate_text)
        verdict = _safety_model.invoke(prompt).content.strip().upper()
        if "PELIGRO" in verdict:
            return False
        return True
    except Exception:
        # Fallar abierto ("Fail Open") para evitar bloquear respuestas legítimas por fallos menores de API,
        # o fallar cerrado si la seguridad es crítica. Por defecto True (Fail Open) según lógica existente.
        return True

def _check_is_duplicate(message_id: str) -> bool:
    """Verifica la idempotencia para evitar procesar el mismo mensaje dos veces.

    Args:
        message_id (str): El ID único del mensaje entrante de WhatsApp.

    Returns:
        bool: True si el mensaje es un duplicado (ya procesado o en proceso), False en caso contrario.
    """
    if not message_id or not _db_client:
        return False

    doc_ref = _db_client.collection("processed_messages").document(message_id)
    try:
        if doc_ref.get().exists:
            return True

        doc_ref.set({
            "timestamp": firestore.SERVER_TIMESTAMP,
            "status": "processing"
        })
        return False
    except Exception as e:
        config.logger.error(f"Error verificando duplicado: {e}")
        return False

def _analyze_tone_and_intent(user_text: str, history: str) -> dict:
    """Clasifica la intención y detecta el tono del usuario.

    Args:
        user_text (str): El mensaje actual del usuario.
        history (str): El historial de la conversación.

    Returns:
        dict: {'intent': str, 'style_instruction': str}
    """
    default_result = {"intent": "SALES_QUERY", "style_instruction": "Sé útil y conciso."}

    try:
        if not _safety_model:
            return default_result

        # Usamos un prompt combinado para ahorrar latencia/costo
        prompt = config.INTENT_AND_TONE_PROMPT.format(history=history, user_input=user_text)
        response_text = _safety_model.invoke(prompt).content.strip()

        # Parseo simple de JSON o formato estructurado
        # Esperamos algo como: CATEGORY: SALES_QUERY | TONE: CASUAL

        intent = "SALES_QUERY"
        style_instruction = "Sé útil y conciso."

        if "FEEDBACK_POS" in response_text: intent = "FEEDBACK_POS"
        elif "FEEDBACK_NEG" in response_text: intent = "FEEDBACK_NEG"
        elif "OTHER" in response_text: intent = "OTHER"

        if "DIRECTO" in response_text:
            style_instruction = "El usuario es directo. Responde con datos precisos, sin rodeos, usa listas."
        elif "DUBITATIVO" in response_text:
            style_instruction = "El usuario está indeciso. Actúa como un asesor empático, haz preguntas guía y sé muy amable."
        elif "ENFADADO" in response_text:
            style_instruction = "El usuario parece molesto. Sé extremadamente formal, discúlpate si es necesario y ofrece soluciones rápidas."
        elif "CASUAL" in response_text:
            style_instruction = "El usuario es casual. Usa un tono amigable, puedes usar emojis y ser conversacional."

        return {"intent": intent, "style_instruction": style_instruction}

    except Exception as e:
        config.logger.error(f"Error analizando tono/intención: {e}")
        return default_result

def _analyze_image(image_data: bytes, user_text: str) -> str:
    """Analiza una imagen enviada por el usuario para extraer información de autos.

    Args:
        image_data (bytes): Los datos binarios de la imagen.
        user_text (str): El texto acompañante del usuario.

    Returns:
        str: Descripción enriquecida de la imagen o mensaje de rechazo si no es un auto.
    """
    if not _safety_model:
        return ""

    try:
        # Prompt multimodal para Gemini
        import base64
        b64_image = base64.b64encode(image_data).decode('utf-8')

        message = HumanMessage(
            content=[
                {"type": "text", "text": f"Analiza esta imagen. El usuario dice: '{user_text}'.\n"
                                         "1. ¿Es un auto? (SI/NO)\n"
                                         "2. Si es SI: Describe marca, modelo aproximado, color y tipo (SUV, Sedán, etc).\n"
                                         "3. Si es NO: Responde 'NO_AUTO'."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
            ]
        )

        response = _safety_model.invoke([message]).content.strip()

        if "NO_AUTO" in response:
            return "NO_AUTO"

        return response

    except Exception as e:
        config.logger.error(f"Error analizando imagen: {e}")
        return "ERROR_IMAGE"

def _should_ask_feedback(bot_response: str) -> bool:
    """Decide si se debe pedir feedback al usuario sobre la respuesta generada.

    Args:
        bot_response (str): La respuesta que el bot va a enviar.

    Returns:
        bool: True si se debe agregar la pregunta de feedback, False si no.
    """
    try:
        if not _safety_model:
            return False

        prompt = config.FEEDBACK_DECISION_PROMPT.format(bot_response=bot_response)
        decision = _safety_model.invoke(prompt).content.strip().upper()
        return "SI" in decision
    except Exception as e:
        config.logger.error(f"Error decidiendo feedback: {e}")
        return False

def _handle_negative_feedback(phone: str, history: str) -> str:
    """Maneja el feedback negativo analizando la causa y guardando el insight.

    Args:
        phone (str): ID del usuario para logging.
        history (str): Historial de conversación.

    Returns:
        str: Respuesta empática para el usuario.
    """
    default_response = "Entendido. ¿Podrías reformular tu consulta con más detalles para poder ayudarte mejor?"

    try:
        if not _safety_model or not _db_client:
            return default_response

        prompt = config.FAILURE_ANALYSIS_PROMPT.format(history=history)
        raw_response = _safety_model.invoke(prompt).content.strip()

        # Limpieza básica de JSON Markdown (```json ... ```)
        raw_response = raw_response.replace("```json", "").replace("```", "").strip()

        analysis = json.loads(raw_response)
        insight = analysis.get("insight", "Error desconocido")
        user_explanation = analysis.get("user_explanation", default_response)

        # Guardar Insight en Firestore
        _db_client.collection("bot_insights").add({
            "user_phone": phone,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "insight": insight,
            "full_history": history
        })

        return f"{user_explanation} Por favor, intenta preguntarme de otra forma."

    except Exception as e:
        config.logger.error(f"Error manejando feedback negativo: {e}")
        return default_response

def _search_cars(query: str) -> str:
    """Busca autos en el inventario usando Vector Search.

    Args:
        query (str): La consulta del usuario.

    Returns:
        str: Texto con los resultados relevantes del inventario.
    """
    try:
        if not _db_client or not _embeddings_service:
            return "No se pudo conectar a la base de datos."

        # ⚡ Performance: Reutilizamos el cliente de Embeddings global
        if not _embeddings_service:
            # Fallback por si no se inicializó en _init_services (casos raros)
             config.logger.warning("Embeddings service no inicializado, creando uno on-the-fly.")
             embeddings_service = VertexAIEmbeddings(
                model_name="text-embedding-004",
                project=config.PROJECT_ID,
                location=MODEL_LOCATION
            )
        else:
            embeddings_service = _embeddings_service

        config.logger.info(f"🔎 Buscando autos para: {query}")

        # 1. Generar Embedding de la consulta
        query_vector = _embeddings_service.embed_query(query)

        # 2. Búsqueda Vectorial en Firestore
        # Se asume que la colección 'inventory_vectors' tiene un índice vectorial en 'embedding_field'
        collection = _db_client.collection("inventory_vectors")

        # Nota: find_nearest requiere que el índice vectorial exista.
        results = collection.find_nearest(
            vector_field="embedding_field",
            query_vector=Vector(query_vector),
            distance_measure=firestore.DistanceMeasure.EUCLIDEAN, # O COSINE, según configuración del índice
            limit=5,
            distance_result_field="distance"
        ).get()

        if not results:
            return "No encontré autos que coincidan exactamente con esa descripción."

        # 3. Formatear resultados
        info = []
        for doc in results:
            data = doc.to_dict()
            # Omitimos el embedding gigante en la respuesta al LLM
            data.pop("embedding_field", None)
            info.append(str(data))

        return "\n---\n".join(info)

    except Exception as e:
        config.logger.error(f"Error en Vector Search: {e}")
        return "Tuve un problema buscando en el inventario."

def process_message(user_text: str, phone_number: str, message_id: Optional[str] = None, image_data: Optional[bytes] = None, audio_data: Optional[bytes] = None) -> Union[str, bytes, None]:
    """Función principal de orquestación para procesar mensajes entrantes.

    Maneja inicialización, deduplicación, Vector Search, gestión de contexto,
    invocación del LLM, manejo de errores y auditoría de seguridad.

    Admite texto, imagen y audio. Si la entrada es audio, la respuesta será audio (bytes).

    Args:
        user_text (str): El texto recibido del usuario.
        phone_number (str): El número de teléfono del usuario.
        message_id (Optional[str]): El ID único del mensaje para deduplicación.
        image_data (Optional[bytes]): Datos binarios de la imagen si se envió una.
        audio_data (Optional[bytes]): Datos binarios del audio si se envió uno.

    Returns:
        Union[str, bytes, None]: El texto (str) o audio (bytes) de respuesta, o None si es duplicado.
    """
    # Asegurar que los servicios estén listos
    sales_llm = _init_services()
    
    # Deduplicación
    if _check_is_duplicate(message_id):
        return None

    # 0. Procesamiento de Audio (si existe)
    # Detectamos género y transcribimos para usarlo como 'user_text'
    detected_gender = None
    if audio_data:
        audio_analysis = _analyze_audio(audio_data)
        user_text = audio_analysis.get("text", "")
        detected_gender = audio_analysis.get("gender", "FEMALE")
        if not user_text:
            return None # Audio ininteligible o vacío

    # Gestión de Contexto
    history = _manage_history(phone_number)

    # 1. Análisis Multimodal (si hay imagen)
    image_context = ""
    if image_data:
        image_analysis = _analyze_image(image_data, user_text)
        if image_analysis == "NO_AUTO":
            return "Lo siento, solo puedo analizar imágenes de autos para ayudarte a buscar en el inventario. 🚗"
        elif image_analysis != "ERROR_IMAGE":
            image_context = f"\n[INFO IMAGEN: El usuario envió una foto. Análisis: {image_analysis}]"
            config.logger.info(f"Imagen analizada: {image_analysis}")

    # 2. Análisis de Intención y Tono & Búsqueda Vectorial (Paralelo)
    # ⚡ Performance: Optimistic Search - Ejecutamos búsqueda e intención simultáneamente
    search_query = user_text
    if image_context:
        search_query += f" {image_context}"

    future_analysis = _executor.submit(_analyze_tone_and_intent, user_text, history)
    future_search = _executor.submit(_search_cars, search_query)

    analysis = future_analysis.result()
    intent = analysis["intent"]
    style_instruction = analysis["style_instruction"]
    config.logger.info(f"Intención: {intent} | Estilo: {style_instruction}")

    try:
        final_text = ""

        if intent == "FEEDBACK_NEG":
            # 3. Manejo de Feedback Negativo
            final_text = _handle_negative_feedback(phone_number, history)

        elif intent == "FEEDBACK_POS":
             # 4. Manejo de Feedback Positivo
             final_text = "¡Gracias! Me alegra haberte ayudado. 😊 ¿Buscas algo más?"

        else:
            # 5. Flujo Normal (RAG con Vector Search)

            # Recuperamos resultado de búsqueda (ya debería estar listo o casi listo)
            inventory_context = future_search.result()

            # Construir Prompt RAG
            prompt = (
                f"Eres Jules, un asistente de ventas de autos experto y amable.\n"
                f"Usa la siguiente información del INVENTARIO para responder al usuario.\n"
                f"Si la información no está en el inventario, dilo honestamente, pero ofrece alternativas si las ves.\n\n"
                f"INVENTARIO RELEVANTE:\n{inventory_context}\n\n"
                f"HISTORIAL:\n{history}{image_context}\n\n"
                f"CONSULTA USUARIO: '{user_text}'\n\n"
                f"INSTRUCCIÓN DE TONO: {style_instruction}\n"
            )

            response = sales_llm.invoke(prompt)
            final_text = response.content

            # Auditoría de Seguridad
            if not _audit_response(final_text):
                return "No puedo procesar esa solicitud por motivos de seguridad."

            # 6. Decisión de Feedback (Supervisor)
            if _should_ask_feedback(final_text):
                final_text += " (¿Te sirvió esta info? Responde SÍ o NO)"

        # Guardar Interacción
        _manage_history(phone_number, user_text, final_text)

        # SI LA ENTRADA FUE AUDIO -> SALIDA AUDIO
        if audio_data and detected_gender:
            audio_response = _text_to_speech(final_text, detected_gender)
            if audio_response:
                return audio_response
            # Si falla el TTS, devolvemos texto como fallback

        return final_text

    except Exception as e:
        config.logger.error(f"Error procesando mensaje: {e}")
        return "Tuve un pequeño error técnico. ¿Podrías preguntarme de nuevo?"

def _analyze_audio(audio_bytes: bytes) -> dict:
    """Analiza un archivo de audio para transcribirlo y detectar el género del hablante.

    Args:
        audio_bytes (bytes): El contenido binario del archivo de audio.

    Returns:
        dict: {'text': str, 'gender': str} donde gender es 'MALE' o 'FEMALE'.
    """
    if not _safety_model:
        return {"text": "", "gender": "FEMALE"} # Default

    try:
        # Prompt multimodal
        # Usamos 'media' type con raw bytes. langchain-google-vertexai mapea esto a Blob.
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": "Escucha este audio atentamente. Tu tarea es:\n"
                            "1. Transcribir lo que dice el usuario (TEXT).\n"
                            "2. Identificar el género de la voz (GENDER: MALE o FEMALE).\n\n"
                            "Responde SOLO en formato JSON exacto:\n"
                            "{\"text\": \"...\", \"gender\": \"...\"}"
                },
                {
                    "type": "media",
                    "mime_type": "audio/ogg",
                    "data": audio_bytes
                }
            ]
        )

        response = _safety_model.invoke([message]).content.strip()

        # Limpiar JSON
        response = response.replace("```json", "").replace("```", "").strip()
        data = json.loads(response)

        # Normalizar género
        raw_gender = data.get("gender", "FEMALE").upper()
        gender = "FEMALE"
        if "MALE" in raw_gender or "HOMBRE" in raw_gender:
            gender = "MALE"

        return {
            "text": data.get("text", ""),
            "gender": gender
        }

    except Exception as e:
        config.logger.error(f"Error analizando audio con Gemini: {e}")
        return {"text": "", "gender": "FEMALE"}

def _text_to_speech(text: str, gender: str) -> Optional[bytes]:
    """Convierte texto a audio usando Google Cloud TTS con fallback.

    Args:
        text (str): El texto a convertir.
        gender (str): 'MALE' o 'FEMALE'.

    Returns:
        Optional[bytes]: El audio en formato MP3.
    """
    try:
        client = texttospeech.TextToSpeechClient()
        input_text = texttospeech.SynthesisInput(text=text)

        # 1. Intento Principal (Voces Neurales)
        voice_name = config.TTS_VOICE_MALE if gender == "MALE" else config.TTS_VOICE_FEMALE

        # Configuración común (fuera del try interno para que esté disponible en fallback)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        try:
            voice = texttospeech.VoiceSelectionParams(
                language_code="es-US",
                name=voice_name
            )
            response = client.synthesize_speech(
                input=input_text, voice=voice, audio_config=audio_config
            )
            return response.audio_content
        except Exception as e:
            config.logger.warning(f"⚠️ TTS Neural falló: {e}. Intentando fallback estándar.")

            # 2. Intento Fallback (Voces Estándar)
            fallback_voice = "es-US-Standard-B" if gender == "MALE" else "es-US-Standard-A"
            voice = texttospeech.VoiceSelectionParams(
                language_code="es-US",
                name=fallback_voice
            )
            response = client.synthesize_speech(
                input=input_text, voice=voice, audio_config=audio_config
            )
            return response.audio_content

    except Exception as e:
        config.logger.error(f"❌ Error fatal en TTS: {e}")
        return None
