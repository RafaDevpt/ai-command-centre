# Authentication

<!-- Created by Redfox using Claude -->

## Command Centre
- Local user created on the command line (never through the web):
  `docker compose exec app python -m app.cli criar-utilizador <nome>`;
  reset: `… repor-senha <nome>`. Password of 12+ characters, argon2id.
- 7-day session in `aicc_sessao` cookie (`HttpOnly`, `SameSite=Strict`,
  `Secure` with HTTPS). In «Definições» (Settings), you can see devices with
  active sessions and end the others; changing the password ends other sessions.
- CSRF: the token is returned by `/api/auth/me` and sent in the `X-CSRF-Token` header.

## Codex («Sign in with ChatGPT»)
- Settings → Providers → «Iniciar sessão com ChatGPT» (Sign in with ChatGPT).
- The server requests a device code from the official app-server
  (`account/login/start`, `type: chatgptDeviceCode`). The page shows the
  address `https://auth.openai.com/codex/device` and the code; open it on
  any device, sign in to your OpenAI account and enter the code.
- Credentials are stored in `agents/codex/` (CODEX_HOME, 700, stored in
  a file), only inside the `codex` container. The API returns only: session
  status / plan / masked email.
- «Terminar sessão do Codex» (Sign out of Codex) calls `account/logout`.

## Claude
- No login integration. Shortcut to https://claude.ai and import of the
  official export (see PROVIDERS).
