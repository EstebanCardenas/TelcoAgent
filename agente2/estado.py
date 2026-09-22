"""Estado del plan fijo del Asesor de Retención."""

from typing import TypedDict


class EstadoPlan(TypedDict, total=False):
    expediente: dict
    plan: list[str]
    paso_actual: int
    max_pasos: int
    topes: list[dict]
    ofertas_candidatas: list[dict]
    ofertas_otorgadas: list[dict]
    elegibles: list[dict]
    oferta_pedida: str
    oferta_elegida: dict
    deriva_n2: bool
    compromiso: str
    justificacion: str
    estado: str
    motivo_rechazo: str
    marca_dato: str
