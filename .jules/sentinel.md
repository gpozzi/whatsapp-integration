## 2026-01-06 - [Timing Attack Prevention in API Key Validation]
**Vulnerability:** The API key verification in `ingestor.py` used a standard string comparison (`!=`). This allows an attacker to infer the API key character by character by measuring the time it takes for the comparison to fail.
**Learning:** Even in high-level languages like Python, simple equality checks for secrets can introduce timing side channels.
**Prevention:** Always use `secrets.compare_digest()` (or equivalent constant-time comparison functions) when validating API keys, tokens, or passwords.

## 2026-01-07 - [SSRF Prevention in URL Downloads]
**Vulnerability:** The `download_media` function blindly sent the `Authorization` header to any URL it was given. An attacker could potentially manipulate input to trigger a request to an external server (or internal resource) and capture the credentials (SSRF).
**Learning:** `requests` automatically handles redirects, but if the initial URL is not validated, or if code blindly trusts a URL param, it can be abused. Additionally, checking for domain suffixes (e.g. `endswith('facebook.com')`) is insufficient as it allows domains like `evilfacebook.com`.
**Prevention:** Explicitly validate URL schemes (`https`) and allowlist trusted domains using exact matches or proper subdomain checks (`.example.com`).

## 2026-01-31 - [Webhook Signature Verification & Dual-Purpose Endpoints]
**Vulnerability:** The WhatsApp webhook endpoint accepted POST requests without verifying the `X-Hub-Signature-256`, allowing attackers to spoof messages. The endpoint also supported Google Pub/Sub Pushes, creating a bypass risk if verification logic relied solely on `User-Agent`.
**Learning:** Shared endpoints (e.g., WhatsApp + Pub/Sub) require careful authentication layering. A simple `User-Agent` check for bypass is insecure. Verification logic must align with the payload structure and processing path (i.e., only bypass if the payload is actually processed as Pub/Sub).
**Prevention:** Always verify webhook signatures. For dual-purpose endpoints, ensure authentication bypasses are tightly coupled to the alternative logic path (e.g., successful payload parsing) and not just request headers.
