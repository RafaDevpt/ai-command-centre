# Changelog

<!-- Created by Redfox using Claude -->

## 0.4.0 — 2026-11-20 — Team with Claude Code
- First public release: English documentation, CI (backend, migrations, frontend,
  Compose), security policy, contribution guide and issue templates.
- Claude Code runner hardened: no MCP servers, user settings, plugins or slash
  commands, and an empty temporary working directory per request.
- Integration of the official Claude Code CLI with prompt on stdin,
  `stream-json` events, tools disabled and no session persistence.
- Live board by agent, assignment links, reconnection by querying persisted
  state and explicit errors for interrupted or failed members.
- No new migration; the board uses existing `team_messages`.
- New default **Collaboration** entry, with agent graph, request composer
  and event inspector linked to the edges.
- Claude runner isolated on the host, accessible to the container over a
  private Unix socket inside the project.
- Claude Code in `stream-json --verbose` and button to retry failed or
  interrupted tasks without losing the original error from the history.
- Coordinator sessions accept JSON aliases used in review responses;
  unknown or contradictory assignments fail explicitly.
- Continuous conversation with persistent history, editable memory shared
  between Codex/Claude/local models and reservation of one turn per conversation.
- Migration 0004 associates existing history with individual conversations and
  retains legacy history; agent context is isolated by conversation.
- Failures during worker setup or cancellation release the conversation and
  record the task as erro/interrompida, without leaving it stuck running.
- The interface starts in **Collaboration**, shows chat turns and allows saved
  conversations to resume; periodic refresh recovers database state.

## 0.3.0 — 2026-11-19 — Team
- **«Equipa» (Team) page:** multiple agents on a shared objective without
  intervention; the coordinator (Codex/ChatGPT by default) divides, assigns,
  reviews and completes; shared board, user notes, stop, up to 6 rounds.
- Agents: create and delete, editable role (used by the coordinator). Default
  roles: Codex plans and coordinates; Ollama (Qwen) handles basic tasks.
- Healthcheck at the address configured in `AICC_HOST` (allows listening on
  another address, for example the Tailscale one).
- Manual bridge to Claude: briefing for Claude Code and pasted response,
  with coordinator resume.
- Migration 0003; 44 tests.

## 0.2.0 — 2026-11-19 — Phases 2 to 7
- **Phase 2 (authentication):** local user (CLI), argon2id, sessions in
  secure cookie, CSRF, attempt limit, devices, password change.
- **Phase 3 (conversation):** sessions, messages and attachments in the database;
  unified conversation over WebSocket with streaming and «parar» (stop); history
  search; archive; models page (installed models only); dashboard with status and resources.
- **Phase 4 (Codex):** official rust-v0.170.0 app-server in an isolated container,
  «Sign in with ChatGPT» login by device code, models, conversation with resumable
  threads, approval requests linked to Approvals.
- **Phase 5 (work):** projects (instructions, documents, search), memory with
  pending proposals and on-demand embeddings, Codex and Ollama agents (read-only),
  analysis → review → comparison → consolidation collaboration, approvals page and audit log.
- **Phase 6 (Claude):** shortcut, import of the official export (ZIP/JSON) as
  read-only sessions, manual record of external sessions.
- **Phase 7:** recovery after restart (approvals, runs and orphaned collaborations),
  `scripts/backup.sh`, documentation, 37 tests.

## 0.1.0 — 2026-11-19 — Phase 1 (foundations)
- Project structure, git, Compose `aicc` with its own network.
- FastAPI backend: `/api/health`, `/api/health/ready`, serves the frontend,
  security headers, Alembic (`0001`: audit_log).
- React 19 + Vite 8 + TS frontend: dark shell, dashboard, PWA, Claude shortcut.
- PostgreSQL 17 without a TCP port (Unix socket), internal network.
