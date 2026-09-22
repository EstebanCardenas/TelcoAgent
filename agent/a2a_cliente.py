"""Cliente A2A del Agente 1 hacia el Asesor de Retención.

El modelo de primera línea no llama a este módulo. Lo hace el nodo `acciones`,
después de crear el ticket y antes de `respuesta`.
"""

import json
import re
import time

import httpx
from langchain.messages import ToolMessage

from agente2.contrato import RespuestaTarea
from agente2.seguridad.detector_firmas import tiene_firma_de_ataque
from agente2.seguridad.esquema import artefacto_mal_formado
from cli.config import get_settings

TERMINALES = frozenset({"completed", "rejected", "failed"})
ESPERA_SUBMITTED_S = 2.0
ESPERA_WORKING_S = 8.0
INTERVALO_SONDEO_S = 0.2

_CATEGORIAS = ("tecnica", "facturacion", "retencion", "consulta", "otro")
_TONOS = ("frustrado", "urgente", "agresivo", "neutro", "cordial")
_URGENCIAS = ("alta", "media", "baja")
_PRIORIDADES = ("baja", "media", "alta", "critica")
_BLOQUE_INTERNO = re.compile(r"===.*?===", re.DOTALL)


def tarea_id_desde_ticket(ticket_id: str) -> str:
    match = re.fullmatch(r"TKT-(\d+)", ticket_id or "")
    if match:
        return f"TAR-{match.group(1)}"
    return "TAR-0"


def resolver_segmento(state: dict) -> str:
    """VIP solo si el perfil autenticado o una herramienta lo marcaron.

    El texto del cliente no mueve este campo.
    """
    if state.get("segmento") == "VIP":
        return "VIP"
    for mensaje in state.get("messages") or []:
        if not isinstance(mensaje, ToolMessage):
            continue
        try:
            datos = json.loads(str(mensaje.content))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(datos, dict):
            continue
        cliente = datos.get("cliente") if isinstance(datos.get("cliente"), dict) else datos
        if cliente.get("vip") is True:
            return "VIP"
    return "regular"


def _neutralizar(texto: str) -> str:
    limpio = _BLOQUE_INTERNO.sub(" ", texto or "")
    lineas = [linea for linea in limpio.splitlines() if not tiene_firma_de_ataque(linea)]
    return re.sub(r"\s+", " ", " ".join(lineas)).strip()


def sanear_expediente(state: dict) -> tuple[str, str]:
    """motivo y resumen salen de la clasificación, no del chat crudo."""
    categoria = state.get("categoria") if state.get("categoria") in _CATEGORIAS else "otro"
    tono = state.get("tono") if state.get("tono") in _TONOS else "neutro"
    urgencia = state.get("urgencia") if state.get("urgencia") in _URGENCIAS else "media"
    amenaza = "con amenaza de cancelacion" if state.get("riesgo_churn") else "sin amenaza de cancelacion"
    if categoria == "tecnica":
        hecho = "Falla tecnica de servicio"
    elif categoria == "facturacion":
        hecho = "Inconformidad de facturacion"
    else:
        hecho = f"Caso de categoria {categoria}"
    motivo = _neutralizar(f"{hecho} {amenaza}.")
    resumen = _neutralizar(
        f"{hecho}. Tono {tono}, urgencia {urgencia}. {amenaza.capitalize()}."
    )[:500]
    return motivo, resumen


def consultar_retencion(
    peticion: dict,
    *,
    post=None,
    get=None,
    espera_submitted: float = ESPERA_SUBMITTED_S,
    espera_working: float = ESPERA_WORKING_S,
    intervalo: float = INTERVALO_SONDEO_S,
    dormir=time.sleep,
    reloj=time.monotonic,
) -> dict:
    """POST con un reenvío si no hay submitted; luego sondeo hasta 8 s."""
    tarea_id = peticion.get("tarea_id") or "TAR-0"
    post = post or _post_http
    get = get or _get_http

    recibida = None
    for _intento in (1, 2):
        try:
            recibida = post(peticion)
        except Exception:
            recibida = None
        if isinstance(recibida, dict) and recibida.get("estado") in (
            "submitted",
            *TERMINALES,
        ):
            break
        dormir(min(espera_submitted, 0.05))
        recibida = None

    if recibida is None:
        return {"tarea_id": tarea_id, "estado": "failed"}
    if recibida.get("estado") in TERMINALES:
        return recibida

    inicio = reloj()
    while reloj() - inicio < espera_working:
        try:
            actual = get(tarea_id)
        except Exception:
            actual = None
        if isinstance(actual, dict) and actual.get("estado") in TERMINALES:
            return actual
        dormir(intervalo)
    return {"tarea_id": tarea_id, "estado": "failed"}


def _post_http(peticion: dict) -> dict:
    url = f"{get_settings().agente2_base_url.rstrip('/')}/tareas"
    respuesta = httpx.post(url, json=peticion, timeout=ESPERA_SUBMITTED_S)
    respuesta.raise_for_status()
    datos = respuesta.json()
    if not isinstance(datos, dict):
        raise ValueError("respuesta A2A ilegible")
    return datos


def _get_http(tarea_id: str) -> dict:
    url = f"{get_settings().agente2_base_url.rstrip('/')}/tareas/{tarea_id}"
    respuesta = httpx.get(url, timeout=ESPERA_SUBMITTED_S)
    respuesta.raise_for_status()
    datos = respuesta.json()
    if not isinstance(datos, dict):
        raise ValueError("respuesta A2A ilegible")
    return datos


def obtener_oferta_remota(oferta_id: str) -> dict | None:
    url = f"{get_settings().agente2_base_url.rstrip('/')}/ofertas/{oferta_id}"
    try:
        respuesta = httpx.get(url, timeout=ESPERA_SUBMITTED_S)
    except httpx.HTTPError:
        return None
    if respuesta.status_code != 200:
        return None
    try:
        datos = respuesta.json()
    except ValueError:
        return None
    return datos if isinstance(datos, dict) else None


def obtener_tope_remoto(segmento: str, tipo_oferta: str) -> dict | None:
    url = f"{get_settings().agente2_base_url.rstrip('/')}/topes/{segmento}"
    try:
        respuesta = httpx.get(url, timeout=ESPERA_SUBMITTED_S)
    except httpx.HTTPError:
        return None
    if respuesta.status_code != 200:
        return None
    try:
        datos = respuesta.json()
    except ValueError:
        return None
    for fila in datos.get("topes") or []:
        if fila.get("tipo_oferta") == tipo_oferta:
            return fila
    return None


def validar_artefacto(
    crudo: dict,
    tarea_id: str,
    segmento: str,
    *,
    consultar_oferta=None,
    consultar_tope=None,
) -> dict | None:
    """None si el Agente 1 no debe citar cifras."""
    consultar_oferta = consultar_oferta or obtener_oferta_remota
    consultar_tope = consultar_tope or obtener_tope_remoto
    if not isinstance(crudo, dict):
        return None
    if crudo.get("tarea_id") != tarea_id:
        return None
    if crudo.get("estado") != "completed":
        return None
    try:
        respuesta = RespuestaTarea.model_validate(crudo)
    except Exception:
        return None
    if not (respuesta.compromiso or "").strip():
        return None
    if artefacto_mal_formado(respuesta):
        return None
    oferta = consultar_oferta(respuesta.oferta_id)
    if not oferta:
        return None
    if respuesta.valor != oferta.get("valor") or respuesta.meses != oferta.get("meses"):
        return None
    if respuesta.tipo and oferta.get("tipo") and respuesta.tipo != oferta.get("tipo"):
        return None
    tope = consultar_tope(segmento, oferta.get("tipo") or respuesta.tipo)
    if not tope:
        return None
    if respuesta.valor > tope["valor_maximo"] or respuesta.meses > tope["meses_maximo"]:
        return None
    return crudo


def _uno(valor, permitidos: tuple, por_defecto: str) -> str:
    texto = str(valor or "").strip().lower()
    return texto if texto in permitidos else por_defecto


def armar_peticion(state: dict, ticket_id: str) -> dict:
    motivo, resumen = sanear_expediente(state)
    return {
        "tarea_id": tarea_id_desde_ticket(ticket_id),
        "ticket_id": ticket_id,
        "contacto_id": state.get("contacto_id") or "",
        "area_destino": "retencion",
        "segmento": resolver_segmento(state),
        "categoria": _uno(state.get("categoria"), _CATEGORIAS, "otro"),
        "motivo": motivo,
        "resumen": resumen,
        "prioridad": _uno(state.get("prioridad"), _PRIORIDADES, "alta"),
        "riesgo_churn": True,
        "tono": _uno(state.get("tono"), _TONOS, "neutro"),
        "urgencia": _uno(state.get("urgencia"), _URGENCIAS, "media"),
    }


def procesar_retencion(
    state: dict,
    ticket_id: str,
    *,
    consultar=None,
    consultar_oferta=None,
    consultar_tope=None,
) -> dict:
    """Campos para mezclar en el estado. Dict vacío si no corresponde consultar."""
    if state.get("decision") != "escalar":
        return {}
    if state.get("area_destino") != "retencion":
        return {}
    if not state.get("riesgo_churn"):
        return {}
    if not ticket_id:
        return {}

    peticion = armar_peticion(state, ticket_id)
    consultar = consultar or consultar_retencion
    try:
        crudo = consultar(peticion)
    except Exception:
        crudo = {"tarea_id": peticion["tarea_id"], "estado": "failed"}
    if not isinstance(crudo, dict):
        crudo = {"tarea_id": peticion["tarea_id"], "estado": "failed"}

    autorizado = validar_artefacto(
        crudo,
        peticion["tarea_id"],
        peticion["segmento"],
        consultar_oferta=consultar_oferta,
        consultar_tope=consultar_tope,
    )
    if autorizado:
        estado = "completed"
        deriva = bool(autorizado.get("deriva_n2"))
    elif crudo.get("estado") == "rejected":
        estado = "rejected"
        deriva = bool(crudo.get("deriva_n2"))
    else:
        estado = "failed"
        deriva = False
    return {
        "segmento": peticion["segmento"],
        "tarea_id": peticion["tarea_id"],
        "estado_tarea_a2a": estado,
        "compromiso_retencion": (autorizado or {}).get("compromiso") or "",
        "oferta_retencion": (autorizado or {}).get("oferta_id"),
        "deriva_n2": deriva,
    }


def bloque_compromiso(state: dict) -> str:
    texto = (state.get("compromiso_retencion") or "").strip()
    if texto:
        return (
            "Compromiso de retención autorizado (cítalo tal cual; no reescribas "
            f"la cifra ni los meses):\n{texto}\n"
            "Prohibido inventar otro porcentaje o vigencia."
        )
    if state.get("decision") == "escalar" and state.get("area_destino") == "retencion":
        return (
            "No hay compromiso comercial autorizado en este turno. "
            "Informa el escalamiento a retención. No nombres porcentajes ni meses."
        )
    return "No aplica un compromiso de retención."
