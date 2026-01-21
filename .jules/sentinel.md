## 2026-01-06 - [Timing Attack Prevention in API Key Validation]
**Vulnerability:** The API key verification in `ingestor.py` used a standard string comparison (`!=`). This allows an attacker to infer the API key character by character by measuring the time it takes for the comparison to fail.
**Learning:** Even in high-level languages like Python, simple equality checks for secrets can introduce timing side channels.
**Prevention:** Always use `secrets.compare_digest()` (or equivalent constant-time comparison functions) when validating API keys, tokens, or passwords.

## 2026-01-07 - [SSRF Prevention in URL Downloads]
**Vulnerability:** The `download_media` function blindly sent the `Authorization` header to any URL it was given. An attacker could potentially manipulate input to trigger a request to an external server (or internal resource) and capture the credentials (SSRF).
**Learning:** `requests` automatically handles redirects, but if the initial URL is not validated, or if code blindly trusts a URL param, it can be abused. Additionally, checking for domain suffixes (e.g. `endswith('facebook.com')`) is insufficient as it allows domains like `evilfacebook.com`.
**Prevention:** Explicitly validate URL schemes (`https`) and allowlist trusted domains using exact matches or proper subdomain checks (`.example.com`).

## 2026-01-21 - [Consistent Secret Comparison & None Safety]
**Vulnerability:** Webhook verification in `main.py` used `==` for token comparison and lacked explicit `None` checks, allowing potential timing attacks or `None` bypasses if config was missing.
**Learning:** Security fixes often get applied to new modules (`ingestor.py`) but miss legacy entry points (`main.py`). `None` propagation from `os.environ.get` can lead to `None == None` true conditions if not explicitly guarded.
**Prevention:** Audit all entry points for secret comparisons. Ensure `secrets.compare_digest` is used everywhere and wrap inputs in truthiness checks (`if token and expected and compare_digest(...)`).
