"""[SEMANA 4] Memoria de corto plazo con checkpointers (laboratorio 11).

Persiste el estado de cada conversación en disco, indexado por `thread_id`, para
que sobreviva al reinicio del CLI. El complemento de largo plazo está en
`store.py`.
"""

import asyncio
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

# Relativo al cwd (`/app` en Docker). El compose monta un volumen en `data/`
# para que el archivo sobreviva a `docker compose run --rm`.
RUTA_CHECKPOINTS = Path("data") / "checkpoints.sqlite"


class AsyncSqliteSaver(SqliteSaver):
    """SqliteSaver que soporta métodos asíncronos delegando al hilo de ejecución."""

    async def aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        return await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        return await asyncio.to_thread(self.list, config, filter=filter, before=before, limit=limit)


def build_checkpointer(backend: str = "sqlite"):
    """Retorna un BaseCheckpointSaver según el backend: memory | sqlite | postgres."""
    if backend == "sqlite":
        RUTA_CHECKPOINTS.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(RUTA_CHECKPOINTS), check_same_thread=False)
        return AsyncSqliteSaver(conn)
    elif backend == "memory":
        return MemorySaver()
    else:
        raise ValueError(f"Backend no soportado: {backend}")
