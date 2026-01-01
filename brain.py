import datetime
import pandas as pd
import google.auth
from googleapiclient.discovery import build
from google.cloud import firestore

# Integraciones de IA
from langchain_google_vertexai import ChatVertexAI
from langchain_experimental.agents import create_pandas_dataframe_agent
import config

# --- ESTADO GLOBAL ---
_db_client = None
_df_inventory = None
_sales_agent = None
_safety_model = None

def _init_services():
    global _db_client, _safety_model
    if _db_client: return 

    try:
        config.logger.info("🔌 Conectando servicios...")
        
        # --- CAMBIO IMPORTANTE: Forzamos la ubicación a 'us-central1' ---
        # Gemini 2.0 y 1.5 a veces no están en todas las regiones de Europa.
        # Al poner 'us-central1' aquí, aseguramos que siempre encuentre el modelo.

        # Temperatura 0 es VITAL para evitar alucinaciones de formato
        llm = ChatVertexAI(
            model_name="gemini-2.5-flash",
            project=config.PROJECT_ID,
            location="us-central1", # <--- CAMBIADO (Antes era config.LOCATION)
            temperature=0.0, 
        )

        _safety_model = ChatVertexAI(
            model_name="gemini-2.5-flash",
            project=config.PROJECT_ID,
            location="us-central1", # <--- CAMBIADO (Antes era config.LOCATION)
            temperature=0.0,
        )
        
        _db_client = firestore.Client(project=config.PROJECT_ID, database=config.DATABASE_NAME)
        return llm
    except Exception as e:
        config.logger.critical(f"Error fatal: {e}")
        raise

def _load_inventory(llm_model):
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
        if len(rows) < 2: return False

        headers = [h.lower().strip() for h in rows[0]]
        _df_inventory = pd.DataFrame(rows[1:], columns=headers)
        
        # --- CONFIGURACIÓN ANTI-LOOP ---
        _sales_agent = create_pandas_dataframe_agent(
            llm_model, 
            _df_inventory, 
            verbose=True,
            allow_dangerous_code=True,
            prefix=config.SALES_AGENT_PREFIX,
            # Importante: Manejo de errores de parsing
            handle_parsing_errors=True,
            # Importante: Límite de iteraciones bajo (4 intentos máx)
            max_iterations=4,
        )
        config.logger.info(f"✅ Inventario cargado: {len(_df_inventory)} autos.")
        return True
    except Exception as e:
        config.logger.error(f"Error cargando inventario: {e}")
        return False

def _manage_history(phone, user_text=None, bot_text=None, clear=False):
    if not _db_client: return ""
    doc_ref = _db_client.collection("chats_whatsapp").document(phone)
    
    if clear:
        doc_ref.delete()
        return ""

    history = []
    try:
        doc = doc_ref.get()
        if doc.exists:
            raw = doc.to_dict().get('mensajes', [])
            history = [m for m in raw if isinstance(m, str)]
    except: pass

    if user_text:
        history.append(f"Usuario: {user_text}")
        if bot_text: history.append(f"Bot: {bot_text}")
        if len(history) > 6: history = history[-6:]
        
        doc_ref.set({
            "mensajes": history,
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })

    return "\n".join(history)

def _audit_response(candidate_text):
    try:
        prompt = config.SAFETY_AUDITOR_PROMPT.format(candidate_response=candidate_text)
        verdict = _safety_model.invoke(prompt).content.strip().upper()
        if "PELIGRO" in verdict: return False
        return True
    except: return True

def _check_is_duplicate(message_id):
    """Verifica si el mensaje ya fue procesado para evitar bucles de reintentos."""
    if not message_id or not _db_client: return False

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
        config.logger.error(f"Error checking duplicate: {e}")
        return False

def process_message(user_text, phone_number, message_id=None):
    primary_model = _init_services()
    
    # --- DEDUPLICACIÓN ---
    if _check_is_duplicate(message_id):
        return None

    if _df_inventory is None:
        if not _load_inventory(primary_model):
            return "El sistema se está reiniciando, dame un minuto..."

    history = _manage_history(phone_number)
    
    try:
        prompt = f"HISTORIAL:\n{history}\n\nCONSULTA: '{user_text}'"
        
        # Ejecutamos el agente
        response = _sales_agent.invoke(prompt)
        final_text = response['output']
        
        # --- FILTRO ESTÉTICO FINAL ---
        # Si a pesar de todo falla y devuelve el mensaje de error en inglés, lo ocultamos.
        if "Agent stopped" in final_text or "iteration limit" in final_text:
            config.logger.warning("⚠️ Loop detectado y ocultado al usuario.")
            final_text = "¡Uy! Me mareé buscando en tantos autos 😵‍💫. ¿Podrías ser un poco más específico con lo que buscas? (Ej: Toyota Corolla 2020)"
            
        # Auditoría de seguridad
        if not _audit_response(final_text):
            return "No puedo procesar esa solicitud por motivos de seguridad."
            
        _manage_history(phone_number, user_text, final_text)
        return final_text
        
    except Exception as e:
        config.logger.error(f"Error procesando mensaje: {e}")
        return "Tuve un pequeño error técnico. ¿Podrías preguntarme de nuevo?"
