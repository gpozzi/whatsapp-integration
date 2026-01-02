# 🤖 AutoBot: Tu Asistente de Ventas con Auto-Mejora (Vertex AI)

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)
![Google Cloud](https://img.shields.io/badge/Google_Cloud-Run-red?style=for-the-badge&logo=google-cloud)
![WhatsApp](https://img.shields.io/badge/WhatsApp-Business_API-success?style=for-the-badge&logo=whatsapp)
![Vertex AI](https://img.shields.io/badge/Vertex_AI-Gemini_2.5-orange?style=for-the-badge&logo=google)

**AutoBot** es un asistente virtual de última generación para WhatsApp, diseñado no solo para vender autos, sino para **aprender de sus errores**. Utiliza una arquitectura de **IA Híbrida** con Google Vertex AI, combinando modelos potentes para ventas y modelos ligeros para supervisión y seguridad.

---

## 🏛️ Arquitectura Técnica

El sistema opera en una arquitectura **Serverless** sobre Google Cloud Run, diseñada para alta disponibilidad, seguridad y bajo coste.

### Componentes Principales

- **`main.py` (The Gatekeeper):**
  - **Webhook:** Gestiona el handshake y recepción de mensajes de Meta.
  - **Seguridad:** Implementa sanitización de inputs (límite de 1000 caracteres) y tiempos de espera estrictos (10s).
  - **Idempotencia:** Evita el procesamiento de mensajes duplicados o reintentos antiguos (>5 minutos).

- **`brain.py` (The Core / Router):**
  - **Router Inteligente:** Clasifica la intención del usuario antes de actuar.
  - **Gestor de Contexto:** Ventana deslizante de ~4000 caracteres con filtrado de "higiene" (elimina errores técnicos del historial).
  - **Orquestador de IA:** Decide qué modelo usar según la tarea.

- **`config.py`:** Centraliza configuración, prompts y validación de variables (ej. LangSmith).

### 🔄 Flujo de Datos Detallado

```mermaid
graph TD
    User([👤 Usuario]) <-->|Mensaje| WA[📱 Meta API]
    WA <-->|Webhook POST| CR[☁️ Google Cloud Run]

    subgraph "AutoBot Brain (brain.py)"
        CR -->|Procesa Entrada| Router{🔀 Clasificador de Intención}

        Router -->|Consulta de Ventas| Agent[🤖 Sales Agent\n(Gemini 2.5 Flash)]
        Router -->|Feedback Negativo| Analyst[🧐 Failure Analyst\n(Gemini 2.5 Lite)]
        Router -->|Feedback Positivo| Simple[✅ Simple Ack]

        Agent <-->|Lees/Escribe| Hist[(🗄️ Firestore\nHistorial)]
        Agent <-->|Lee Inventario| Sheets[(📊 Google Sheets)]

        Analyst -->|Guarda Insight| Insights[(💡 Firestore\nInsights)]
    end

    Agent -->|Genera Respuesta| Auditor[🛡️ Safety Auditor\n(Gemini 2.5 Lite)]
    Auditor -->|Aprobado| CR
    Analyst -->|Respuesta Empática| CR
    Simple -->|Respuesta| CR
```

---

## ✨ Características Clave

### 1. Estrategia "Dual Model" 🧠⚡
Optimizamos costes y latencia usando dos versiones de Gemini:
- **Gemini 2.5 Flash:** El "cerebro pesado". Se encarga de la lógica de ventas, filtrado de DataFrames y consultas complejas de inventario.
- **Gemini 2.5 Flash-Lite:** El "cerebro ágil". Se encarga de tareas auxiliares de alta velocidad y bajo coste:
    - Clasificación de Intención.
    - Auditoría de Seguridad (Safety Checks).
    - Análisis de Feedback y decisión de cuándo pedir retroalimentación.

### 2. Sistema de Auto-Mejora (Self-Improvement Loop) 🔄
El bot aprende de las interacciones fallidas:
1. Si el bot da una respuesta compleja, pregunta: *"¿Te sirvió esta info?"*.
2. Si el usuario responde **"NO"**, el sistema activa el **Failure Analyst**.
3. El analista revisa el historial, diagnostica qué falló (ej. "No entendió el filtro de precio") y guarda el **Insight** en la colección `bot_insights` de Firestore.
4. Responde al usuario con empatía y pide reformular.

### 3. Fiabilidad Empresarial 🛡️
- **Idempotencia:** Cada `message_id` se registra en Firestore (`processed_messages`) para evitar respuestas dobles ante reintentos de WhatsApp.
- **Timeouts Estrictos:** Las peticiones a la API de WhatsApp mueren a los 10 segundos para no bloquear el hilo de ejecución.
- **Context Hygiene:** El historial se limpia de mensajes de error internos para no "confundir" al modelo en turnos siguientes.

---

## 🛠️ Configuración

### Variables de Entorno

| Variable | Descripción | Requerido |
| :--- | :--- | :---: |
| `GCP_PROJECT` | ID de tu proyecto Google Cloud. | ✅ |
| `VERIFY_TOKEN` | Token secreto para el Webhook de Meta. | ✅ |
| `WHATSAPP_TOKEN` | Token de acceso (Permanent) de WhatsApp API. | ✅ |
| `PHONE_NUMBER_ID` | ID del número de teléfono (WhatsApp Business). | ✅ |
| `SPREADSHEET_ID` | ID del Google Sheet con el inventario. | ✅ |
| `LOCATION` | Región de ejecución (Default: `us-central1`). | ❌ |
| `DATABASE_NAME` | Nombre de la DB Firestore (Default: `(default)`). | ❌ |
| `LANGCHAIN_TRACING_V2`| Set a `true` para activar trazas en LangSmith. | ❌ |
| `LANGCHAIN_API_KEY` | API Key de LangSmith (debe empezar con `ls-`). | ❌ |

---

## 🚀 Despliegue

El despliegue es automático gracias a Google Cloud Buildpacks.

```bash
# 1. Autentícate
gcloud auth login

# 2. Despliega en Cloud Run (desde la raíz)
gcloud run deploy autobot \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars VERIFY_TOKEN=tu_secreto,WHATSAPP_TOKEN=token_meta,SPREADSHEET_ID=id_sheet
```

---

*Desarrollado con ❤️ y Python.*
