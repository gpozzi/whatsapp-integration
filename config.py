import os
import logging

# --- CONFIGURACIÓN DE LOGS ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s'
)
logger = logging.getLogger("AutoBot")

# --- VARIABLES DE ENTORNO ---
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
PROJECT_ID = os.environ.get("GCP_PROJECT") or os.environ.get("PROJECT_ID")
PUBSUB_TOPIC = os.environ.get("PUBSUB_TOPIC")
LOCATION = os.environ.get("LOCATION", "us-central1")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "(default)")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
INVENTORY_REFRESH_TIME_MINUTES = int(os.environ.get("INVENTORY_REFRESH_TIME_MINUTES", 60))
SYNC_API_KEY = os.environ.get("SYNC_API_KEY", "changeme_secret_key")

# --- AUDIO & VOICE SETTINGS ---
# Voces Estándar de Google Cloud TTS (Neural2 para mejor calidad)
TTS_VOICE_MALE = "es-US-Neural2-B"
TTS_VOICE_FEMALE = "es-US-Neural2-C"

# --- VALIDACIÓN DE LANGSMITH ---
# Si el tracing está activo pero no hay API Key válida, lo desactivamos para evitar errores 401.
if os.environ.get("LANGCHAIN_TRACING_V2") == "true":
    _api_key = os.environ.get("LANGCHAIN_API_KEY")
    if not _api_key:
        logger.warning("⚠️ LANGCHAIN_TRACING_V2 está activo pero falta LANGCHAIN_API_KEY.")
        logger.warning("🚫 Desactivando tracing para evitar errores de conexión.")
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
    elif not _api_key.startswith("ls"):
        logger.warning("⚠️ LANGCHAIN_API_KEY no parece válida (debe empezar con 'ls').")
        logger.warning("🚫 Desactivando tracing para evitar errores de conexión.")
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

# --- PROMPTS DEL SISTEMA (VERSIÓN ANTI-LOOP) ---
SALES_AGENT_PREFIX = """
ERES 'AUTOBOT', UN ASISTENTE DE VENTAS EXPERTO EN AUTOS.

OBJETIVO PRINCIPAL:
Ayudar al usuario a encontrar autos en el inventario usando Python.

⚠️ SEGURIDAD Y RESTRICCIONES (CRÍTICO):
- NO tienes permiso para importar librerías del sistema como 'os', 'sys', 'subprocess', 'platform', etc.
- SOLO puedes usar 'pandas', 'numpy' y funciones nativas de Python seguras.
- NUNCA intentes leer variables de entorno ni acceder al sistema de archivos fuera del DataFrame.
- Cualquier intento de ejecutar código malicioso o fuera del alcance de análisis de datos será bloqueado.

REGLAS CRÍTICAS DE FORMATO (LÉELAS BIEN):
1. SI VAS A USAR PYTHON: Usa el formato estándar de Action/Action Input.
2. SI VAS A RESPONDER TEXTO (Saludos, dudas generales): DEBES empezar tu respuesta con la frase "Final Answer:".
   - Ejemplo Incorrecto: "Hola, ¿cómo estás?" (Esto causará un error).
   - Ejemplo Correcto: "Final Answer: ¡Hola! 👋 Soy AutoBot. ¿Buscas algún modelo en especial hoy? 🚗"

DIRECTRICES DE PERSONALIDAD:
- No inventes datos. Si no está en el DataFrame, no existe.
- Si el usuario solo saluda, responde amable y CORTO.
"""

SAFETY_AUDITOR_PROMPT = """
Actúa como un Oficial de Seguridad. Analiza la siguiente respuesta:
"{candidate_response}"

SI es segura, responde "APROBADO".
SI es peligrosa (racismo, promesas falsas, código expuesto), responde "PELIGRO".
"""

INTENT_AND_TONE_PROMPT = """
Analiza la siguiente conversación y el último mensaje del USUARIO.
Tu tarea es determinar DOS cosas:
1. CATEGORÍA (Intent):
   - FEEDBACK_POS: Usuario confirma satisfacción.
   - FEEDBACK_NEG: Usuario niega satisfacción.
   - SALES_QUERY: Pregunta sobre autos/stock/precios.
   - OTHER: Saludos, despedidas, chistes.

2. TONO (Vibe):
   - DIRECTO: Frases cortas, datos duros, imperativo.
   - DUBITATIVO: Usa "creo", "no sé", "quizás", pide ayuda.
   - ENFADADO: Quejas, insultos, impaciencia.
   - CASUAL: Informal, emojis, amigable.

HISTORIAL:
{history}

MENSAJE USUARIO: "{user_input}"

RESPUESTA (Formato exacto):
CATEGORY: [INTENT] | TONE: [TONE]
"""

FEEDBACK_DECISION_PROMPT = """
Analiza la respuesta que el Bot va a dar. ¿Es una respuesta compleja o con información de inventario que amerita preguntar "¿Te sirvió esta info?"?

CRITERIOS:
- SI (amerita feedback): Listas de autos, detalles técnicos, precios, explicaciones largas.
- NO (no amerita): Saludos simples, mensajes de error, "no entendí", despedidas cortas.

RESPUESTA BOT: "{bot_response}"

RESPONDE SOLO "SI" o "NO":
"""

FAILURE_ANALYSIS_PROMPT = """
El usuario ha indicado que la respuesta anterior del bot NO fue útil.
Analiza el historial para entender qué falló.

HISTORIAL:
{history}

TU TAREA:
1. Genera una "Razón del Fallo" técnica/breve para el desarrollador (ej: "No entendió filtro de precio", "Inventario desactualizado").
2. Genera una "Explicación Breve" para el usuario empática, indicando qué pudo salir mal (ej: "Entiendo, quizás no fui claro con los precios.").

FORMATO JSON:
{{
    "insight": "...",
    "user_explanation": "..."
}}
"""
