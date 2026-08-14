"""[SEMANA 2 — PENDIENTE] Servidor MCP del equipo (laboratorio 7).

Este servidor expone las herramientas de ACCIÓN del agente (las que modifican el
estado del negocio: registrar, escalar, crear, etc.) mediante el Model Context
Protocol. Corre como proceso independiente (transporte stdio); su agente lo
consume a través del cliente MCP (`agent/mcp_client.py`).

Abajo hay un servidor MÍNIMO que ya funciona, con una herramienta de ejemplo
(`ping`) para que verifiquen el transporte:

    python mcp_server/server.py        # lo arranca en modo stdio (para el cliente)

REEMPLACEN la herramienta de ejemplo por las herramientas de acción de SU caso
de negocio (lean el enunciado). La semana 2 pide que el servidor exponga al
menos una herramienta propia.
"""

from mcp.server.fastmcp import FastMCP
from typing import Annotated
from pydantic import Field

from cli.config import get_settings
from mcp_server.rag_client import RagClient

mcp = FastMCP("acciones-del-agente")
client = RagClient(get_settings())


@mcp.tool
def public_knowledge_base_login() -> str:
    """
    Hace login en el API para consultar el RAG de la base de conocimiento
    pública de telecom. Este llamado debe hacerse antes de hacer cualquier
    interacción con el API del RAG.
    """
    try:
        client.login()
        return 'Login exitoso'
    except Exception as e:
        return f'Login fallido, error: {e}'


@mcp.tool
def query_public_knowledge_base(
    query: Annotated[str, Field(description="Query a realizar sobre la base de conocimiento público")]
) -> str:
    """
    Realiza una consulta sobre el RAG para obtener información
    de conocimiento público sobre la empresa.
    """
    try:
        response = client.query_knowledge_base(query)
        return response
    except Exception as e:
        return f'Error al consultar la base de conocimiento: {e}'

@mcp.tool()
def ping() -> str:
    """
    Herramienta para verificar que el servidor está vivo.
    """
    return "pong"


if __name__ == "__main__":
    mcp.run(transport="stdio")
