"""Instrumentación con LangSmith (semana 3, laboratorio 9).

LangGraph y LangChain se trazan solos cuando LANGCHAIN_TRACING_V2=true.
Este módulo agrega:
  - `trazable`: decorador para funciones propias del proyecto (usa
    @traceable de LangSmith solo si el tracing está activo, para que el
    código funcione igual sin credenciales configuradas).
  - `traza`: context manager para un bloque (por ejemplo la retención)
    que debe verse como traza hija, con entradas y salidas propias.
  - `anotar_traza`, `etiquetar_traza`, `anotar_evento`: datos que se leen
    en el panel de la traza abierta, sin cambiar el valor que devuelve
    la función.
  - `tracing_activo`: chequeo usado por el CLI y los tests.
"""

import contextlib
import functools
import inspect
import os
from typing import Callable


def tracing_activo() -> bool:
    return os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true" and bool(
        os.getenv("LANGCHAIN_API_KEY")
    )


def get_client():
    """Instancia y retorna un cliente de LangSmith para tracing y consulta de trazas."""
    from langsmith import Client

    api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
    return Client(api_key=api_key)


def _run_actual():
    """Run de LangSmith en curso. None si el tracing está apagado o no hay padre."""
    if not tracing_activo():
        return None
    try:
        from langsmith.run_helpers import get_current_run_tree
    except ImportError:
        return None
    return get_current_run_tree()


def anotar_traza(**campos: object) -> None:
    """Añade metadatos a la traza abierta. Los None se omiten."""
    presentes = {clave: valor for clave, valor in campos.items() if valor is not None}
    if not presentes:
        return
    run = _run_actual()
    if run is None:
        return
    run.metadata.update(presentes)


def etiquetar_traza(*etiquetas: str) -> None:
    """Añade etiquetas a la traza abierta, para filtrar en LangSmith."""
    utiles = [etiqueta for etiqueta in etiquetas if etiqueta]
    if not utiles:
        return
    run = _run_actual()
    if run is None:
        return
    run.add_tags(utiles)


def anotar_evento(mensaje: str, *, en_padre: bool = False) -> None:
    """Deja una línea en la cronología de la traza abierta.

    Con `en_padre`, la línea queda en la traza que llamó a esta función,
    para que el proceso completo se lea sin abrir cada paso.
    """
    texto = (mensaje or "").strip()
    if not texto:
        return
    run = _run_actual()
    if run is None:
        return
    destino = run
    if en_padre:
        padre = getattr(run, "parent_run", None)
        if padre is not None:
            destino = padre
    destino.add_event(texto)


def cerrar_traza(run, salidas: dict) -> None:
    """Fija las salidas de una traza abierta con `traza`. None no hace nada."""
    if run is None:
        return
    run.end(outputs=salidas)


def entradas_sin_llamables(entradas: dict) -> dict:
    """Quita funciones y None del input que LangSmith va a guardar."""
    return {
        clave: valor
        for clave, valor in entradas.items()
        if valor is not None and not callable(valor)
    }


@contextlib.asynccontextmanager
async def traza(
    name: str,
    *,
    run_type: str = "chain",
    inputs: dict | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
):
    """Abre una traza hija. Si LangSmith no está activo, no hace nada."""
    if not tracing_activo():
        yield None
        return
    try:
        from langsmith import trace
    except ImportError:
        yield None
        return
    async with trace(
        name,
        run_type=run_type,
        inputs=inputs or {},
        tags=tags,
        metadata=metadata,
    ) as run:
        yield run


def trazable(
    name: str | None = None,
    *,
    run_type: str = "chain",
    tags: list[str] | None = None,
    metadata: dict | None = None,
    process_inputs: Callable | None = None,
    process_outputs: Callable | None = None,
) -> Callable:
    """Aplica @traceable de LangSmith si hay tracing configurado; si no, no-op.

    La decisión se toma en la primera llamada y no al importar el módulo: el
    `.env` que trae LANGCHAIN_API_KEY lo carga `cli.config`, y un módulo que se
    importe antes que él se quedaría sin trazas.
    """

    def decorator(func: Callable) -> Callable:
        resuelta = None

        def resolver():
            nonlocal resuelta
            if resuelta is None:
                if tracing_activo():
                    from langsmith import traceable

                    opciones: dict = {
                        "name": name or func.__name__,
                        "run_type": run_type,
                    }
                    if tags:
                        opciones["tags"] = list(tags)
                    if metadata:
                        opciones["metadata"] = dict(metadata)
                    if process_inputs is not None:
                        opciones["process_inputs"] = process_inputs
                    if process_outputs is not None:
                        opciones["process_outputs"] = process_outputs
                    resuelta = traceable(**opciones)(func)
                else:
                    resuelta = func
            return resuelta

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await resolver()(*args, **kwargs)

            return wrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return resolver()(*args, **kwargs)

        return wrapper

    return decorator
