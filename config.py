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
