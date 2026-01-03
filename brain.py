import datetime
import logging
import json
from typing import Optional, List, Union

import pandas as pd
import google.auth
from googleapiclient.discovery import build
from google.cloud import firestore
from google.cloud import texttospeech
import base64

# AI Integrations
from langchain_google_vertexai import ChatVertexAI
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain_experimental.tools.python.tool import PythonAstREPLTool
from langchain_core.messages import HumanMessage
import config
from security import validate_python_code, SecurityError

# --- ESTADO GLOBAL ---
_db_client: Optional[firestore.Client] = None
_df_inventory: Optional[pd.DataFrame] = None
_inventory_timestamp: Optional[datetime.datetime] = None
_safety_model: Optional[ChatVertexAI] = None

# --- CONSTANTES ---
MODEL_SALES = "gemini-2.5-flash"
MODEL_SAFETY = "gemini-2.5-flash-lite"
MODEL_LOCATION = "us-central1"
MODEL_TEMP = 0.0
CONTEXT_CHAR_LIMIT = 4000
CONTEXT_TIMEOUT_HOURS = 6
BAD_WORDS = ["Error", "Processing", "Agent stopped"]

class SafePythonAstREPLTool(PythonAstREPLTool):
    """Herramienta de ejecución de Python con validación de seguridad (AST)."""

    name: str = "python_repl_ast"
    description: str = (
        "A Python shell. Use this to execute python commands. "
        "Input should be a valid python command. "
        "When using this tool, sometimes output is abbreviated - "
        "make sure it does not look abbreviated before using it in your answer."
    )

    def _run(self, query: str, run_manager=None) -> str:
        try:
            validate_python_code(query)
            return super()._run(query, run_manager=run_manager)
        except SecurityError as e:
            return f"SecurityError: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

def _init_services() -> ChatVertexAI:
    """Inicializa los servicios de Google Cloud y los modelos de IA.

    Inicializa el cliente de Firestore, el LLM de Ventas (Gemini 2.5 Flash) y
    el Juez de Seguridad (Gemini 2.5 Flash Lite). Fuerza la ejecución en
    'us-central1' con temperatura 0.0 para garantizar consistencia.

    Returns:
        ChatVertexAI: La instancia inicializada del LLM principal de Ventas.

    Raises:
        Exception: Si falla la inicialización de algún servicio.
    """
    global _db_client, _safety_model
    if _db_client:
        return  # Servicios ya inicializados (la lógica en process_message maneja el retorno)

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

        _db_client = firestore.Client(project=config.PROJECT_ID, database=config.DATABASE_NAME)
        return llm
    except Exception as e:
        config.logger.critical(f"Error fatal inicializando servicios: {e}")
        raise

def _load_inventory() -> bool:
    """Descarga el inventario desde Google Sheets.

    Returns:
        bool: True si el inventario se cargó exitosamente, False en caso contrario.
    """
    global _df_inventory, _inventory_timestamp
    try:
        config.logger.info("📥 Descargando inventario...")
        creds, _ = google.auth.default()
        service = build('sheets', 'v4', credentials=creds)

        meta = service.spreadsheets().get(spreadsheetId=config.SPREADSHEET_ID).execute()
        sheet_title = meta['sheets'][0]['properties']['title']
        result = service.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID, range=f"'{sheet_title}'!A:AZ"
        ).execute()

        rows = result.get('values', [])
        if len(rows) < 2:
            return False

        headers = [h.lower().strip() for h in rows[0]]
        _df_inventory = pd.DataFrame(rows[1:], columns=headers)
        _inventory_timestamp = datetime.datetime.now(datetime.timezone.utc)

        config.logger.info(f"✅ Inventario cargado: {len(_df_inventory)} autos.")
        return True
    except Exception as e:
        config.logger.error(f"Error cargando inventario: {e}")
        # Revertir estado parcial para evitar inconsistencias
        _df_inventory = None
        _inventory_timestamp = None
        return False

def _get_sales_agent(llm_model: ChatVertexAI):
    """Obtiene una instancia fresca del agente de ventas con el inventario actualizado.

    Verifica si el inventario necesita recarga (TTL) antes de crear el agente.
    """
    global _df_inventory, _inventory_timestamp

    # Verificar si el inventario es stale o no existe
    needs_reload = False
    if _df_inventory is None or _inventory_timestamp is None:
        needs_reload = True
    else:
        now = datetime.datetime.now(datetime.timezone.utc)
        if (now - _inventory_timestamp) > datetime.timedelta(minutes=config.INVENTORY_REFRESH_TIME_MINUTES):
            needs_reload = True
            config.logger.info("⌛ Inventario caducado (TTL). Recargando...")

    if needs_reload:
        if not _load_inventory():
             # Si falla la recarga, pero teníamos datos viejos, podríamos decidir usarlos o fallar.
             # Aquí fallamos si no tenemos nada. Si tenemos algo viejo, _df_inventory podría ser None si falló.
             if _df_inventory is None:
                raise Exception("No se pudo cargar el inventario.")

    # Crear una nueva instancia del agente para este request
    return create_pandas_dataframe_agent(
        llm_model,
        _df_inventory,
        verbose=True,
        allow_dangerous_code=True,
        prefix=config.SALES_AGENT_PREFIX,
        agent_executor_kwargs={"handle_parsing_errors": True},
        max_iterations=4,
    )

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
            # Si el bot respondió, intentamos actualizar el perfil (asíncrono idealmente, aquí síncrono)
            # Para no sobrecargar, lo hacemos de forma simple o al final del turno.
            # En esta arquitectura simple, lo llamamos aquí.
            _update_user_profile(phone, "\n".join(history_list[-4:])) # Solo analizamos lo último
        
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

def _find_similar_cars(query_context: str, sales_agent) -> str:
    """Busca autos similares cuando no hay resultados exactos.

    Args:
        query_context (str): Texto que describe lo que se buscaba (para extraer precio/tipo).
        sales_agent: La instancia del agente a usar.

    Returns:
        str: Texto con sugerencias.
    """
    if _df_inventory is None or _df_inventory.empty:
        return ""

    try:
        # Estrategia: Le pedimos al Agente que busque "alternativas" explícitamente.
        cross_sell_prompt = (
            f"El usuario buscaba: '{query_context}'. No se encontró exacto.\n"
            "TU TAREA: Buscar en el dataframe autos SIMILARES (mismo tipo de carrocería O precio +/- 20%).\n"
            "Si encuentras algo, recomiéndalo sutilmente (máximo 2 opciones).\n"
            "Si no, di 'No encontré similares'."
        )

        response = sales_agent.invoke(cross_sell_prompt)
        output = response['output']

        if "No encontré" in output or "Agent stopped" in output:
            return ""

        return f"\n\n💡 Sugerencia: {output}"

    except Exception as e:
        config.logger.error(f"Error buscando similares: {e}")
        return ""

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
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": f"Analiza esta imagen. El usuario dice: '{user_text}'.\n"
                            "1. ¿Es un auto? (SI/NO)\n"
                            "2. Si es SI: Describe marca, modelo aproximado, color y tipo (SUV, Sedán, etc).\n"
                            "3. Si es NO: Responde 'NO_AUTO'."
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"} # Gemini client handles this if correctly formatted, but raw bytes support varies by client version.
                    # Best practice with ChatVertexAI/LangChain: pass the blob if supported or base64.
                    # Assuming langchain-google-vertexai handles base64 encoded data uri or raw image parts.
                    # Let's use a simpler prompt structure if possible or rely on the library to handle bytes.
                }
            ]
        )

        # We need to base64 encode the bytes first for the data URI format
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

def process_message(user_text: str, phone_number: str, message_id: Optional[str] = None, image_data: Optional[bytes] = None, audio_data: Optional[bytes] = None) -> Union[str, bytes, None]:
    """Función principal de orquestación para procesar mensajes entrantes.

    Maneja inicialización, deduplicación, carga de inventario, gestión de contexto,
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
    # Asegurar que los servicios estén listos (retorna instancia del LLM de Ventas)
    primary_model = _init_services()
    
    # Deduplicación
    if _check_is_duplicate(message_id):
        return None

    # Obtener instancia del agente (carga inventario si es necesario)
    try:
        # Si _init_services retornó None (porque _db_client ya existía), necesitamos asegurar una instancia.
        model_to_use = primary_model
        if not model_to_use:
             model_to_use = ChatVertexAI(
                model_name=MODEL_SALES,
                project=config.PROJECT_ID,
                location=MODEL_LOCATION,
                temperature=MODEL_TEMP,
            )

        sales_agent = _get_sales_agent(model_to_use)
    except Exception as e:
        config.logger.error(f"Error obteniendo agente de ventas: {e}")
        return "El sistema se está actualizando, dame un minuto..."

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

    # 2. Análisis de Intención y Tono
    analysis = _analyze_tone_and_intent(user_text, history)
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
            # 5. Flujo Normal (Sales Agent)
            prompt = f"HISTORIAL:\n{history}{image_context}\n\nCONSULTA: '{user_text}'\n\nINSTRUCCIÓN DE TONO: {style_instruction}"
            if image_context:
                prompt += "\nNOTA: El usuario busca algo similar a lo que se describe en [INFO IMAGEN]."

            response = sales_agent.invoke(prompt)
            final_text = response['output']

            # Lógica de Cross-Selling (Si la respuesta indica vacío)
            # Detectamos frases típicas de "no hay resultados"
            no_stock_phrases = ["no tengo", "no encuentro", "no hay", "0 resultados", "no está disponible"]
            if any(p in final_text.lower() for p in no_stock_phrases):
                suggestion = _find_similar_cars(user_text, sales_agent)
                if suggestion:
                    final_text += suggestion

            # Filtro Estético/Errores
            if "Agent stopped" in final_text or "iteration limit" in final_text:
                config.logger.warning("⚠️ Loop detectado y ocultado.")
                final_text = "¡Uy! Me mareé buscando en tantos autos 😵‍💫. ¿Podrías ser un poco más específico con lo que buscas? (Ej: Toyota Corolla 2020)"

            # Auditoría de Seguridad
            if not _audit_response(final_text):
                return "No puedo procesar esa solicitud por motivos de seguridad."

            # 5. Decisión de Feedback (Supervisor)
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
