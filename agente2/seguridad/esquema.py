"""Validación de entrada y de artefacto, y delimitadores del texto libre."""

import secrets

from agente2.contrato import PeticionRetencion, RespuestaTarea
from agente2.seguridad.clasificador import clasificar_inyeccion
from agente2.seguridad.detector_firmas import tiene_firma_de_ataque


def nueva_marca() -> str:
    """Marca por tarea. El atacante no la conoce de antemano."""
    return secrets.token_hex(8)


def envolver(texto: str, marca: str) -> str:
    return f"<<{marca}\n{texto}\n{marca}>>"


def entrada_no_confiable(
    motivo: str, resumen: str, clasificador=None
) -> bool:
    """True si hay que rechazar y no ejecutar el plan comercial."""
    texto = f"{motivo}\n{resumen}"
    if tiene_firma_de_ataque(texto):
        return True
    fn = clasificador if clasificador is not None else clasificar_inyeccion
    return bool(fn(texto))


def rechazo_entrada_no_confiable(peticion: PeticionRetencion) -> RespuestaTarea:
    return RespuestaTarea(
        tarea_id=peticion.tarea_id,
        estado="rejected",
        motivo_rechazo="entrada_no_confiable",
    )


def artefacto_mal_formado(respuesta: RespuestaTarea) -> bool:
    """Un compromiso sin oferta, o una oferta completed sin justificación."""
    compromiso = (respuesta.compromiso or "").strip()
    justificacion = (respuesta.justificacion or "").strip()
    if compromiso and not respuesta.oferta_id:
        return True
    if respuesta.estado == "completed" and respuesta.oferta_id and not justificacion:
        return True
    if respuesta.oferta_id and respuesta.valor is None:
        return True
    if respuesta.oferta_id and respuesta.meses is None:
        return True
    return False
