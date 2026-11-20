#!/bin/sh
# Cópia da BD (pg_dump) + ficheiros do AI Command Centre para backups/ (700).
# Não pára nada. Created by Redfox using Claude
set -eu
cd "$(dirname "$0")/.."
umask 077
data=$(date +%F-%H%M)
docker compose exec -T db sh -c 'PGPASSWORD="$(cat /run/secrets/db_password)" pg_dump -h /var/run/postgresql -U aicc -Fc aicc' \
  > "backups/aicc-$data.dump"
# Inclui as credenciais do Codex e config/: trate o ficheiro como uma palavra-passe.
tar -czf "backups/aicc-ficheiros-$data.tar.gz" .env config projects attachments agents/codex
ls -la "backups/aicc-$data.dump" "backups/aicc-ficheiros-$data.tar.gz"
