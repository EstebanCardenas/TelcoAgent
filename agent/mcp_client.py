"""[SEMANA 2 — PENDIENTE] Cliente MCP del agente (laboratorio 8).

El cliente MCP lanza SU servidor MCP (`mcp_server/server.py`) como subproceso
(transporte stdio) y convierte las herramientas que expone en tools de LangChain,
para que el agente las use igual que las locales.

Implementen `load_mcp_tools()` conectándose a su servidor. `load_mcp_tools_safe()`
ya está lista: envuelve la anterior para que el CLI no se caiga si el servidor
todavía no existe o no arranca (degrada a solo herramientas locales).
"""

import sys
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient

SERVER_PATH = str((Path(__file__).resolve().parent.parent / "mcp_server" / "server.py").resolve())

config = {
    "agent-actions": {
        "command": sys.executable,
        "args": [SERVER_PATH],
        "transport": "stdio",
    }
}
client = MultiServerMCPClient(config)


async def load_mcp_tools() -> list:
    """Descubre y devuelve las herramientas expuestas por su servidor MCP."""
    return await client.get_tools()


async def load_mcp_tools_safe() -> tuple[list, str | None]:
    """Variante tolerante para el CLI: retorna (tools, error)."""
    try:
        return await load_mcp_tools(), None
    except Exception as exc:  # noqa: BLE001 — cualquier fallo degrada, no rompe
        return [], str(exc)
