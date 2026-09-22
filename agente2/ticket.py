"""Lectura del ticket en la API empresarial.

Única consulta permitida a esa API: comprobar que el ticket existe, sigue
abierto y está en retención. Catálogo, topes e historial no salen de aquí.
"""

import httpx

from agente2.config import get_settings

_CERRADOS = {"resuelto", "cerrado"}


def consultar_ticket(ticket_id: str) -> dict | None:
    url = f"{get_settings().api_base_url.rstrip('/')}/telecom/tickets/{ticket_id}"
    try:
        respuesta = httpx.get(url, timeout=2.0)
    except httpx.HTTPError:
        return None
    if respuesta.status_code != 200:
        return None
    try:
        datos = respuesta.json()
    except ValueError:
        return None
    return datos if isinstance(datos, dict) else None


def ticket_es_valido(ticket: dict | None) -> str | None:
    """Devuelve el motivo de rechazo o None si el ticket sirve para el plan."""
    if not ticket:
        return "ticket_desconocido"
    if str(ticket.get("estado") or "").lower() in _CERRADOS:
        return "ticket_desconocido"
    area = ticket.get("area_destino")
    if area and area != "retencion":
        return "fuera_de_retencion"
    return None
