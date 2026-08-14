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

import sys
from pathlib import Path

# Asegurar que el directorio raíz del proyecto esté en sys.path al ejecutarse como script
_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import json
import requests
from typing import Annotated, Literal
from pydantic import Field
from mcp.server.fastmcp import FastMCP

from cli.config import get_settings

mcp = FastMCP("acciones-del-agente")


@mcp.tool()
def crear_ticket_escalamiento(
    contacto_id: Annotated[str, Field(description="Identificador del contacto origen (ej. CTO-001)")],
    categoria: Annotated[str, Field(description="Categoría del problema a escalar: tecnica, facturacion, retencion, etc.")],
    prioridad: Annotated[Literal["baja", "media", "alta", "critica"], Field(description="Nivel de prioridad del ticket")],
    area_destino: Annotated[
        Literal["soporte_tecnico_n1", "soporte_tecnico_n2", "facturacion", "retencion", "supervision"],
        Field(description="Área humana especializada de destino"),
    ],
    resumen: Annotated[str, Field(description="Resumen y justificación del escalamiento con datos relevantes")],
    cliente_id: Annotated[str | None, Field(description="Id del cliente si está identificado")] = None,
) -> str:
    """Crea un ticket de escalamiento en la API empresarial de Telco Andina para transferir un caso a un área especializada."""
    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/telecom/tickets"
    payload = {
        "contacto_id": contacto_id,
        "categoria": categoria,
        "prioridad": prioridad,
        "area_destino": area_destino,
        "resumen": resumen,
        "cliente_id": cliente_id,
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code in (200, 201):
            return json.dumps(res.json(), ensure_ascii=False)
        return f"Error al crear ticket: status {res.status_code} - {res.text}"
    except Exception as e:
        return f"Error de conexión al crear ticket en API empresarial: {e}"


@mcp.tool()
def registrar_telemetria(
    contacto_id: Annotated[str, Field(description="Identificador único del contacto atendido")],
    categoria: Annotated[str, Field(description="Categoría principal: tecnica | facturacion | retencion | consulta | otro")],
    tono_detectado: Annotated[Literal["frustrado", "urgente", "agresivo", "neutro", "cordial"], Field(description="Tono emocional detectado")],
    urgencia: Annotated[Literal["baja", "media", "alta"], Field(description="Nivel de urgencia del caso")],
    decision: Annotated[Literal["resolver", "escalar"], Field(description="Decisión tomada por el agente")],
    categoria_secundaria: Annotated[str | None, Field(description="Segunda categoría si el mensaje es mixto")] = None,
    riesgo_churn: Annotated[bool | None, Field(description="True si hay amenaza de cancelación")] = None,
    detalle: Annotated[str | None, Field(description="Detalle o justificación de la decisión")] = None,
) -> str:
    """Registra la auditoría y telemetría obligatoria en la API empresarial antes de emitir una respuesta al cliente."""
    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/telecom/telemetria"
    payload = {
        "contacto_id": contacto_id,
        "categoria": categoria,
        "tono_detectado": tono_detectado,
        "urgencia": urgencia,
        "decision": decision,
        "categoria_secundaria": categoria_secundaria,
        "riesgo_churn": riesgo_churn,
        "detalle": detalle,
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code in (200, 201):
            return json.dumps(res.json(), ensure_ascii=False)
        return f"Error al registrar telemetría: status {res.status_code} - {res.text}"
    except Exception as e:
        return f"Error de conexión al registrar telemetría en API empresarial: {e}"


@mcp.tool()
def ping() -> str:
    """Herramienta de diagnóstico para verificar que el servidor MCP responde."""
    return "pong"


if __name__ == "__main__":
    mcp.run(transport="stdio")
