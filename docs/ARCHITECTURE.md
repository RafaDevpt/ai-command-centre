# Architecture

<!-- Created by Redfox using Claude -->

```
 browser / PWA (iPhone, PC)
        │  HTTP 127.0.0.1:3000 (Tailscale: only with approval, see INSTALLATION)
        ▼
 ┌──────────── aicc-app (host network, uid 1000, read-only rootfs) ─────────────┐
 │ FastAPI /api/* + WebSocket /api/ws/chat + static frontend (Vite build)       │
 │   ├── PostgreSQL over Unix socket ──► aicc-db (internal network, no TCP port)│
 │   ├── Ollama http://127.0.0.1:11434 (existing installation, untouched)       │
 │   ├── Unix socket run/codex ──► aicc-codex                                   │
 │   └── Unix socket run/claude ◄── official CLI runner on the host              │
 └──────────────────────────────────────────────────────────────────────────────┘
 ┌──────────── aicc-codex (outbound-only aicc_codex network, uid 1000) ──────────┐
 │ ponte_codex.py ──stdio──► official codex-app-server (rust-v0.170.0)           │
 │ sees only: agents/codex (credentials), projects (read-only), logs             │
 └──────────────────────────────────────────────────────────────────────────────┘
Claude Code: user's systemd runner on the host; only the project's Unix socket
is mounted in the app container. Claude.ai: separate official application
(shortcut + import of the official export).
```

## Decisions

1. **One container for frontend and backend.** FastAPI serves the Vite static
   build. Less memory; port 3000.
2. **Application on the host network.** Ollama listens only on 127.0.0.1 and
   changing this would require approval. The application can reach it without
   touching Ollama, and listens only on `AICC_HOST` (127.0.0.1).
3. **PostgreSQL without a TCP port.** `listen_addresses=''`; Unix socket in a
   volume (`database/socket`); internal `aicc_db` network; scram-sha-256 on the socket too.
4. **No Redis.** In-memory state only for ephemeral items (pending approvals,
   background tasks); everything else is in the database.
5. **Node.js only in containers.** No Node on the system.
6. **Migrations at startup.** `alembic upgrade head` before uvicorn.
7. **Codex in a separate container (phase 4).** Codex sandbox uses
   bubblewrap, which needs user namespaces; inside Docker this would require
   loosening seccomp or granting capabilities, which is not done. Instead the
   app-server runs in a container without access to the database, the database password or attachments (only its own Codex sign-in),
   with projects mounted read-only, no capabilities, read-only rootfs, `pids_limit`
   and 1 GB of memory. The application communicates with it over a Unix socket
   (directory mode 700) through `ponte_codex.py`, which starts an app-server per
   connection. The app-server is stopped after 15 minutes of inactivity.
8. **Codex binaries pinned and verified.** The image downloads the official
   release with `ADD --checksum=sha256:…`; the build fails if the hash changes.
9. **Approvals.** Codex requests (`item/commandExecution/requestApproval`,
   `item/fileChange/requestApproval`, `item/permissions/requestApproval` and the
   older versions) become `approvals` rows; Codex receives a response only after
   the user decides. No decision in 15 min ⇒ rejection. Unsupported requests
   (dynamic tools, MCP elicitation, attestation) are rejected.
10. **Agents and background collaboration** (`asyncio`), with state in the database.
    On startup, «a correr» (running) executions and collaborations become «erro
    (interrompida por reinício)» and pending approvals become «expirada».
11. **Memory.** User notes enter as approved; anything an agent proposes
    (`MEMÓRIA: …` lines) remains pending and is not added to the context until
    approved. Embeddings only on request, using the already installed `nomic-embed-text`.
12. **Context limited** to 6000 characters (instructions, approved memory,
    document excerpts) and the last 20 messages, because of the CPU.

13. **«Equipa» (Team)** (`equipa.py`). Codex coordinates → JSON plan (1–5 subtasks,
    each assigned by role) → Claude Code and local models execute in parallel
    (tasks for the same agent run in series) → Codex reviews, completes or requests
    corrections. Partial outputs and states are recorded in the existing board,
    so the panel can recover the state after a disconnection. Execution failures
    prevent completion; restarts mark active tasks as interrupted. Claude Code is
    called via the official CLI with `-p`, `--output-format stream-json`,
    `--verbose`, prompt on stdin and tools disabled. No Anthropic API, browser
    automation, cookies or proxies. Execution requires `claude` in the backend's
    PATH and use of the already authenticated official session. The backend
    communicates with `scripts/claude_runner.py` over the private
    `run/claude/claude.sock` socket. The runner uses the CLI and the user's session
    on the host; the container receives only the socket and never mounts the
    authentication directory. `aicc-claude-runner.service` keeps the runner active.
14. **Continuous Team conversations** (`team_conversations`, Alembic 0004).
    Each conversation belongs to the user, stores the transcript across tasks
    and has editable shared memory. The board supplied to Codex and members
    includes memory and previous results from that conversation only, with a
    context limit; the full transcript remains in the database. A compare-and-set
    reserves one turn at a time. On restart, orphaned runs become erro/interrompidas
    and the conversation is reopened. The parser accepts common aliases from
    model JSON, but validates exact names and rejects contradictory aliases.

## Data model (Alembic 0004)

`users`, `login_sessions`, `login_attempts`, `audit_log`, `projects`,
`chat_sessions`, `messages`, `project_documents`, `memory_items`, `agents`,
`agent_runs`, `collab_tasks`, `approvals`, `team_tasks`, `team_messages` and
`team_conversations`. Migration 0003 added `agents.role`; 0004 creates persistent
conversations, associates existing tasks with individual conversations and
adds the turn number. Streaming continues to update `team_messages`.
