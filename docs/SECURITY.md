# Security

<!-- Created by Redfox using Claude -->

## Containers
- Non-root (app and codex uid 1000; PostgreSQL uid 70 after startup),
  `no-new-privileges`, `cap_drop: ALL` (the database has only the capabilities
  its entrypoint needs), read-only rootfs in app and codex, memory limits,
  `pids_limit` in codex.
- No Docker socket in any container; no privileged mode; no published ports.
  Networks and volumes belong only to the `aicc` project; other server
  containers are untouched.
- PostgreSQL without a TCP port, internal network, password on the socket too.
- The Codex container cannot see the database, the database password or attachments (it holds only its own Codex sign-in, in `agents/codex`); projects
  are mounted read-only.

## Application
- Local login: argon2id, session in `HttpOnly` + `SameSite=Strict` cookie
  (`Secure` with HTTPS), token stored only as SHA-256, CSRF on all requests that
  change data and on every WebSocket message, WebSocket `Origin` check, 5 failures
  in 15 min ⇒ 429 (by IP and user), same response time for a non-existent user.
- Headers: CSP `default-src 'self'`, `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy: no-referrer`; no `/docs` or OpenAPI.
- The service worker never caches the API.
- Uploaded files: size limits (attachments 5 MB, documents 10 MB, Claude export
  100 MB), sanitised names, saved with mode 600.
- Project isolation: documents and memory can only be read/changed through the
  URL for that project; model context contains only the session's project.

## Agents and approvals
- Default profile (and only available one): **read-only**.
- Ollama agent: text only, no tools.
- Claude Code: official CLI in print mode, no tools and no session persistence;
  prompt sent via stdin, process error output discarded and never logged. Requires
  a `claude.ai`/`firstParty` session and removes API variables, environment
  tokens and proxies before execution. The CLI runs in a separate host service;
  the app container sees only the private Unix socket inside the project, never
  the authentication directory. Authentication remains under the CLI's control.
- Codex: `sandbox: read-only`, `approvalPolicy: untrusted`; any command,
  file change or permissions request goes through Approvals. The decision is
  recorded in the audit log (who, when).
- Memory proposed by agents remains pending until approved.

## Secrets
- `.env` (600), `config/` (700), `agents/codex/` (700); none of these go into
  git, the database, logs or API responses. The ChatGPT account email is masked
  (`r***@dominio`).

## Providers
- Official authentication only. No browser cookies, extracted tokens,
  unofficial proxies or claude.ai automation. Claude Code uses the authenticated
  first-party CLI; runtime needs access to the executable and session without
  copying credentials into the application, database or logs.
