# Providers

<!-- Created by Redfox using Claude -->

| Provider | How | Status |
|---|---|---|
| Ollama | Local API 127.0.0.1:11434, installed models only (never `pull`/`delete`) | integrated |
| OpenAI Codex | Official app-server (JSON-RPC over stdio), «Sign in with ChatGPT» | integrated; login required |
| Claude Code | Official `claude` CLI, first-party session already authenticated | integrated for team tasks, no API |
| Claude | Separate official application | shortcut + export import |

## Ollama
- Streaming `/api/chat`, `think: false`, `num_ctx` 4096, `keep_alive` 2 min.
- `OLLAMA_MAX_LOADED_MODELS=1` (existing configuration): using a model here
  may unload the model another server application is using.
- Embeddings only on request with `nomic-embed-text` (Projects → Index).

## Codex
- Release `rust-v0.170.0`, `codex-app-server` and `bwrap` binaries verified
  by SHA-256 at build time.
- Threads in `sandbox: read-only`, `approvalPolicy: untrusted`, `cwd` in
  `projects/<id>` (or `projects/_geral`). The thread id is kept in the session
  for resuming (`thread/resume`); if it no longer exists, a new one starts and a warning is shown.
- The model list comes from `model/list` (1 h cache).
- The bubblewrap sandbox does not work inside Docker (no user namespaces); the
  isolation is provided by the `codex` container (see ARCHITECTURE, decision 7).
  Approved commands may therefore fail with a sandbox error; Docker is not
  loosened to avoid this.

## Codex and the ChatGPT Go plan
- OpenAI includes Go among the plans with Codex, with lower limits than Plus/Pro
  and subject to availability; when the limit is reached, requests fail until
  the period renews. There is no supported way to bypass this and this project
  does not attempt to.
- The app-server documentation allows ChatGPT authentication in local or open
  source applications (this is the case: personal use on your server), but not
  in commercial services or services hosted for third parties.
- **Your account's actual eligibility can only be confirmed when you sign in**:
  after sign-in, the dashboard shows the plan (`go`, `plus`, …). Tested up to the
  point requiring the user: the device code is issued.

## Claude
- **Automatic team member:** Claude Code receives tasks through the official CLI
  (`claude -p --output-format stream-json --verbose`), with the prompt on stdin,
  `--no-session-persistence` and tools disabled. Partial output is streamed to
  the persistent board. It uses first-party authentication already configured
  in the CLI, validates that the session is `claude.ai`/first-party and removes
  API variables, environment tokens and proxies; no credentials are read or
  logged and no paid Anthropic API, browser, cookies or proxy is used. CLI errors
  remain visible and do not count as a completed task.
- **Execution on the server:** `scripts/claude_runner.py` is a user systemd
  service; it runs the CLI installed on the host and exposes only a private Unix
  socket in the project's `run/claude` directory. The `app` container mounts
  that socket; it does not receive the CLI or authentication directory. The unit
  is in `scripts/aicc-claude-runner.service` and is enabled with
  `systemctl --user link` and `systemctl --user enable --now aicc-claude-runner.service`.
- «Abrir Claude» (Open Claude) button (sidebar and Settings) for https://claude.ai.
- Import of the official export (claude.ai → Settings → Privacy → Export data):
  ZIP or `conversations.json`. Conversations are in Sessions → External,
  read-only; reimport does not duplicate them (by `uuid`).
- Manual record of a session (title, `https://claude.ai/…` link, notes).
- **Manual bridge in Team:** «Gerar briefing» (Generate briefing) keeps the
  manual workflow (objective, plan, work done, notes, request: code + tests) to
  paste into Claude Code; the pasted response enters the board as «Claude» and,
  if the task had already finished, the coordinator resumes (up to 2 extra rounds).
  The manual workflow also works without the CLI available at runtime.
- There is no browser automation, cookie, token or proxy reading, and Claude
  account status/limits are not shown because there is no official way to obtain them.
