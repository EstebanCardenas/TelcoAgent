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
from observability.tracing import (
    anotar_evento,
    anotar_traza,
    entradas_sin_llamables,
    etiquetar_traza,
    trazable,
)

_ETIQUETAS_RETENCION = ["retencion", "a2a", "agente1"]

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


def _entradas_expediente(entradas: dict) -> dict:
    """Lo que LangSmith debe mostrar al armar el expediente, sin el chat."""
    state = entradas.get("state") if isinstance(entradas.get("state"), dict) else {}
    return {
        "ticket_id": entradas.get("ticket_id"),
        "contacto_id": state.get("contacto_id"),
        "categoria": state.get("categoria"),
        "tono": state.get("tono"),
        "urgencia": state.get("urgencia"),
        "prioridad": state.get("prioridad"),
        "riesgo_churn": bool(state.get("riesgo_churn")),
        "segmento": state.get("segmento"),
    }


def _omitir_retencion(motivo: str) -> dict:
    anotar_traza(aplica=False, motivo_omision=motivo)
    etiquetar_traza("retencion-omitida")
    anotar_evento(f"No se consultó retención: {motivo}.")
    return {}


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


@trazable(
    name="retencion-consultar-a2a",
    tags=_ETIQUETAS_RETENCION,
    metadata={"paso": "retencion"},
    process_inputs=entradas_sin_llamables,
)
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
    intentos_post = 0
    sondeos = 0

    def cerrar(resultado: dict, *, agoto_espera: bool) -> dict:
        anotar_traza(
            intentos_post=intentos_post,
            sondeos=sondeos,
            estado=resultado.get("estado"),
            agoto_espera=agoto_espera,
        )
        etiquetar_traza(f"a2a-{resultado.get('estado') or 'sin-estado'}")
        return resultado

    recibida = None
    for _intento in (1, 2):
        intentos_post += 1
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
        return cerrar({"tarea_id": tarea_id, "estado": "failed"}, agoto_espera=False)
    if recibida.get("estado") in TERMINALES:
        return cerrar(recibida, agoto_espera=False)

    inicio = reloj()
    while reloj() - inicio < espera_working:
        sondeos += 1
        try:
            actual = get(tarea_id)
        except Exception:
            actual = None
        if isinstance(actual, dict) and actual.get("estado") in TERMINALES:
            return cerrar(actual, agoto_espera=False)
        dormir(intervalo)
    return cerrar({"tarea_id": tarea_id, "estado": "failed"}, agoto_espera=True)


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


@trazable(
    name="retencion-consultar-oferta",
    run_type="tool",
    tags=_ETIQUETAS_RETENCION,
    metadata={"paso": "retencion"},
)
def obtener_oferta_remota(oferta_id: str) -> dict | None:
    url = f"{get_settings().agente2_base_url.rstrip('/')}/ofertas/{oferta_id}"
    datos = None
    motivo = None
    try:
        respuesta = httpx.get(url, timeout=ESPERA_SUBMITTED_S)
    except httpx.HTTPError:
        motivo = "sin_respuesta"
    else:
        if respuesta.status_code != 200:
            motivo = f"http_{respuesta.status_code}"
        else:
            try:
                cuerpo = respuesta.json()
            except ValueError:
                motivo = "json_invalido"
            else:
                if isinstance(cuerpo, dict):
                    datos = cuerpo
                else:
                    motivo = "cuerpo_invalido"
    anotar_traza(
        oferta_id=oferta_id,
        encontrada=datos is not None,
        motivo=motivo,
        tipo=(datos or {}).get("tipo"),
        valor=(datos or {}).get("valor"),
        meses=(datos or {}).get("meses"),
    )
    return datos


@trazable(
    name="retencion-consultar-tope",
    run_type="tool",
    tags=_ETIQUETAS_RETENCION,
    metadata={"paso": "retencion"},
)
def obtener_tope_remoto(segmento: str, tipo_oferta: str) -> dict | None:
    url = f"{get_settings().agente2_base_url.rstrip('/')}/topes/{segmento}"
    fila = None
    motivo = None
    try:
        respuesta = httpx.get(url, timeout=ESPERA_SUBMITTED_S)
    except httpx.HTTPError:
        motivo = "sin_respuesta"
    else:
        if respuesta.status_code != 200:
            motivo = f"http_{respuesta.status_code}"
        else:
            try:
                datos = respuesta.json()
            except ValueError:
                motivo = "json_invalido"
            else:
                if not isinstance(datos, dict):
                    motivo = "cuerpo_invalido"
                else:
                    for candidata in datos.get("topes") or []:
                        if candidata.get("tipo_oferta") == tipo_oferta:
                            fila = candidata
                            break
                    if fila is None:
                        motivo = "tipo_sin_tope"
    anotar_traza(
        segmento=segmento,
        tipo_oferta=tipo_oferta,
        encontrado=fila is not None,
        motivo=motivo,
        valor_maximo=(fila or {}).get("valor_maximo"),
        meses_maximo=(fila or {}).get("meses_maximo"),
    )
    return fila


def _salida_validacion(salida):
    """La traza muestra el veredicto, no el cuerpo crudo cuando no autoriza."""
    if not isinstance(salida, dict):
        return {"autorizado": False}
    return {
        "autorizado": True,
        "tarea_id": salida.get("tarea_id"),
        "estado": salida.get("estado"),
        "oferta_id": salida.get("oferta_id"),
        "tipo": salida.get("tipo"),
        "valor": salida.get("valor"),
        "meses": salida.get("meses"),
        "deriva_n2": bool(salida.get("deriva_n2")),
        "compromiso": salida.get("compromiso") or "",
    }


@trazable(
    name="retencion-validar-artefacto",
    tags=_ETIQUETAS_RETENCION,
    metadata={"paso": "retencion"},
    process_inputs=entradas_sin_llamables,
    process_outputs=_salida_validacion,
)
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

    def no(motivo: str):
        anotar_traza(autorizado=False, motivo_no_autorizado=motivo)
        etiquetar_traza("artefacto-rechazado")
        anotar_evento(f"Artefacto no autorizado: {motivo}.", en_padre=True)
        return None

    if not isinstance(crudo, dict):
        return no("la respuesta no es un objeto")
    if crudo.get("tarea_id") != tarea_id:
        return no("tarea_id no coincide")
    if crudo.get("estado") != "completed":
        return no("estado distinto de completed")
    try:
        respuesta = RespuestaTarea.model_validate(crudo)
    except Exception:
        return no("esquema invalido")
    if not (respuesta.compromiso or "").strip():
        return no("compromiso vacio")
    if artefacto_mal_formado(respuesta):
        return no("artefacto mal formado")
    oferta = consultar_oferta(respuesta.oferta_id)
    if not oferta:
        return no("oferta no encontrada")
    if respuesta.valor != oferta.get("valor") or respuesta.meses != oferta.get("meses"):
        return no("valor o meses no coinciden con el catalogo")
    if respuesta.tipo and oferta.get("tipo") and respuesta.tipo != oferta.get("tipo"):
        return no("tipo distinto del catalogo")
    tope = consultar_tope(segmento, oferta.get("tipo") or respuesta.tipo)
    if not tope:
        return no("tope no encontrado")
    if respuesta.valor > tope["valor_maximo"] or respuesta.meses > tope["meses_maximo"]:
        return no("excede el tope")
    anotar_traza(
        autorizado=True,
        oferta_id=respuesta.oferta_id,
        tipo=respuesta.tipo,
        valor=respuesta.valor,
        meses=respuesta.meses,
        deriva_n2=bool(respuesta.deriva_n2),
    )
    etiquetar_traza("artefacto-autorizado")
    anotar_evento(
        f"Compromiso autorizado ({respuesta.oferta_id}, {respuesta.valor}, {respuesta.meses} meses).",
        en_padre=True,
    )
    return crudo


def _uno(valor, permitidos: tuple, por_defecto: str) -> str:
    texto = str(valor or "").strip().lower()
    return texto if texto in permitidos else por_defecto


@trazable(
    name="retencion-armar-expediente",
    tags=_ETIQUETAS_RETENCION,
    metadata={"paso": "retencion"},
    process_inputs=_entradas_expediente,
)
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
        return _omitir_retencion("decision distinta de escalar")
    if state.get("area_destino") != "retencion":
        return _omitir_retencion("area_destino distinta de retencion")
    if not state.get("riesgo_churn"):
        return _omitir_retencion("riesgo_churn es falso")
    if not ticket_id:
        return _omitir_retencion("sin ticket_id")

    peticion = armar_peticion(state, ticket_id)
    anotar_traza(aplica=True, tarea_id=peticion["tarea_id"], segmento=peticion["segmento"])
    anotar_evento(
        f"Expediente {peticion['tarea_id']}, segmento {peticion['segmento']}."
    )
    consultar = consultar or consultar_retencion
    try:
        crudo = consultar(peticion)
    except Exception:
        crudo = {"tarea_id": peticion["tarea_id"], "estado": "failed"}
    if not isinstance(crudo, dict):
        crudo = {"tarea_id": peticion["tarea_id"], "estado": "failed"}
    anotar_evento(f"El Asesor respondió {crudo.get('estado') or 'sin estado'}.")

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
    anotar_traza(
        estado_tarea_a2a=estado,
        oferta_retencion=(autorizado or {}).get("oferta_id"),
        deriva_n2=deriva,
        compromiso_autorizado=bool((autorizado or {}).get("compromiso")),
    )
    etiquetar_traza(f"a2a-{estado}")
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
