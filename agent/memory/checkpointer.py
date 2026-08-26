"""[SEMANA 4 — IMPLEMENTADO] Memoria de corto plazo con checkpointers (laboratorio 11).

El equipo debe implementar `build_checkpointer(backend)` retornando un
checkpointer de LangGraph que persista en disco (SqliteSaver o superior),
y conectar el CLI para que cada conversación use un `thread_id` propio.
"""


from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

def build_checkpointer(backend: str = "sqlite"):
    """Retorna un BaseCheckpointSaver según el backend: memory | sqlite | postgres."""
    if backend == "sqlite":
        import sqlite3
        conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
        return SqliteSaver(conn)
    elif backend == "memory":
        return MemorySaver()
    else:
        raise ValueError(f"Backend no soportado: {backend}")
