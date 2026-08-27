"""[SEMANA 4 — PENDIENTE] Memoria de largo plazo y perfiles (laboratorio 12).

El equipo debe implementar aquí la memoria que persiste ENTRE sesiones
(perfil del cliente/usuario, preferencias, hechos relevantes del caso de
negocio) usando el Store de LangGraph, y la estrategia de compresión de
contexto cuando la conversación supera un umbral.
"""


def build_store():
    """Retorna el Store de memoria de largo plazo del agente."""
    from langgraph.store.memory import InMemoryStore
    return InMemoryStore()
