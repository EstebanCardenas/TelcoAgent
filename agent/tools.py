"""[SEMANA 2 — PENDIENTE] Herramientas locales del agente (laboratorio 6).

Las herramientas son las capacidades que el agente puede invocar para consultar
o actuar sobre los sistemas del caso de negocio (por ejemplo, la API empresarial
de la operadora o la base de conocimiento). Cada herramienta es una función
decorada con `@tool` de LangChain, con una descripción clara: ese texto es lo
que el LLM lee para decidir cuándo usarla.

Diseñen las herramientas que su caso necesite (lean el enunciado). La semana 2
pide al menos 3 herramientas locales, cada una con nombre y descripción.

Las herramientas de ACCIÓN (las que modifican el estado del negocio) se exponen
además a través de su servidor MCP (`mcp_server/server.py`), no aquí.
"""

# from langchain_core.tools import tool
#
# @tool
# def mi_herramienta(argumento: str) -> dict:
#     """Descripción clara: qué hace y cuándo el agente debería usarla."""
#     ...

import json
import requests
from langchain_core.tools import tool

from cli.config import get_settings
from agent.rag_client import RagClient


@tool
def consultar_base_conocimiento_publica(query: str) -> str:
    """Consulta la base de conocimiento pública (RAG) de Telco Andina sobre catálogo de planes, tarifas, tiendas, horarios, canales de atención y políticas institucionales generales."""
    try:
        client = RagClient(get_settings())
        client.login()
        return client.query_knowledge_base(query)
    except Exception as e:
        return f"Error al consultar la base de conocimiento RAG: {e}"


@tool
def consultar_politicas_institucionales(tipo: str) -> str:
    """Consulta las políticas de escalamiento específicas de Telco Andina (por ejemplo: 'vip', 'falla-masiva', 'palabras-clave') desde la API empresarial."""
    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/telecom/politicas/{tipo.strip().lower()}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return json.dumps(res.json(), ensure_ascii=False)
        return f"Error al consultar política '{tipo}': status {res.status_code} - {res.text}"
    except Exception as e:
        return f"Error al conectar con la API empresarial: {e}"


@tool
def consultar_casos_resueltos(categoria: str = "") -> str:
    """Consulta el repositorio histórico de casos resueltos (precedentes de síntoma -> solución aplicada) filtrables por categoría ('tecnica', 'facturacion', 'retencion', etc.)."""
    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/telecom/casos-resueltos"
    params = {}
    if categoria and categoria.strip():
        params["categoria"] = categoria.strip().lower()
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            return json.dumps(res.json(), ensure_ascii=False)
        return f"Error al consultar casos resueltos: status {res.status_code} - {res.text}"
    except Exception as e:
        return f"Error al conectar con la API empresarial: {e}"


def get_local_tools() -> list:
    """Lista de herramientas locales del agente para consultas y conocimiento."""
    return [
        consultar_base_conocimiento_publica,
        consultar_politicas_institucionales,
        consultar_casos_resueltos,
    ]

def get_local_tools_by_name() -> dict:
    return {tool.name: tool for tool in get_local_tools()}
