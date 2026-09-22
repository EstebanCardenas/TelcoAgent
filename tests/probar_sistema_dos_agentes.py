"""Prueba del sistema de dos agentes: Agente 1 llama al Asesor de Retención.

Exige el Agente 2 en AGENTE2_BASE_URL (por defecto http://localhost:8090).
Si ese proceso no responde, el script termina sin invocar el grafo.

También exige la API empresarial (el especialista valida el ticket) y Ollama
(ambos grafos). No sustituye al Agente 2 por un doble de prueba.

Uso, desde main/, con api y agente2 levantados:

    docker compose up -d api agente2
    python tests/probar_sistema_dos_agentes.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.graph import build_graph
from agent.mcp_client import load_mcp_tools_safe
from agent.memory.checkpointer import build_checkpointer
from agent.memory.store import build_store
from agent.tools import get_local_tools
from cli.config import get_settings

MENSAJE = (
    "Llevo cinco días sin internet, ya llamé tres veces, si no me resuelven hoy "
    "cancelo todo y me llevo las tres líneas a la competencia. Mi contacto es CTO-008."
)

CAMPOS_A2A = (
    "ticket_id",
    "ticket_n2_id",
    "tarea_id",
    "segmento",
    "estado_tarea_a2a",
    "oferta_retencion",
    "deriva_n2",
    "compromiso_retencion",
)


def _imprimir(titulo: str, cuerpo) -> None:
    print(titulo)
    if isinstance(cuerpo, (dict, list)):
        print(json.dumps(cuerpo, indent=2, ensure_ascii=False))
    else:
        print(cuerpo)
    print()


def _get_json(url: str, timeout: float = 2.0) -> tuple[int, dict | None]:
    try:
        respuesta = httpx.get(url, timeout=timeout)
    except httpx.HTTPError:
        return 0, None
    try:
        datos = respuesta.json()
    except ValueError:
        return respuesta.status_code, None
    return respuesta.status_code, datos if isinstance(datos, dict) else None


def exigir_servicio(url: str, *, nombre: str, clave: str | None = None) -> dict:
    codigo, datos = _get_json(url)
    if codigo != 200 or not isinstance(datos, dict):
        print(f"{nombre} no responde en {url}.")
        print("Levante los servicios: docker compose up -d api agente2")
        print("Ollama debe estar en el anfitrión: ollama serve")
        sys.exit(1)
    if clave and datos.get("servicio") != clave:
        print(f"{nombre} respondió, pero no es el Asesor de Retención: {datos}")
        sys.exit(1)
    return datos


def consultar_tarea(base: str, tarea_id: str) -> dict | None:
    if not tarea_id:
        return None
    _codigo, datos = _get_json(f"{base.rstrip('/')}/tareas/{tarea_id}", timeout=3.0)
    return datos


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    base_agente2 = settings.agente2_base_url.rstrip("/")
    base_api = settings.api_base_url.rstrip("/")

    salud_agente2 = exigir_servicio(
        f"{base_agente2}/health",
        nombre="Agente 2",
        clave="asesor-retencion",
    )
    exigir_servicio(f"{base_api}/health", nombre="API empresarial")

    print("Sistema de dos agentes: Situación B")
    print(f"Agente 2        : {base_agente2}  {salud_agente2}")
    print(f"API empresarial : {base_api}")
    print(f"modelo          : {settings.ollama_model}")
    print()

    tools = get_local_tools() + (await load_mcp_tools_safe())[0]
    graph = build_graph(
        tools=tools,
        checkpointer=build_checkpointer("sqlite"),
        store=build_store("sqlite"),
    )

    thread_id = str(uuid.uuid4())
    run_config = {
        "configurable": {"thread_id": thread_id},
        "run_name": f"dos-agentes:{settings.caso_negocio}:situacion-b",
        "tags": [
            settings.caso_negocio,
            f"grupo-{settings.grupo}",
            "semana-8",
            "dos-agentes",
            "situacion-b",
        ],
        "metadata": {
            "caso": settings.caso_negocio,
            "grupo": settings.grupo,
            "semana": 8,
            "proposito": "agente1-llama-agente2",
        },
    }

    print("THREAD_ID:", thread_id)
    print("Cliente  :", MENSAJE)
    print()

    a2a: dict = {}
    salida_final = None

    async for update in graph.astream(
        {"messages": [HumanMessage(content=MENSAJE)]},
        config=run_config,
        stream_mode="updates",
    ):
        for nodo, salida_nodo in update.items():
            print(f"  [Nodo: {nodo}]")
            if isinstance(salida_nodo, dict):
                for campo in CAMPOS_A2A:
                    if campo in salida_nodo and salida_nodo[campo] not in (None, ""):
                        a2a[campo] = salida_nodo[campo]
                        print(f"    {campo}: {salida_nodo[campo]}")
            mensajes = (
                salida_nodo.get("messages", []) if isinstance(salida_nodo, dict) else []
            )
            for mensaje in mensajes:
                if isinstance(mensaje, AIMessage) and mensaje.tool_calls:
                    for llamada in mensaje.tool_calls:
                        print(f"    Thought/Action: {llamada['name']}({llamada['args']})")
                elif isinstance(mensaje, AIMessage) and mensaje.content:
                    texto = str(mensaje.content)
                    if texto.startswith("[auditoría]"):
                        print(f"    {texto}")
                    elif not texto.startswith("["):
                        salida_final = texto
                elif isinstance(mensaje, ToolMessage):
                    print(f"    Observation ({mensaje.name}): {str(mensaje.content)[:180]}...")

    print()
    _imprimir("Estado A2A en el Agente 1", a2a)

    tarea = consultar_tarea(base_agente2, str(a2a.get("tarea_id") or ""))
    if tarea is None:
        print("El Agente 1 no dejó tarea_id. El Asesor de Retención no fue consultado.")
        print("Revise que se haya creado un ticket de retención y que AGENTE2_BASE_URL apunte al puerto 8090.")
    else:
        _imprimir("GET /tareas en el Agente 2", tarea)

    print("Agente 1 al cliente:")
    print(salida_final)
    print()

    compromiso = str(a2a.get("compromiso_retencion") or "")
    if a2a.get("estado_tarea_a2a") == "completed" and compromiso:
        print("Resultado: el especialista autorizó un compromiso. El Agente 1 debe citarlo, no reinventar la cifra.")
    elif a2a.get("estado_tarea_a2a"):
        print(
            f"Resultado: retención en estado {a2a['estado_tarea_a2a']}. "
            "El cliente no debe oír porcentajes ni meses inventados."
        )
    else:
        print("Resultado: este turno no activó al Asesor de Retención.")


if __name__ == "__main__":
    asyncio.run(main())
