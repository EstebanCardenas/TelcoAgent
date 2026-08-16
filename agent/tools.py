"""[SEMANA 2] Herramientas locales del agente (laboratorio 6).

Las herramientas son las capacidades que el agente puede invocar para consultar
o actuar sobre los sistemas del caso de negocio (por ejemplo, la API empresarial
de la operadora o la base de conocimiento). Cada herramienta es una función
decorada con `@tool` de LangChain, con una descripción clara: ese texto es lo
que el LLM lee para decidir cuándo usarla.

Aquí viven las herramientas de CONSULTA (solo lectura). Las herramientas de
ACCIÓN (las que modifican el estado del negocio: crear tickets, registrar
telemetría) se exponen a través del servidor MCP (`mcp_server/server.py`).

Contrato de retorno
-------------------
Toda herramienta devuelve un JSON en texto con una de estas dos formas:

    {"estado": "ok",    ...datos...}
    {"estado": "error", "codigo": "...", "mensaje": "...", "accion_sugerida": "..."}

`accion_sugerida` es deliberado: ante una falla el LLM recibe una instrucción de
qué hacer (degradar, reintentar o escalar) en vez de un stacktrace, y así no
inventa el dato que no pudo consultar.

Cada herramienta declara su `args_schema` con `Field(description=...)` enumerando
los valores aceptados: esa descripción es la guía que lee el LLM al elegirlos.
"""

import json
import time

import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from cli.config import get_settings
from agent.rag_client import RagClient, RagError

# Si el RAG responde 429 con un `Retry-After` corto, la herramienta espera y
# reintenta una vez. Si la espera es mayor, no bloquea el turno: devuelve el
# error para que el agente decida cómo seguir.
ESPERA_MAXIMA_REINTENTO_SEG = 15

# Qué debe hacer el agente ante cada modo de falla del RAG. Es la política de
# degradación del caso: nunca inventar información institucional.
_ACCION_POR_CODIGO_RAG = {
    "rate_limit": (
        "No repitas esta consulta. Continúa el análisis SIN la base de conocimiento: no inventes "
        "tarifas, horarios ni políticas. Dile al cliente que verificarás ese dato y ofrécele el "
        "siguiente paso concreto; si el caso lo amerita, escálalo."
    ),
    "pregunta_rechazada": (
        "Reformula la consulta en términos concretos y neutros (sin datos personales) e inténtalo "
        "UNA sola vez más. Si vuelve a fallar, continúa sin la base de conocimiento."
    ),
    "credenciales_invalidas": (
        "La base de conocimiento no está disponible por configuración. Continúa sin ella, no "
        "inventes información institucional y reporta la indisponibilidad en el expediente."
    ),
    "sin_configurar": (
        "La base de conocimiento no está disponible por configuración. Continúa sin ella, no "
        "inventes información institucional y reporta la indisponibilidad en el expediente."
    ),
    "coleccion_no_existe": (
        "La base de conocimiento no está disponible. Continúa sin ella y reporta la "
        "indisponibilidad en el expediente."
    ),
    "sin_conexion": (
        "El servicio de conocimiento no responde. No reintentes más de una vez: continúa el "
        "análisis con lo que dice el mensaje del cliente y deja constancia de que el dato quedó "
        "pendiente de verificación."
    ),
}
_ACCION_RAG_POR_DEFECTO = (
    "Continúa el análisis sin la base de conocimiento, no inventes información institucional y "
    "deja el dato como pendiente de verificación en el expediente."
)


def _ok(**datos) -> str:
    return json.dumps({"estado": "ok", **datos}, ensure_ascii=False)


def _error(codigo: str, mensaje: str, accion_sugerida: str, **extra) -> str:
    return json.dumps(
        {
            "estado": "error",
            "codigo": codigo,
            "mensaje": mensaje,
            "accion_sugerida": accion_sugerida,
            **extra,
        },
        ensure_ascii=False,
    )


def _get_api(ruta: str, params: dict | None = None) -> tuple[dict | list | None, str | None]:
    """GET contra la API empresarial. Devuelve (datos, error) — nunca lanza."""
    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}{ruta}"
    try:
        res = requests.get(url, params=params, timeout=10)
    except requests.RequestException as exc:
        return None, f"La API empresarial ({settings.api_base_url}) no responde: {exc}"
    if res.status_code == 404:
        return None, f"no_encontrado: {res.text[:200]}"
    if res.status_code != 200:
        return None, f"status {res.status_code}: {res.text[:200]}"
    try:
        return res.json(), None
    except ValueError:
        return None, "la API empresarial devolvió un cuerpo que no es JSON"


class ConocimientoInput(BaseModel):
    query: str = Field(
        description=(
            "Pregunta corta en lenguaje natural sobre información pública: planes, tarifas, "
            "promociones, tiendas, horarios, canales de atención o políticas. Ejemplo: "
            "'horario de la tienda de Chapinero'"
        )
    )


class PoliticaInput(BaseModel):
    tipo: str = Field(
        description=(
            "Tipo de política. Valores aceptados, exactamente uno de estos tres: "
            "'vip', 'falla-masiva', 'palabras-clave'"
        )
    )


class CasosResueltosInput(BaseModel):
    categoria: str = Field(
        default="",
        description=(
            "Categoría por la que filtrar los precedentes: 'tecnica', 'facturacion', "
            "'retencion', 'consulta'. Déjala vacía para traer todos los casos"
        ),
    )


class ContactoInput(BaseModel):
    contacto_id: str = Field(
        description="Identificador del contacto en el punto de integración, con formato CTO-001"
    )


@tool("consultar_base_conocimiento_publica", args_schema=ConocimientoInput)
def consultar_base_conocimiento_publica(query: str) -> str:
    """Consulta la base de conocimiento pública (RAG) de Telco Andina sobre catálogo de planes, tarifas, promociones, tiendas, horarios, canales de atención y políticas institucionales. Úsala para información pública que NO depende de la cuenta de un cliente: no requiere autenticar a nadie."""
    try:
        client = RagClient(get_settings())
        try:
            datos = client.query_knowledge_base(query)
        except RagError as exc:
            # Cuota por minuto agotada con espera corta: reintentar una vez.
            if exc.codigo == "rate_limit" and 0 < (exc.reintentar_en or 0) <= ESPERA_MAXIMA_REINTENTO_SEG:
                time.sleep(exc.reintentar_en)
                datos = client.query_knowledge_base(query)
            else:
                raise
        return _ok(respuesta=datos["respuesta"], fuentes=datos["fuentes"])
    except RagError as exc:
        return _error(
            exc.codigo,
            exc.mensaje,
            _ACCION_POR_CODIGO_RAG.get(exc.codigo, _ACCION_RAG_POR_DEFECTO),
            reintentar_en_segundos=exc.reintentar_en,
        )
    except Exception as exc:  # noqa: BLE001 — una tool nunca debe romper el grafo
        return _error("error_inesperado", str(exc), _ACCION_RAG_POR_DEFECTO)


@tool("consultar_politicas_institucionales", args_schema=PoliticaInput)
def consultar_politicas_institucionales(tipo: str) -> str:
    """Consulta una política de escalamiento vigente de Telco Andina por su tipo: 'vip', 'falla-masiva' o 'palabras-clave'. Úsala antes de decidir el área y la prioridad de un escalamiento, para no contradecir las reglas de la empresa."""
    tipo_normalizado = (tipo or "").strip().lower()
    datos, error = _get_api(f"/telecom/politicas/{tipo_normalizado}")
    if error:
        if error.startswith("no_encontrado"):
            return _error(
                "politica_no_existe",
                f"No existe una política registrada con el tipo '{tipo_normalizado}'.",
                "Los tipos válidos son 'vip', 'falla-masiva' y 'palabras-clave'. Corrige el tipo o "
                "continúa aplicando el criterio general de escalamiento.",
            )
        return _error(
            "api_no_disponible",
            error,
            "Continúa sin la política. Aplica el criterio general, escala si hay duda y deja "
            "constancia en el expediente de que la política no pudo verificarse.",
        )
    return _ok(politica=datos)


@tool("consultar_casos_resueltos", args_schema=CasosResueltosInput)
def consultar_casos_resueltos(categoria: str = "") -> str:
    """Consulta el repositorio histórico de casos ya resueltos (síntoma -> solución aplicada), opcionalmente filtrado por categoría ('tecnica', 'facturacion', 'retencion', 'consulta'). Úsala para proponer una solución ya probada y mantener consistencia con decisiones anteriores."""
    params = {}
    if categoria and categoria.strip():
        params["categoria"] = categoria.strip().lower()
    datos, error = _get_api("/telecom/casos-resueltos", params=params)
    if error:
        return _error(
            "api_no_disponible",
            error,
            "Continúa sin precedentes históricos: analiza el caso por su contenido y sé explícito "
            "en que la decisión no se apoyó en casos previos.",
        )
    casos = datos if isinstance(datos, list) else datos.get("casos", datos)
    if isinstance(casos, list) and not casos:
        return _ok(
            casos=[],
            nota=f"No hay precedentes registrados para la categoría '{categoria or 'todas'}'. "
            "Resuelve por criterio propio sin citar precedentes.",
        )
    return _ok(casos=casos)


@tool("obtener_contacto", args_schema=ContactoInput)
def obtener_contacto(contacto_id: str) -> str:
    """Obtiene el mensaje original del cliente y sus metadatos (canal, timestamp, id de sesión) desde el punto de integración interno, a partir del identificador del contacto (por ejemplo 'CTO-001'). Úsala cuando te den un id de contacto en lugar del texto del mensaje."""
    identificador = (contacto_id or "").strip()
    if not identificador:
        return _error(
            "contacto_id_vacio",
            "No se recibió un identificador de contacto.",
            "Pide el identificador del contacto o trabaja directamente con el texto del mensaje.",
        )
    datos, error = _get_api(f"/telecom/contactos/{identificador}")
    if error:
        if error.startswith("no_encontrado"):
            return _error(
                "contacto_no_existe",
                f"El contacto '{identificador}' no existe en el punto de integración.",
                "Verifica el identificador con quien te lo entregó. No inventes el contenido del "
                "mensaje ni continúes el análisis sobre un contacto inexistente.",
            )
        return _error(
            "api_no_disponible",
            error,
            "No es posible recuperar el mensaje original. Pide el texto del contacto directamente "
            "antes de continuar el análisis.",
        )
    return _ok(contacto=datos)


def cliente_existe(numero_identificacion: str) -> bool:
    """¿Hay un cliente con esa cédula? Consulta pública, sin autenticación.

    La API solo responde `{"existe": true|false}`, sin revelar dato alguno. El
    `cliente_id` sale del contacto, y el perfil completo exige autenticarse.
    La usa el nodo de recepción, no el modelo: por eso no es una herramienta.
    """
    cedula = (numero_identificacion or "").strip()
    if not cedula:
        return False
    datos, error = _get_api(f"/telecom/clientes/existe/{cedula}")
    if error or not isinstance(datos, dict):
        return False
    return bool(datos.get("existe"))


def get_local_tools() -> list:
    """Lista de herramientas locales del agente para consultas y conocimiento."""
    return [
        consultar_base_conocimiento_publica,
        consultar_politicas_institucionales,
        consultar_casos_resueltos,
        obtener_contacto,
    ]


def get_local_tools_by_name() -> dict:
    return {tool.name: tool for tool in get_local_tools()}
