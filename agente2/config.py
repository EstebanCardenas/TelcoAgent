"""Configuración del Asesor de Retención.

Se lee de variables de entorno. El nombre del modelo no se escribe en el código.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    db_path: str
    ollama_model: str
    ollama_base_url: str
    ollama_num_ctx: int
    api_base_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        host=os.getenv("AGENTE2_HOST", "127.0.0.1"),
        port=int(os.getenv("AGENTE2_PORT", "8090")),
        db_path=os.getenv("AGENTE2_DB_PATH", "data/retencion.sqlite"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
        api_base_url=os.getenv("API_BASE_URL", "http://localhost:8080"),
    )
