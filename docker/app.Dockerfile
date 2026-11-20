# AI Command Centre — imagem da aplicação (frontend + backend). Created by Redfox using Claude
FROM node:24-bookworm-slim AS frontend
WORKDIR /f
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# Codex app-server oficial (openai/codex, release fixa) + bubblewrap para a
# sandbox. ADD --checksum falha a build se o SHA-256 não bater certo.
FROM python:3.15-slim AS codex
ARG CODEX_REL=https://github.com/openai/codex/releases/download/rust-v0.170.0
ADD --checksum=sha256:abcc363820de3c731b57f37bd05ef7e6a50a9de0ed1c13456d084dede95c5d00 \
    ${CODEX_REL}/codex-app-server-x86_64-unknown-linux-musl.tar.gz /dl/app-server.tar.gz
ADD --checksum=sha256:c4482289915f01babc2e5bbe2b097c667c547bfa942c0ec84cb3fa7bb08eae23 \
    ${CODEX_REL}/bwrap-x86_64-unknown-linux-musl.tar.gz /dl/bwrap.tar.gz
RUN mkdir -p /out && cd /dl && tar -xzf app-server.tar.gz && tar -xzf bwrap.tar.gz \
 && mv codex-app-server-x86_64-unknown-linux-musl /out/codex-app-server \
 && mv bwrap-x86_64-unknown-linux-musl /out/bwrap && chmod 755 /out/*

FROM python:3.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY --from=frontend /f/dist ./static
COPY --from=codex /out/ /app/bin/
COPY scripts/arranque.sh /app/arranque.sh
# Corre com o UID do dono de /data/ai-command-centre (1000), nunca como root.
USER 1000:1000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://%s:%s/api/health' % (os.environ.get('AICC_HOST','127.0.0.1'), os.environ.get('AICC_PORT','3000')),timeout=4).status==200 else 1)"
CMD ["/app/arranque.sh"]
