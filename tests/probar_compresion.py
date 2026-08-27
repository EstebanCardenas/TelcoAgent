import asyncio
from pathlib import Path
import sys
import uuid

# Asegura que la raíz del proyecto esté en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.graph import build_graph
from agent.memory.checkpointer import build_checkpointer
from agent.mcp_client import load_mcp_tools_safe
from agent.tools import get_local_tools
from cli.config import get_settings

async def main():
    settings = get_settings()
    
    # Checkpointer SQLite
    checkpointer = build_checkpointer("sqlite")
    
    tools = get_local_tools()
    mcp_tools, mcp_cleanups = await load_mcp_tools_safe()
    tools.extend(mcp_tools)
    
    # Cargar grafo
    app = build_graph(tools, checkpointer=checkpointer)
    
    thread_id = f"sesion-compresion-{uuid.uuid4().hex[:8]}"
    
    print(f"\n=======================================================")
    print(f"--- INICIANDO SESIÓN CON COMPRESIÓN DE CONTEXTO ---")
    print(f"Thread ID: {thread_id}")
    print(f"=======================================================\n")
    
    turnos = [
        "Hola, me llamo Carlos y mi cedula es 123456.",
        "Tengo un problema con el cobro de mi factura, me están cobrando de más.",
        "No entiendo por qué mi factura dice $85,000 si mi plan es de $45,000.",
        "¿Me puedes confirmar mi nombre, cédula y el valor que te reporté anteriormente?"
    ]
    
    for i, mensaje in enumerate(turnos, 1):
        print(f"\n=== INICIO TURNO {i} ===")
        print(f"Cliente: {mensaje}")
        
        run_config = {
            "configurable": {"thread_id": thread_id},
            "run_name": f"compresion:{settings.caso_negocio}:turno-{i}",
            "tags": [settings.caso_negocio, f"grupo-{settings.grupo}", "compresion-contexto"],
            "metadata": {"caso": settings.caso_negocio, "grupo": settings.grupo, "turno": i, "thread_id": thread_id},
        }
        
        estado_inicial = {"messages": [("user", mensaje)]}
        salida_agente = None
        
        async for update in app.astream(estado_inicial, config=run_config, stream_mode="updates"):
            for nodo, salida_nodo in update.items():
                print(f"  [Nodo: {nodo}]")
                if nodo == "compresion_contexto":
                    print(f"    >>> [COMPRESIÓN ACTIVADA] <<<")
                    print(f"    Resumen generado: {salida_nodo.get('resumen_contexto')}")
                    from langchain_core.messages import RemoveMessage
                    removidos = [m for m in salida_nodo.get("messages", []) if isinstance(m, RemoveMessage)]
                    print(f"    Mensajes eliminados del estado activo: {len(removidos)}")
                
                for m in salida_nodo.get("messages", []):
                    if hasattr(m, "content") and m.content and not str(m.content).startswith("["):
                        if nodo == "respuesta":
                            salida_agente = m.content

        print("\nAgente:")
        print(salida_agente)
        
        # Verificar estado tras el turno
        st = app.get_state(run_config)
        mensajes_actuales = len(st.values.get("messages", []))
        tiene_resumen = bool(st.values.get("resumen_contexto"))
        print(f"\n  [Estado post-turno {i}]: {mensajes_actuales} mensajes en memoria activa | Resumen presente: {tiene_resumen}")
        print(f"=== FIN TURNO {i} ===\n")

    # Estado final consolidado
    final_state = app.get_state({"configurable": {"thread_id": thread_id}})
    print("\n=======================================================")
    print("--- RESUMEN FINAL DE LA SESIÓN ---")
    print(f"Thread ID: {thread_id}")
    print(f"Resumen acumulativo en estado: {final_state.values.get('resumen_contexto')}")
    print(f"Total mensajes en memoria activa: {len(final_state.values.get('messages', []))}")
    print(f"Tipos de mensajes en memoria: {[m.type for m in final_state.values.get('messages', [])]}")
    print("=======================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
