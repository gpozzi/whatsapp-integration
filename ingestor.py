import json
import logging
import config
from google.cloud import firestore
# Conditional import to allow tests to run without the actual package installed if needed,
# though we just installed it.
try:
    from google.cloud.firestore import Vector
except ImportError:
    # Fallback or mock if testing in an environment without the library
    Vector = lambda x: x

from langchain_google_vertexai import VertexAIEmbeddings

def sync_inventory(request):
    """
    Maneja la sincronización del inventario.
    Recibe JSON, genera embeddings y guarda en Firestore Vector Search.
    """
    # 1. Seguridad: Verificar API Key
    api_key = request.headers.get("X-API-KEY")
    if not api_key or api_key != config.SYNC_API_KEY:
        config.logger.warning("⛔ Intento de acceso no autorizado a /sync-inventory")
        return "Unauthorized", 401

    if request.method != "POST":
        return "Method Not Allowed", 405

    try:
        # 2. Parsear Datos
        data = request.get_json()
        if not data:
            return "Bad Request: No JSON provided", 400

        # Validar campos mínimos (opcional, pero recomendado)
        # Asumimos que data es un diccionario simple del auto

        # 3. Generar Texto para Embedding
        # Concatenamos campos relevantes para la búsqueda semántica
        # Ej: "Toyota Corolla 2020 Blanco Sedan 20000 USD"
        text_parts = []
        for key, value in data.items():
            if key not in ["id", "embedding_field"]: # Ignorar IDs o campos técnicos
                text_parts.append(f"{value}")

        text_to_embed = " ".join(text_parts)
        config.logger.info(f"🧬 Generando embedding para: {text_to_embed[:50]}...")

        # 4. Generar Embedding con Vertex AI
        embeddings_service = VertexAIEmbeddings(
            model_name="text-embedding-004",
            project=config.PROJECT_ID,
            location=config.LOCATION
        )
        vector_values = embeddings_service.embed_query(text_to_embed)

        # 5. Guardar en Firestore
        db = firestore.Client(project=config.PROJECT_ID, database=config.DATABASE_NAME)
        collection_ref = db.collection("inventory_vectors")

        # Preparar documento
        doc_data = data.copy()
        doc_data["embedding_field"] = Vector(vector_values)
        doc_data["text_representation"] = text_to_embed # Útil para depuración o keyword search simple

        # Usar un ID específico si viene en los datos, sino auto-id
        doc_id = str(data.get("id", "")) if data.get("id") else None

        if doc_id:
            collection_ref.document(doc_id).set(doc_data)
            config.logger.info(f"✅ Auto actualizado en inventario: {doc_id}")
        else:
            new_ref = collection_ref.add(doc_data)
            config.logger.info(f"✅ Auto agregado al inventario: {new_ref[1].id}")

        return "Inventory Synced", 200

    except Exception as e:
        config.logger.error(f"❌ Error en sync_inventory: {e}", exc_info=True)
        return f"Internal Server Error: {str(e)}", 500
