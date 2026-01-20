## 2026-01-06 - [Timing Attack Prevention in API Key Validation]
**Vulnerability:** The API key verification in `ingestor.py` used a standard string comparison (`!=`). This allows an attacker to infer the API key character by character by measuring the time it takes for the comparison to fail.
**Learning:** Even in high-level languages like Python, simple equality checks for secrets can introduce timing side channels.
**Prevention:** Always use `secrets.compare_digest()` (or equivalent constant-time comparison functions) when validating API keys, tokens, or passwords.

## 2026-01-07 - [SSRF Prevention in URL Downloads]
**Vulnerability:** The `download_media` function blindly sent the `Authorization` header to any URL it was given. An attacker could potentially manipulate input to trigger a request to an external server (or internal resource) and capture the credentials (SSRF).
**Learning:** `requests` automatically handles redirects, but if the initial URL is not validated, or if code blindly trusts a URL param, it can be abused. Additionally, checking for domain suffixes (e.g. `endswith('facebook.com')`) is insufficient as it allows domains like `evilfacebook.com`.
**Prevention:** Explicitly validate URL schemes (`https`) and allowlist trusted domains using exact matches or proper subdomain checks (`.example.com`).

## 2026-01-08 - [HMAC Signature Verification for Webhooks]
**Vulnerability:** The WhatsApp webhook endpoint (`/webhook`) lacked signature verification, allowing any actor to spoof messages by sending a POST request with a valid payload structure.
**Learning:** Publicly accessible webhook endpoints must verify the origin of the request to prevent data injection and denial-of-service attacks. relying solely on a "verify token" (which is only used for the initial handshake) is insufficient for securing POST traffic.
**Prevention:** Implement HMAC-SHA256 signature verification using the App Secret for all incoming POST requests on webhook endpoints. Use `secrets.compare_digest` for secure comparison.
