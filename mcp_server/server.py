"""[SEMANA 2] Servidor MCP del equipo (laboratorio 7).

Este servidor expone las herramientas de ACCIÓN del agente (las que modifican el
estado del negocio: registrar, escalar, crear, etc.) mediante el Model Context
Protocol. Corre como proceso independiente (transporte stdio); su agente lo
consume a través del cliente MCP (`agent/mcp_client.py`).

Se arranca así (el cliente MCP lo hace por su cuenta como subproceso):

    python mcp_server/server.py        # modo stdio

Expone las tres acciones del caso Telco Andina: registrar el contacto entrante,
crear un ticket de escalamiento y registrar la telemetría obligatoria de
auditoría. Las tres escriben en la API empresarial, y por eso viven aquí y no en
`agent/tools.py`, donde están las consultas.

`registrar_contacto` la invoca el nodo de recepción del grafo directamente, sin
pasar por el modelo: el punto de integración es un paso determinista del caso.
"""

import sys
from pathlib import Path

# Asegurar que el directorio raíz del proyecto esté en sys.path al ejecutarse como script
_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import json
import warnings

# El cliente MCP solo le pasa a este subproceso HOME, LOGNAME, PATH, SHELL y
# USER, así que su ruido se silencia aquí: no llega ninguna variable de entorno.
# `mcp` declara su campo `lifespan` con una referencia adelantada que
# `pydantic-settings` reporta por stderr, y eso se mezcla con la conversación.
warnings.filterwarnings(
    "ignore",
    message=r"Field 'lifespan' has an incomplete definition",
    module=r"pydantic_settings\..*",
)

import requests
from typing import Annotated, Literal
from pydantic import Field
from mcp.server.fastmcp import FastMCP

from cli.config import get_settings

# Por defecto FastMCP registra en INFO cada petición recibida, sobre la
# conversación del CLI. Los errores se siguen viendo.
mcp = FastMCP("acciones-del-agente", log_level="WARNING")


def _contacto_existe(contacto_id: str) -> bool | None:
    """¿El contacto existe en el punto de integración? None si no se pudo verificar.

    Un registro de auditoría con un identificador inexistente es peor que la
    ausencia del registro, porque nadie lo detecta al revisar.
    """
    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/telecom/contactos/{contacto_id}"
    try:
        res = requests.get(url, timeout=10)
    except requests.RequestException:
        return None
    if res.status_code == 200:
        return True
    if res.status_code == 404:
        return False
    return None


def _error(codigo: str, mensaje: str, accion_sugerida: str) -> str:
    return json.dumps(
        {
            "estado": "error",
            "codigo": codigo,
            "mensaje": mensaje,
            "accion_sugerida": accion_sugerida,
        },
        ensure_ascii=False,
    )


def _error_contacto_inexistente(contacto_id: str) -> str:
    return _error(
        "contacto_no_existe",
        f"El contacto '{contacto_id}' no existe en el punto de integración.",
        "No inventes identificadores. Usa el `contacto_id` que te dio el cliente o recupéralo con "
        "`obtener_contacto`; si no lo tienes, pídeselo al cliente antes de registrar nada.",
    )


def _escribir(url: str, payload: dict, que: str, accion_sugerida: str) -> str:
    """POST contra la API empresarial con el contrato de error de las herramientas."""
    try:
        res = requests.post(url, json=payload, timeout=10)
    except requests.RequestException as exc:
        return _error("sin_conexion", f"La API empresarial no responde al {que}: {exc}", accion_sugerida)
    if res.status_code in (200, 201):
        return json.dumps(res.json(), ensure_ascii=False)
    return _error("api_no_disponible", f"status {res.status_code}: {res.text[:200]}", accion_sugerida)


@mcp.tool()
def registrar_contacto(
    texto: Annotated[str, Field(description="Mensaje del cliente tal como llegó, sin reescribir")],
    canal: Annotated[
        Literal["chat", "correo", "llamada_transcrita"],
        Field(description="Canal por el que entró el contacto"),
    ] = "chat",
    cliente_id: Annotated[
        str | None, Field(description="Id del cliente (CLI-xxxx) si ya está identificado")
    ] = None,
) -> str:
    """Registra un contacto entrante en el punto de integración de Telco Andina y devuelve su identificador (CTO-xxx), necesario para la telemetría y los tickets."""
    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/telecom/contactos"
    return _escribir(
        url,
        {"canal": canal, "texto": texto, "cliente_id": cliente_id},
        "registrar el contacto",
        "Atiende el caso sin identificador y deja constancia de que el registro quedó pendiente.",
    )


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
    if _contacto_existe(contacto_id) is False:
        return _error_contacto_inexistente(contacto_id)

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
    return _escribir(
        url,
        payload,
        "crear el ticket",
        "El escalamiento no quedó registrado. Dile al cliente que su caso pasa a un operador "
        "humano y avisa que el ticket debe crearse a mano.",
    )


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
    if _contacto_existe(contacto_id) is False:
        return _error_contacto_inexistente(contacto_id)

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
    return _escribir(
        url,
        payload,
        "registrar la telemetría",
        "El caso queda sin constancia de auditoría. Déjalo anotado en el expediente antes de "
        "responderle al cliente.",
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
