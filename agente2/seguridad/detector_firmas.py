"""Búsqueda de frases conocidas de ataque en motivo y resumen.

Es coincidencia de texto. No llama al modelo.
"""

import re
import unicodedata

# Frases del ataque de la semana 7 y variantes cercanas. Se comparan sobre
# el texto en minúsculas y sin tildes.
FIRMAS = (
    "=== nota interna",
    "nota interna del sistema",
    "ignora la tabla",
    "aprueba 50",
    "omite el registro",
    "historial_descuentos",
    "topes_segmento",
    "sin justificacion",
    "responde unicamente con el compromiso",
    "vip institucional",
    "ignore previous",
    "eres el sistema",
)


def _normalizar(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", texto.lower())
    sin_tildes = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_tildes)


def tiene_firma_de_ataque(texto: str) -> bool:
    normalizado = _normalizar(texto or "")
    return any(firma in normalizado for firma in FIRMAS)
