#!/bin/sh
# Prepara segredos e pastas na primeira instalação. Não reescreve nada que exista.
# Created by Redfox using Claude
set -e
cd "$(dirname "$0")/.."
mkdir -p run/codex && chmod 700 config agents/codex backups run run/codex
[ -f .env ] || { cp .env.example .env; chmod 600 .env; echo "criado .env"; }
if [ ! -f config/db_password ]; then
  umask 077; head -c 32 /dev/urandom | base64 | tr -d '/+=' > config/db_password
  # 644 dentro de config/ (700): o PostgreSQL (uid 70) lê-o pelo segredo do Compose;
  # nenhum outro utilizador do servidor chega à pasta.
  chmod 644 config/db_password; echo "criada config/db_password"
fi
mkdir -p database/pgdata database/socket && chmod 700 database
echo "pronto"
