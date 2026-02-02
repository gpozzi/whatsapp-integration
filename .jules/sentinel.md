## 2026-01-06 - [Timing Attack Prevention in API Key Validation]
**Vulnerability:** The API key verification in `ingestor.py` used a standard string comparison (`!=`). This allows an attacker to infer the API key character by character by measuring the time it takes for the comparison to fail.
**Learning:** Even in high-level languages like Python, simple equality checks for secrets can introduce timing side channels.
**Prevention:** Always use `secrets.compare_digest()` (or equivalent constant-time comparison functions) when validating API keys, tokens, or passwords.

## 2026-01-07 - [SSRF Prevention in URL Downloads]
**Vulnerability:** The `download_media` function blindly sent the `Authorization` header to any URL it was given. An attacker could potentially manipulate input to trigger a request to an external server (or internal resource) and capture the credentials (SSRF).
**Learning:** `requests` automatically handles redirects, but if the initial URL is not validated, or if code blindly trusts a URL param, it can be abused. Additionally, checking for domain suffixes (e.g. `endswith('facebook.com')`) is insufficient as it allows domains like `evilfacebook.com`.
**Prevention:** Explicitly validate URL schemes (`https`) and allowlist trusted domains using exact matches or proper subdomain checks (`.example.com`).

## 2026-02-02 - [Hybrid Webhook Signature Verification]
**Vulnerability:** The `whatsapp_webhook` endpoint handles both verified WhatsApp messages and unauthenticated Google Pub/Sub push messages (via payload detection). This creates a complexity where strictly enforcing signatures breaks the Pub/Sub flow if not handled carefully.
**Learning:** Hybrid endpoints that mix authenticated external traffic (WhatsApp) with internal traffic (Pub/Sub) are prone to security bypasses. Security logic must be applied *conditionally* based on the detected traffic type, but this increases the attack surface if the detection logic is spoofable.
**Prevention:** Ideally, separate the endpoints (`/webhook` for WhatsApp, `/pubsub-push` for Google). If impossible, enforce strict validation order: Check signature for everything unless it strictly matches the internal protocol format, and document the risk.
