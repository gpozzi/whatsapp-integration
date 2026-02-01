## 2026-01-06 - [Timing Attack Prevention in API Key Validation]
**Vulnerability:** The API key verification in `ingestor.py` used a standard string comparison (`!=`). This allows an attacker to infer the API key character by character by measuring the time it takes for the comparison to fail.
**Learning:** Even in high-level languages like Python, simple equality checks for secrets can introduce timing side channels.
**Prevention:** Always use `secrets.compare_digest()` (or equivalent constant-time comparison functions) when validating API keys, tokens, or passwords.

## 2026-01-07 - [SSRF Prevention in URL Downloads]
**Vulnerability:** The `download_media` function blindly sent the `Authorization` header to any URL it was given. An attacker could potentially manipulate input to trigger a request to an external server (or internal resource) and capture the credentials (SSRF).
**Learning:** `requests` automatically handles redirects, but if the initial URL is not validated, or if code blindly trusts a URL param, it can be abused. Additionally, checking for domain suffixes (e.g. `endswith('facebook.com')`) is insufficient as it allows domains like `evilfacebook.com`.
**Prevention:** Explicitly validate URL schemes (`https`) and allowlist trusted domains using exact matches or proper subdomain checks (`.example.com`).

## 2026-02-01 - [Webhook Signature Verification Missing]
**Vulnerability:** The WhatsApp webhook endpoint accepted POST requests without verifying the `X-Hub-Signature-256` header, allowing any attacker to impersonate WhatsApp and inject fake messages.
**Learning:** Checking for the presence of a configuration variable (like `APP_SECRET`) is not enough; the verification logic itself must be implemented and enforced. Also, dual-purpose endpoints (serving both external webhooks and internal Pub/Sub) require careful bypassing logic to avoid breaking internal flows while securing external ones.
**Prevention:** Implement HMAC-SHA256 signature verification for all public webhooks. Use `secrets.compare_digest` for comparison. Ensure tests explicitly cover "missing signature" and "invalid signature" scenarios.
