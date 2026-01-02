import datetime
import logging
from typing import Optional, List, Union

import pandas as pd
import google.auth
from googleapiclient.discovery import build
from google.cloud import firestore

# AI Integrations
from langchain_google_vertexai import ChatVertexAI
from langchain_experimental.agents import create_pandas_dataframe_agent
import config

# --- ESTADO GLOBAL ---
_db_client: Optional[firestore.Client] = None
_df_inventory: Optional[pd.DataFrame] = None
_sales_agent = None
_safety_model: Optional[ChatVertexAI] = None

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

def _load_inventory(llm_model: ChatVertexAI) -> bool:
    """Descarga el inventario desde Google Sheets e inicializa el Agente de DataFrame.

    Args:
        llm_model (ChatVertexAI): El modelo de lenguaje que potenciará al agente.

    Returns:
        bool: True si el inventario se cargó y el agente se creó exitosamente, False en caso contrario.
    """
    global _df_inventory, _sales_agent
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

        # Inicializar Agente con configuración anti-bucle y manejo de errores
        _sales_agent = create_pandas_dataframe_agent(
            llm_model,
            _df_inventory,
            verbose=True,
            allow_dangerous_code=True,
            prefix=config.SALES_AGENT_PREFIX,
            agent_executor_kwargs={"handle_parsing_errors": True},
            max_iterations=4,
        )
        config.logger.info(f"✅ Inventario cargado: {len(_df_inventory)} autos.")
        return True
    except Exception as e:
        config.logger.error(f"Error cargando inventario: {e}")
        # Revertir estado parcial para evitar inconsistencias
        _df_inventory = None
        _sales_agent = None
        return False

def _manage_history(phone: str, user_text: Optional[str] = None, bot_text: Optional[str] = None, clear: bool = False) -> str:
    """Gestiona el historial del chat con ventana de contexto inteligente y filtrado de higiene.

    Recupera, actualiza y formatea el historial del chat. Implementa una ventana deslizante
    basada en caracteres (~4000) y filtra mensajes de error técnico para
    mantener la pureza del contexto para el LLM.

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
                    config.logger.info(f"🧹 Contexto expirado para {phone}. Reiniciando conversación.")

            if not is_expired:
                # Validación básica para asegurar lista de cadenas
                history_list = [m for m in raw if isinstance(m, str)]

    except Exception as e:
        config.logger.warning(f"Error leyendo historial: {e}")

    # Actualizar historial si hay nuevos mensajes
    if user_text:
        history_list.append(f"Usuario: {user_text}")
        if bot_text:
            history_list.append(f"Bot: {bot_text}")
        
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

    for msg in reversed(history_list):
        # Higiene: Omitir mensajes que contengan errores técnicos
        if any(bad in msg for bad in BAD_WORDS):
            continue

        msg_len = len(msg)
        if current_chars + msg_len > CONTEXT_CHAR_LIMIT:
            break

        selected_messages.append(msg)
        current_chars += msg_len

    # Restaurar orden cronológico
    return "\n".join(reversed(selected_messages))

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

def process_message(user_text: str, phone_number: str, message_id: Optional[str] = None) -> Optional[str]:
    """Función principal de orquestación para procesar mensajes entrantes.

    Maneja inicialización, deduplicación, carga de inventario, gestión de contexto,
    invocación del LLM, manejo de errores y auditoría de seguridad.

    Args:
        user_text (str): El texto recibido del usuario.
        phone_number (str): El número de teléfono del usuario.
        message_id (Optional[str]): El ID único del mensaje para deduplicación.

    Returns:
        Optional[str]: El texto de respuesta para enviar, o None si es duplicado.
    """
    # Asegurar que los servicios estén listos (retorna instancia del LLM de Ventas)
    primary_model = _init_services()
    
    # Deduplicación
    if _check_is_duplicate(message_id):
        return None

    # Verificación de Inventario
    if _df_inventory is None:
        # Necesitamos pasar el modelo a _load_inventory.
        # Si _init_services retornó None (porque _db_client ya existía), necesitamos asegurar una instancia.
        model_to_use = primary_model
        if not model_to_use:
             model_to_use = ChatVertexAI(
                model_name=MODEL_SALES,
                project=config.PROJECT_ID,
                location=MODEL_LOCATION,
                temperature=MODEL_TEMP,
            )

        if not _load_inventory(model_to_use):
            return "El sistema se está reiniciando, dame un minuto..."

    # Gestión de Contexto
    history = _manage_history(phone_number)

    try:
        prompt = f"HISTORIAL:\n{history}\n\nCONSULTA: '{user_text}'"

        # Invocar Agente
        response = _sales_agent.invoke(prompt)
        final_text = response['output']

        # Filtro Estético/Errores
        if "Agent stopped" in final_text or "iteration limit" in final_text:
            config.logger.warning("⚠️ Loop detectado y ocultado.")
            final_text = "¡Uy! Me mareé buscando en tantos autos 😵‍💫. ¿Podrías ser un poco más específico con lo que buscas? (Ej: Toyota Corolla 2020)"

        # Auditoría de Seguridad
        if not _audit_response(final_text):
            return "No puedo procesar esa solicitud por motivos de seguridad."

        # Guardar Interacción
        _manage_history(phone_number, user_text, final_text)
        return final_text

    except Exception as e:
        config.logger.error(f"Error procesando mensaje: {e}")
        return "Tuve un pequeño error técnico. ¿Podrías preguntarme de nuevo?"
