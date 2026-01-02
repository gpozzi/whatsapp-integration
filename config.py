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
LOCATION = os.environ.get("LOCATION", "us-central1")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "(default)")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")

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

INTENT_CLASSIFIER_PROMPT = """
Analiza la siguiente conversación y clasifica el último mensaje del USUARIO en una de estas categorías:

1. FEEDBACK_POS: El usuario dice "SÍ" (o similar) respondiendo a una pregunta de satisfacción previa del bot.
2. FEEDBACK_NEG: El usuario dice "NO" (o similar) respondiendo a una pregunta de satisfacción previa del bot.
3. SALES_QUERY: El usuario pregunta por autos, precios, stock o características.
4. OTHER: Saludos, despedidas, o cualquier otra cosa.

HISTORIAL:
{history}

MENSAJE USUARIO: "{user_input}"

RESPUESTA (SOLO LA CATEGORÍA):
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
