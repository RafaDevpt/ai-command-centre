"""
Configuração lida do ambiente (.env), nunca do código. Os segredos (palavra-
passe da BD, chave de sessão) vêm de ficheiros com permissões 600.

Created by Redfox using Claude
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AICC_", env_file=None, extra="ignore")

    #: Onde o servidor HTTP escuta. Por omissão só no próprio servidor.
    host: str = "127.0.0.1"
    port: int = 3000
    #: Pasta de dados persistentes (montada no contentor).
    data_dir: Path = Path("/data/ai-command-centre")
    #: PostgreSQL por socket Unix partilhado num volume: sem porta TCP nenhuma.
    db_socket_dir: str = "/run/aicc-db"
    db_name: str = "aicc"
    db_user: str = "aicc"
    db_password_file: Path = Path("/run/secrets/db_password")
    #: Ollama já instalado no anfitrião, só em localhost.
    ollama_url: str = "http://127.0.0.1:11434"
    #: Pasta das ficheiros estáticos do frontend (build do Vite).
    static_dir: Path = Path("/app/static")
    log_level: str = "info"
    #: Só para testes: URL completo da BD (sobrepõe o socket).
    database_url: SecretStr | None = Field(default=None)

    def url_bd(self) -> str:
        if self.database_url:
            return self.database_url.get_secret_value()
        senha = self.db_password_file.read_text(encoding="utf-8").strip()
        return (f"postgresql+psycopg://{self.db_user}:{senha}@/{self.db_name}"
                f"?host={self.db_socket_dir}")


@lru_cache
def settings() -> Settings:
    return Settings()
