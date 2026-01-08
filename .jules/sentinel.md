## 2026-01-08 - [Timing Attack Prevention in Webhook Verification]
**Vulnerability:** The WhatsApp webhook verification in `main.py` used `request.args.get("hub.verify_token") == config.VERIFY_TOKEN`. This simple string comparison is susceptible to timing attacks, where an attacker can infer the token character by character.
**Learning:** Security-sensitive string comparisons (API keys, tokens, passwords) must always use constant-time algorithms.
**Prevention:** Replaced the comparison with `secrets.compare_digest(token, expected_token)`, which takes the same amount of time regardless of where the mismatch occurs. Also handled potential `None` values to prevent errors.
