# Contributing to AI Command Centre

<!-- Created by Redfox using Claude -->

## Layout

| Path | What lives there |
| :--- | :--- |
| `backend/app/` | FastAPI application: routes (`rotas_*.py`), providers (`ollama.py`, `codex.py`, `claude_code.py`), team orchestrator (`equipa.py`) |
| `backend/alembic/versions/` | Database migrations — one per schema change, never edited after release |
| `backend/tests/` | pytest suite with fake Ollama, Codex and Claude |
| `frontend/src/` | React + TypeScript; one file per page in `paginas/` |
| `scripts/` | First run, start-up, backup and the Claude Code runner |
| `docs/` | Documentation, kept in sync with the code |

Code identifiers and comments are in European Portuguese; documentation is in
British English.

## Branches

Short-lived branches off `main`, one topic each, merged by pull request and
deleted on merge:

| Prefix | For |
| :--- | :--- |
| `feat/…` | new functionality |
| `fix/…` | bug fixes |
| `security/…` | security fixes |
| `docs/…` | documentation only |

`main` is protected: CI (backend, frontend and Compose checks) must be green
before a merge.

## Checks to run locally

```bash
cd backend && .venv/bin/python -m pytest -q && uvx ruff check app tests
cd frontend && npm run build && npm run lint
docker compose config -q
```

## Rules that do not bend

- **Official sign-in only.** No browser cookies, extracted tokens, unofficial
  proxies or automation of provider websites.
- **No secrets in the repository, the database, logs or API responses.**
  `.env`, `config/` and `agents/codex/` are ignored for a reason.
- **Agents stay read-only by default.** Anything that changes files, runs
  commands, installs software or changes configuration goes through Approvals.
- **No personal data** — hostnames, IP addresses, usernames or real documents —
  in code, tests, screenshots or issues.
- Every schema change ships with a migration and a test.
- User-visible changes get a CHANGELOG entry.
