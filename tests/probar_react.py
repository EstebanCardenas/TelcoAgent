"""Script de evidencia ReAct (Semana 5).

Ejecuta un único turno con un mensaje mixto del caso Telco Andina que exige
varias consultas secuenciales (política, precedentes, conocimiento público).
Emite la traza a LangSmith con tags de la semana 5.
"""

import asyncio
import sys
from pathlib import Path
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.graph import build_graph
from agent.mcp_client import load_mcp_tools_safe
from agent.memory.checkpointer import build_checkpointer
from agent.memory.store import build_store
from agent.tools import get_local_tools
from cli.config import get_settings
from observability.tracing import tracing_activo

# Situación C + consulta de tienda: churn, facturación, falla técnica y RAG.
MENSAJE = (
    "Me cobraron dos veces el mes pasado, el servicio de internet lleva lento "
    "tres días y encima el técnico que mandaron la semana pasada fue muy grosero. "
    "No sé si seguir con ustedes. Antes de decidir cancelar, ¿a qué hora cierra "
    "la tienda de Chapinero? Si no me resuelven hoy me llevo las tres líneas a "
    "la competencia."
)


async def main():
    settings = get_settings()
    print(f"modelo           : {settings.ollama_model}")
    print(f"LangSmith activo : {tracing_activo()}  proyecto={settings.langsmith_project}")

    tools = get_local_tools() + (await load_mcp_tools_safe())[0]
    graph = build_graph(
        tools=tools,
        checkpointer=build_checkpointer("sqlite"),
        store=build_store("sqlite"),
    )

    thread_id = str(uuid.uuid4())
    run_config = {
        "configurable": {"thread_id": thread_id},
        "run_name": f"react:{settings.caso_negocio}:descomposicion-3pasos",
        "tags": [
            settings.caso_negocio,
            f"grupo-{settings.grupo}",
            "semana-5",
            "react",
        ],
        "metadata": {
            "caso": settings.caso_negocio,
            "grupo": settings.grupo,
            "semana": 5,
            "patron": "react",
            "proposito": "descomposicion-3-o-mas-pasos",
        },
    }

    print("THREAD_ID:", thread_id)
    print("run_name :", run_config["run_name"])
    print("Cliente  :", MENSAJE)
    print()

    pasos_reason = 0
    pasos_act = 0
    tools_usadas: list[str] = []
    salida_final = None

    async for update in graph.astream(
        {"messages": [HumanMessage(content=MENSAJE)]},
        config=run_config,
        stream_mode="updates",
    ):
        for nodo, salida_nodo in update.items():
            print(f"  [Nodo: {nodo}]")
            if nodo == "reason":
                pasos_reason += 1
            elif nodo == "act":
                pasos_act += 1
            for m in salida_nodo.get("messages", []) if isinstance(salida_nodo, dict) else []:
                if isinstance(m, AIMessage) and m.tool_calls:
                    for tc in m.tool_calls:
                        print(f"    Thought/Action: {tc['name']}({tc['args']})")
                elif isinstance(m, AIMessage) and m.content:
                    texto = str(m.content)
                    if texto.startswith("[razonamiento]"):
                        print(f"    {texto[:300]}")
                    elif not texto.startswith("["):
                        salida_final = texto
                elif isinstance(m, ToolMessage):
                    tools_usadas.append(m.name or "")
                    print(f"    Observation ({m.name}): {str(m.content)[:180]}...")

    print()
    print("Agente:")
    print(salida_final)
    print()
    print(f"pasos reason : {pasos_reason}")
    print(f"pasos act    : {pasos_act}")
    print(f"herramientas : {tools_usadas}")
    print(f"pasos ReAct (reason+act) : {pasos_reason + pasos_act}")


if __name__ == "__main__":
    asyncio.run(main())
