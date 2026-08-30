"""Evidencia de memoria de largo plazo (semana 4, entregable 3).

    Sesión A   el cliente se identifica, reporta una falla y amenaza con
               cancelar. Al cerrar, `respuesta` escribe su perfil en el Store.
    Reinicio   se reconstruyen store, checkpointer y grafo desde cero.
    Sesión B   thread_id nuevo. El checkpointer arranca vacío; el Store trae el
               perfil. El cliente escribe una frase que no repite nada de la
               sesión A y el agente responde sabiendo qué le pasó antes.

Correr:  python tests/probar_memoria_largo_plazo.py
"""

import asyncio
from pathlib import Path
import sys
import uuid

# Asegura que la raíz del proyecto esté en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.graph import build_graph
from agent.mcp_client import load_mcp_tools_safe
from agent.memory.checkpointer import build_checkpointer
from agent.memory.store import NS_HISTORIAL, cargar_perfil, historial_cliente
from agent.tools import get_local_tools
from cli.config import get_settings


CEDULA = "123456"
IDENTIDAD_ESPERADA = f"cedula:{CEDULA}"


def titulo(texto: str) -> None:
    print(f"\n{'=' * 70}\n{texto}\n{'=' * 70}\n")


async def armar_agente():
    """Store, checkpointer y grafo recién construidos, como en un arranque en frío."""
    tools = get_local_tools()
    mcp_tools, error_mcp = await load_mcp_tools_safe()
    if error_mcp:
        print(f"  [aviso] servidor MCP no disponible ({error_mcp}); se sigue con tools locales")
    tools.extend(mcp_tools)

    from agent.memory.store import build_store

    checkpointer = build_checkpointer("sqlite")
    store = build_store("sqlite")
    return build_graph(tools, checkpointer=checkpointer, store=store), store


async def correr_sesion(app, thread_id: str, turnos: list[str], etiqueta: str):
    settings = get_settings()
    respuesta_final = None

    for i, mensaje in enumerate(turnos, 1):
        print(f"\n--- {etiqueta} · turno {i} ---")
        print(f"Cliente: {mensaje}")

        run_config = {
            "configurable": {"thread_id": thread_id},
            "run_name": f"largo-plazo:{settings.caso_negocio}:{etiqueta}-turno-{i}",
            "tags": [settings.caso_negocio, f"grupo-{settings.grupo}", "memoria-largo-plazo"],
            "metadata": {
                "caso": settings.caso_negocio,
                "grupo": settings.grupo,
                "sesion": etiqueta,
                "turno": i,
                "thread_id": thread_id,
            },
        }

        async for update in app.astream(
            {"messages": [("user", mensaje)]}, config=run_config, stream_mode="updates"
        ):
            for nodo, salida_nodo in update.items():
                if nodo == "recepcion" and salida_nodo.get("perfil_cliente"):
                    print(f"  [Store · lectura en recepcion] {salida_nodo['perfil_cliente']}")
                for m in salida_nodo.get("messages", []):
                    if nodo == "respuesta" and getattr(m, "content", None):
                        respuesta_final = m.content

    estado = app.get_state({"configurable": {"thread_id": thread_id}}).values
    return respuesta_final, estado


def mostrar_perfil(perfil: dict | None, encabezado: str) -> None:
    print(f"\n{encabezado}")
    if not perfil:
        print("  (sin perfil guardado)")
        return
    for clave in (
        "identidad",
        "interacciones",
        "categorias",
        "riesgo_churn_historico",
        "areas_escalamiento",
        "tickets",
        "compromisos",
        "ultima_interaccion",
    ):
        if perfil.get(clave):
            print(f"  {clave:<24}: {perfil[clave]}")


async def main():
    thread_a = f"largo-plazo-A-{uuid.uuid4().hex[:8]}"
    thread_b = f"largo-plazo-B-{uuid.uuid4().hex[:8]}"

    # ── Sesión A ────────────────────────────────────────────────────────────
    titulo(f"SESIÓN A — thread_id {thread_a}")
    app, store = await armar_agente()

    perfil_previo = cargar_perfil(store, IDENTIDAD_ESPERADA)
    mostrar_perfil(perfil_previo, "Perfil en el Store ANTES de la sesión A:")

    respuesta_a, _ = await correr_sesion(
        app,
        thread_a,
        [
            f"Hola, soy Carlos, mi cedula es {CEDULA}. Llevo dos dias sin internet y ya reinicie el modem.",
            "Si esto no se arregla hoy cancelo el servicio y me voy para la competencia.",
        ],
        "sesionA",
    )
    print("\nAgente (sesión A):")
    print(respuesta_a)

    mostrar_perfil(
        cargar_perfil(store, IDENTIDAD_ESPERADA),
        "Perfil en el Store DESPUÉS de la sesión A (escrito por el nodo `respuesta`):",
    )

    # ── Reinicio ────────────────────────────────────────────────────────────
    titulo("REINICIO — se reconstruyen store, checkpointer y grafo desde cero")
    del app, store
    app, store = await armar_agente()
    print("Objetos nuevos. Lo único que sobrevive está en disco.")

    # ── Sesión B ────────────────────────────────────────────────────────────
    titulo(f"SESIÓN B — thread_id {thread_b} (NUEVO)")

    previo_b = app.get_state({"configurable": {"thread_id": thread_b}}).values
    print(f"Mensajes que el checkpointer tiene para este thread: {len(previo_b.get('messages', []))}")
    mostrar_perfil(cargar_perfil(store, IDENTIDAD_ESPERADA), "Perfil que el Store sí conserva:")

    respuesta_b, estado_b = await correr_sesion(
        app,
        thread_b,
        [f"Buenas, cedula {CEDULA}. Nuevamente estoy sin servicio."],
        "sesionB",
    )
    print("\nAgente (sesión B):")
    print(respuesta_b)

    # ── Verificación ────────────────────────────────────────────────────────
    titulo("VERIFICACIÓN")
    print(f"Perfil que llegó al prompt en la sesión B:\n  {estado_b.get('perfil_cliente') or 'NINGUNO'}")
    print(f"\nDecisión de la sesión B : {estado_b.get('decision')}")
    print(f"Área destino            : {estado_b.get('area_destino')}")
    print(f"Prioridad               : {estado_b.get('prioridad')}")
    print(f"Riesgo de cancelación   : {estado_b.get('riesgo_churn')}")
    print(f"Justificación           : {estado_b.get('justificacion')}")

    print(f"\nHistorial en el namespace ('{NS_HISTORIAL}', '{IDENTIDAD_ESPERADA}'):")
    for entrada in historial_cliente(store, IDENTIDAD_ESPERADA):
        print(
            f"  {entrada.get('fecha', '')[:19]} · {entrada.get('categoria')}"
            f" · churn={entrada.get('riesgo_churn')} · {entrada.get('decision')}"
            f" · {entrada.get('resumen', '')[:60]}"
        )

    mostrar_perfil(cargar_perfil(store, IDENTIDAD_ESPERADA), "Perfil final acumulado:")

    ok = bool(estado_b.get("perfil_cliente")) and not previo_b.get("messages")
    print(
        f"\n=> {'OK' if ok else 'REVISAR'}: la sesión B abrió sin historial en el checkpointer "
        f"{'y aun así' if ok else 'pero NO'} recibió el perfil del Store."
    )


if __name__ == "__main__":
    asyncio.run(main())
