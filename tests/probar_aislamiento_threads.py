"""Script de validacion para aislamiento de memoria entre diferentes thread_id (Semana 4).

Demuestra que dos conversaciones concurrentes o intercaladas con identificadores de
hilo distintos (	hread_id_a y 	hread_id_b) mantienen su estado 100% aislado en el Checkpointer.
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

    checkpointer = build_checkpointer("sqlite")
    graph = build_graph(tools=tools, checkpointer=checkpointer)

    thread_a = f"sesion-cliente-A-{uuid.uuid4()}"
    thread_b = f"sesion-cliente-B-{uuid.uuid4()}"

    print(f"THREAD A (Facturacion): {thread_a}")
    print(f"THREAD B (Consulta aislada): {thread_b}\n")

    secuencia = [
        (
            "Thread A (Turno 1)",
            thread_a,
            "Hola, me llego un cobro no reconocido de 85000 pesos en mi factura de este mes. Mi contacto es CTO-002.",
        ),
        (
            "Thread B (Turno 1 - Cliente Distinto)",
            thread_b,
            "Hola, necesito saber que valor de cobro te acabo de reportar hace un momento?",
        ),
        (
            "Thread A (Turno 2 - Retorno)",
            thread_a,
            "A que area transferiste mi reclamo por el cobro indebido?",
        ),
    ]

    for paso_nombre, th_id, texto in secuencia:
        print(f"=== {paso_nombre} ===")
        print(f"Thread ID: {th_id}")
        print(f"Mensaje: {texto}")

        run_config = {
            "configurable": {"thread_id": th_id},
            "run_name": f"aislamiento:{paso_nombre.split()[1]}",
            "tags": [settings.caso_negocio, f"grupo-{settings.grupo}", "aislamiento-threads"],
            "metadata": {
                "caso": settings.caso_negocio,
                "grupo": settings.grupo,
                "thread_id": th_id,
                "paso": paso_nombre,
            },
        }

        historia = [HumanMessage(content=texto)]
        salida_final = None

        async for update in graph.astream(
            {"messages": historia}, config=run_config, stream_mode="updates"
        ):
            for nodo, salida_nodo in update.items():
                for m in salida_nodo.get("messages", []):
                    if isinstance(m, AIMessage):
                        if m.tool_calls:
                            for tc in m.tool_calls:
                                print(f"  Tool Call: {tc['name']}({tc['args']})")
                        elif m.content and not str(m.content).startswith("["):
                            salida_final = m.content

        print("Respuesta Agente:")
        print(salida_final)
        print(f"=== FIN {paso_nombre} ===\n")


if __name__ == "__main__":
    asyncio.run(main())
