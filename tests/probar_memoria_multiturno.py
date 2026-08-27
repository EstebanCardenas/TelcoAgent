"""Script de validacion para memoria de corto plazo multi-turno (Semana 4).

Ejecuta 3 turnos conversacionales sobre el mismo `thread_id` utilizando el
grafo del agente con Checkpointer SQLite y emite trazas a LangSmith.
"""

import asyncio
from pathlib import Path
import sys
import uuid

# Asegura que la raíz del proyecto esté en sys.path independientemente de cómo se invoque
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from agent.graph import build_graph
from agent.memory.checkpointer import build_checkpointer
from agent.mcp_client import load_mcp_tools_safe
from agent.tools import get_local_tools
from cli.config import get_settings


async def main():
    settings = get_settings()
    local_tools = get_local_tools()
    mcp_tools, _ = await load_mcp_tools_safe()
    tools = local_tools + mcp_tools

    # Construccion del grafo con Checkpointer SQLite
    checkpointer = build_checkpointer("sqlite")
    graph = build_graph(tools=tools, checkpointer=checkpointer)

    # Identificador unico de conversacion para los 3 turnos
    thread_id = str(uuid.uuid4())
    print("THREAD_ID:", thread_id)

    turnos = [
        "Hola, mi servicio de internet esta presentando caidas constantes y lentitud. Mi numero de contacto es CTO-001.",
        "Ya reinicie el modem hace unos minutos y el problema persiste.",
        "A que area escalaste mi solicitud y con que prioridad quedo registrada?",
    ]

    for i, texto in enumerate(turnos, 1):
        print(f"=== INICIO TURNO {i} ===")
        print(f"Cliente: {texto}")
        run_config = {
            "configurable": {"thread_id": thread_id},
            "run_name": f"chat:{settings.caso_negocio}:turno-{i}",
            "tags": [settings.caso_negocio, f"grupo-{settings.grupo}"],
            "metadata": {"caso": settings.caso_negocio, "grupo": settings.grupo, "turno": i},
        }

        historia = [HumanMessage(content=texto)]
        salida_final = None

        async for update in graph.astream(
            {"messages": historia}, config=run_config, stream_mode="updates"
        ):
            for nodo, salida_nodo in update.items():
                print(f"  [Nodo: {nodo}]")
                for m in salida_nodo.get("messages", []):
                    if isinstance(m, AIMessage):
                        if m.tool_calls:
                            for tc in m.tool_calls:
                                print(f"    Tool Call: {tc['name']}({tc['args']})")
                        elif m.content and not str(m.content).startswith("["):
                            salida_final = m.content
                    elif isinstance(m, ToolMessage):
                        print(f"    Tool Output ({m.name}): {str(m.content)[:150]}...")

        print("Agente:")
        print(salida_final)
        print(f"=== FIN TURNO {i} ===\n")


if __name__ == "__main__":
    asyncio.run(main())
