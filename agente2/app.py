"""Servidor HTTP del Asesor de Retención.

Starlette ya viene con `mcp`. No se añade FastAPI a las dependencias fijadas
del curso. El proceso escucha `/health`, el contrato A2A y lecturas del catálogo.
"""

from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from agente2.a2a import tareas
from agente2.config import get_settings
from agente2.db.conexion import conectar, inicializar_bd
from agente2.db.repositorio import listar_topes, obtener_oferta


@asynccontextmanager
async def lifespan(_app: Starlette):
    inicializar_bd(get_settings().db_path)
    yield


def _json(modelo, estado: int = 200) -> JSONResponse:
    return JSONResponse(modelo.model_dump(), status_code=estado)


def health(_request: Request) -> JSONResponse:
    return JSONResponse({"estado": "ok", "servicio": "asesor-retencion"})


async def crear_tarea(request: Request) -> JSONResponse:
    try:
        cuerpo = await request.json()
    except Exception:
        cuerpo = {}
    if not isinstance(cuerpo, dict):
        cuerpo = {}
    respuesta = tareas.aceptar_o_rechazar(cuerpo)
    return _json(respuesta)


def consultar_tarea(request: Request) -> JSONResponse:
    tarea_id = request.path_params["tarea_id"]
    encontrada = tareas.obtener(tarea_id)
    if encontrada is None:
        return JSONResponse(
            {"tarea_id": tarea_id, "estado": "failed", "motivo_rechazo": None},
            status_code=404,
        )
    return _json(encontrada)


def consultar_oferta(request: Request) -> JSONResponse:
    oferta_id = request.path_params["oferta_id"]
    conexion = conectar(get_settings().db_path)
    try:
        fila = obtener_oferta(conexion, oferta_id)
    finally:
        conexion.close()
    if fila is None:
        return JSONResponse(
            {"estado": "error", "mensaje": "oferta no encontrada o inactiva"},
            status_code=404,
        )
    return JSONResponse({"estado": "ok", **fila})


def consultar_topes(request: Request) -> JSONResponse:
    segmento = request.path_params["segmento"]
    conexion = conectar(get_settings().db_path)
    try:
        filas = listar_topes(conexion, segmento)
    finally:
        conexion.close()
    if not filas:
        return JSONResponse(
            {"estado": "error", "mensaje": "segmento desconocido"},
            status_code=404,
        )
    return JSONResponse({"estado": "ok", "segmento": segmento, "topes": filas})


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/tareas", crear_tarea, methods=["POST"]),
        Route("/tareas/{tarea_id}", consultar_tarea, methods=["GET"]),
        Route("/ofertas/{oferta_id}", consultar_oferta, methods=["GET"]),
        Route("/topes/{segmento}", consultar_topes, methods=["GET"]),
    ],
    lifespan=lifespan,
)


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
