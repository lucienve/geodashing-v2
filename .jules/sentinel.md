## 2024-05-24 - [Fix Session Fixation in Verify Endpoint]
**Vulnerability:** The `backend/api/verify.php` endpoint authenticated users upon email verification without regenerating the session ID.
**Learning:** Session fixation was a risk when a user clicks an email verification link while utilizing a preexisting session, allowing an attacker who pre-set the session ID to hijack the authenticated session.
**Prevention:** Call `session_regenerate_id(true)` immediately prior to escalating session privileges or setting authenticated `$_SESSION` variables.
