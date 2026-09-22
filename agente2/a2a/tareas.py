"""Almacén en memoria de las tareas A2A del Asesor de Retención."""

from agente2.contrato import (
    RespuestaTarea,
    parsear_peticion,
    rechazo_fuera_de_retencion,
)

_TAREAS: dict[str, RespuestaTarea] = {}


def reiniciar() -> None:
    _TAREAS.clear()


def registrar(respuesta: RespuestaTarea) -> RespuestaTarea:
    if respuesta.tarea_id:
        _TAREAS[respuesta.tarea_id] = respuesta
    return respuesta


def obtener(tarea_id: str) -> RespuestaTarea | None:
    return _TAREAS.get(tarea_id)


def aceptar_o_rechazar(cuerpo: dict) -> RespuestaTarea:
    """Valida el expediente y deja la tarea en submitted o rejected.

    El plan comercial (Fase 3) aún no corre. Una petición válida queda
    en `submitted` para que el Agente 1 confirme recepción.
    """
    peticion, rechazo = parsear_peticion(cuerpo)
    if rechazo is not None:
        return registrar(rechazo)

    assert peticion is not None
    if not peticion.riesgo_churn or peticion.area_destino != "retencion":
        return registrar(rechazo_fuera_de_retencion(peticion))

    return registrar(
        RespuestaTarea(tarea_id=peticion.tarea_id, estado="submitted")
    )
