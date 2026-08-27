"""[SEMANA 4 — IMPLEMENTADO] Memoria de corto plazo con checkpointers (laboratorio 11).

El equipo debe implementar `build_checkpointer(backend)` retornando un
checkpointer de LangGraph que persista en disco (SqliteSaver o superior),
y conectar el CLI para que cada conversación use un `thread_id` propio.
"""

import asyncio
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver


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
        conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
        return AsyncSqliteSaver(conn)
    elif backend == "memory":
        return MemorySaver()
    else:
        raise ValueError(f"Backend no soportado: {backend}")
