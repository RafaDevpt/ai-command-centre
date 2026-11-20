# Installation

<!-- Created by Redfox using Claude -->

Requirements: Docker Engine + Compose v2 (with BuildKit). No system packages.

```bash
cd /data/ai-command-centre
./scripts/primeira-vez.sh
docker compose up -d --build                   # db, app, codex
docker compose exec app python -m app.cli criar-utilizador <nome>
docker compose ps
```

Update: `docker compose up -d --build` (only recreates the `aicc-*` containers).
Stop: `docker compose stop`. Logs: `docker compose logs -f app codex`;
Codex app-server log: `logs/codex-app-server.log`.

## Access from other devices

By default, the application listens only on `127.0.0.1:3000`. Never expose it
to the Internet. Options, from most secure to least:

1. **SSH tunnel** (no changes): `ssh -L 3000:127.0.0.1:3000 <servidor>` and
   open http://127.0.0.1:3000.
2. **Tailscale Serve with HTTPS** (recommended for a phone; the PWA and
   `Secure` cookies need HTTPS): enable HTTPS certificates in the Tailscale
   console and then run
   `tailscale serve --bg --https=8443 http://127.0.0.1:3000`. It is accessible
   only inside the tailnet, at `https://<máquina>.<tailnet>.ts.net:8443`.
3. **Listen on the Tailscale IP** (`AICC_HOST=<ip-tailscale>` in `.env`, then
   `docker compose up -d app`): HTTP only, encrypted by Tailscale. It works in
   the phone browser, but the PWA will not install and cookies will not be `Secure`.

On iPhone (option 2): open the address in Safari → Share → «Adicionar ao
ecrã principal» (Add to Home Screen).

## Claude Code as a team member (optional)

Claude Code runs **on the host**, using the session that is already signed in
(`claude` → sign in with the claude.ai account). The backend communicates with
it over a Unix socket through `scripts/claude_runner.py`:

```bash
mkdir -p ~/.config/systemd/user run/claude && chmod 700 run/claude
cp scripts/aicc-claude-runner.service ~/.config/systemd/user/   # adjust paths if needed
systemctl --user daemon-reload && systemctl --user enable --now aicc-claude-runner
```

Then, in Agents, create an agent with the `claude-code` provider.
