# Troubleshooting

<!-- Created by Redfox using Claude -->

- **`/api/health/ready` returns 503:** the database is not responding. `docker compose ps`,
  `docker compose logs db`.
- **Ollama «ok: false»:** `curl http://127.0.0.1:11434/api/version` on the server;
  the Ollama user service may be stopped (it is not managed here).
- **Ollama response is slow at first:** the model is loading (CPU); with
  `OLLAMA_MAX_LOADED_MODELS=1`, switching models unloads the previous one.
- **Codex «não disponível»:** `docker compose ps codex`; the socket is
  `run/codex/codex.sock`. `docker compose restart codex` does not affect the app.
- **Codex «Sem sessão no Codex»:** Settings → Sign in with ChatGPT.
- **Codex: limit reached** (common on the Go plan): wait for the period to renew;
  there is no supported way to bypass it.
- **Approved command failed with a sandbox error:** expected in this version
  (see PROVIDERS → Codex). Codex has read-only access to projects.
- **Approval «expirada»:** no one decided within 15 min, or the server restarted.
- **Collaboration «erro — interrompida por reinício»:** start it again.
- **Too many attempts (429):** wait 15 min or reset the password on the command line.
- **Port 3000 is in use:** change `AICC_PORT` in `.env` and run `docker compose up -d`.
- **Blank page after update:** the service worker has cached the old shell; reload twice.
