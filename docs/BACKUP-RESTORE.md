# Backups

<!-- Created by Redfox using Claude -->

```bash
cd /data/ai-command-centre
./scripts/backup.sh
```

Creates in `backups/` (directory mode 700, files mode 600):
- `aicc-<data>.dump` — `pg_dump -Fc` of the database (without stopping anything);
- `aicc-ficheiros-<data>.tar.gz` — `.env`, `config/`, `projects/`,
  `attachments/`, `agents/codex/`. **Contains secrets** (database password,
  Codex credentials): store it like a password.

## Restore

```bash
docker compose stop app codex
tar -xzf backups/aicc-ficheiros-<data>.tar.gz          # in the project directory
docker compose exec -T db sh -c 'PGPASSWORD="$(cat /run/secrets/db_password)" pg_restore -h /var/run/postgresql -U aicc -d aicc --clean --if-exists' \
  < backups/aicc-<data>.dump
docker compose up -d
```

If `config/db_password` changed between backup and restore, restore `config/`
first and recreate the database from the dump.
