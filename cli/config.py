"""Configuración central del proyecto.

Todo se lee de variables de entorno (con `.env` cargado vía python-dotenv).
El nombre del modelo NUNCA se escribe directamente en el código del agente:
siempre se accede a través de `get_settings().ollama_model`, de modo que el
agente funcione con cualquier modelo servido por Ollama. Cada equipo elige el
suyo (laboratorio de LLM Fit) y lo escribe en su propio `.env` — no aquí:
este archivo es infraestructura y no debería necesitar cambios.

Los valores por defecto de abajo (`qwen2.5:3b`, etc.) NO son una imposición de
modelo: son el fallback que usa el CI, que nunca tiene un `.env` disponible.
Si un default queda vacío, `test_configuracion_disponible` falla en el
pipeline aunque el proyecto funcione perfecto en su máquina.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ollama_model: str
    ollama_base_url: str
    ollama_num_ctx: int
    api_base_url: str
    caso_negocio: str
    grupo: str
    langsmith_tracing: bool
    langsmith_project: str
    # RAG (base documental institucional, servicio central de la Universidad)
    rag_base_url: str
    rag_email: str
    rag_password: str
    rag_collection: str
    # URL del Asesor de Retención (Agente 2). El Agente 1 la usa en A2A.
    agente2_base_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
        api_base_url=os.getenv("API_BASE_URL", "http://localhost:8080"),
        caso_negocio=os.getenv("CASO_NEGOCIO", "telecom"),
        grupo=os.getenv("GRUPO", "00"),
        langsmith_tracing=os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true",
        langsmith_project=os.getenv("LANGCHAIN_PROJECT", ""),
        rag_base_url=os.getenv("RAG_BASE_URL", ""),
        rag_email=os.getenv("RAG_EMAIL", ""),
        rag_password=os.getenv("RAG_PASSWORD", ""),
        rag_collection=os.getenv("RAG_COLLECTION", ""),
        agente2_base_url=os.getenv("AGENTE2_BASE_URL", "http://localhost:8090"),
    )
