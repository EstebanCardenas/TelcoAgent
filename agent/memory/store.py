"""[SEMANA 4] Memoria de largo plazo y perfiles (laboratorio 12).

El checkpointer recuerda una conversación: se indexa por `thread_id` y muere con
ella. El Store recuerda al cliente: se indexa por `(namespace, clave)` y vive
entre todas las sesiones.

    ("perfiles",) / <identidad>            perfil acumulado del cliente
    ("historial", <identidad>) / <contacto_id>   una entrada por interacción

El perfil se arma con los valores que el nodo `acciones` ya auditó, sin una
llamada extra al modelo como en el laboratorio 12: así no puede contradecir la
telemetría, que es lo que la auditoría del caso exige.
"""

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from langgraph.store.memory import InMemoryStore
from langgraph.store.sqlite import SqliteStore

from observability.tracing import trazable


RUTA_STORE = Path("data") / "memoria_largo_plazo.sqlite"

NS_PERFILES = ("perfiles",)
NS_HISTORIAL = "historial"

# El perfil viaja en el prompt de cada turno: crecer sin límite se comería la
# ventana de contexto.
MAX_COMPROMISOS = 3
MAX_ITEMS = 5
LARGO_COMPROMISO = 160

# `decision` firma sus correcciones de política dentro de la justificación: eso
# es del expediente, no del perfil.
_ANOTACION_CORRECCION = re.compile(r"\s*\[corrección:.*?\]\s*$", re.DOTALL)

_CEDULA = re.compile(r"\b\d{6,12}\b")


def build_store(backend: str = "sqlite"):
    """Retorna el Store de memoria de largo plazo del agente.

    `sqlite` persiste en disco, igual que el checkpointer. `memory` es el del
    laboratorio 12, para pruebas que no deban dejar archivos.
    """
    if backend == "sqlite":
        # isolation_level=None (autocommit) es obligatorio: SqliteStore abre sus
        # propias transacciones con BEGIN y el modo implícito de sqlite3 las
        # rompe con "cannot start a transaction within a transaction".
        RUTA_STORE.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(RUTA_STORE), check_same_thread=False, isolation_level=None)
        store = SqliteStore(conn)
        store.setup()
        return store
    if backend == "memory":
        return InMemoryStore()
    raise ValueError(f"Backend no soportado: {backend}")


def identidad_cliente(state) -> str | None:
    """Clave con la que se archiva a un cliente, independiente del `thread_id`.

    La cédula sirve cuando la API no respondió y no hay `cliente_id`. El último
    recurso es la identidad de un turno anterior: nadie repite su cédula en cada
    mensaje, y sin eso el segundo turno de una sesión quedaría sin archivar.
    """
    if state.get("cliente_id"):
        return str(state["cliente_id"])

    cedula = _CEDULA.search(state.get("texto_contacto") or "")
    if cedula:
        return f"cedula:{cedula.group(0)}"

    return state.get("identidad_memoria") or None


# ── Lectura ──────────────────────────────────────────────────────────────────

@trazable(name="store_cargar_perfil")
def cargar_perfil(store, identidad: str) -> dict | None:
    """Perfil acumulado del cliente, o None si nunca ha escrito antes."""
    if store is None or not identidad:
        return None
    item = store.get(NS_PERFILES, identidad)
    return item.value if item else None


@trazable(name="store_historial")
def historial_cliente(store, identidad: str, limite: int = 20) -> list[dict]:
    """Interacciones anteriores del cliente, de la más nueva a la más vieja."""
    if store is None or not identidad:
        return []
    items = store.search((NS_HISTORIAL, identidad), limit=limite)
    return sorted(
        (item.value for item in items),
        key=lambda v: v.get("fecha", ""),
        reverse=True,
    )


def perfil_a_texto(perfil: dict | None) -> str:
    """Vuelve el perfil una línea legible para inyectarla en los prompts."""
    if not perfil:
        return ""

    partes = []

    if perfil.get("interacciones"):
        partes.append(f"{perfil['interacciones']} contacto(s) previo(s) registrado(s)")

    categorias = perfil.get("categorias") or {}
    if categorias:
        detalle = ", ".join(
            f"{nombre} x{veces}" for nombre, veces in sorted(categorias.items(), key=lambda p: -p[1])
        )
        partes.append(f"categorías reportadas: {detalle}")

    if perfil.get("riesgo_churn_historico"):
        partes.append("ya amenazó con cancelar en una interacción anterior")

    if perfil.get("areas_escalamiento"):
        partes.append(f"escalado antes a: {', '.join(perfil['areas_escalamiento'])}")

    if perfil.get("tickets"):
        partes.append(f"tickets abiertos previamente: {', '.join(perfil['tickets'])}")

    if perfil.get("compromisos"):
        partes.append("compromisos anteriores: " + " | ".join(perfil["compromisos"]))

    if perfil.get("ultima_interaccion"):
        partes.append(f"último contacto: {perfil['ultima_interaccion'][:10]}")

    # rstrip: los compromisos ya vienen con punto final y quedaría duplicado.
    return ". ".join(parte.rstrip(". ") for parte in partes) + "." if partes else ""


# ── Escritura ────────────────────────────────────────────────────────────────

def _recortar(lista: list, maximo: int) -> list:
    """Conserva los últimos `maximo` elementos, sin repetidos."""
    vistos, salida = set(), []
    for valor in lista:
        if valor and valor not in vistos:
            vistos.add(valor)
            salida.append(valor)
    return salida[-maximo:]


def _compromiso(justificacion: str) -> str:
    """Deja la justificación en una frase corta, sin la anotación de auditoría."""
    texto = _ANOTACION_CORRECCION.sub("", justificacion or "").strip()
    if len(texto) <= LARGO_COMPROMISO:
        return texto

    recorte = texto[:LARGO_COMPROMISO]
    corte = max(recorte.rfind("."), recorte.rfind(" "))
    return (recorte[: corte + 1] if corte > 0 else recorte).strip() + "…"


@trazable(name="store_actualizar_perfil")
def actualizar_perfil(store, identidad: str, state) -> dict | None:
    """Funde lo que este turno dejó en el estado con el perfil ya guardado."""
    if store is None or not identidad:
        return None

    perfil = dict(cargar_perfil(store, identidad) or {})
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    perfil["identidad"] = identidad
    perfil["interacciones"] = perfil.get("interacciones", 0) + 1
    perfil["ultima_interaccion"] = ahora

    if state.get("cliente_id"):
        perfil["cliente_id"] = state["cliente_id"]

    categorias = dict(perfil.get("categorias") or {})
    for clave in ("categoria", "categoria_secundaria"):
        if state.get(clave):
            categorias[state[clave]] = categorias.get(state[clave], 0) + 1
    perfil["categorias"] = categorias

    # Quien amenazó con irse sigue siendo riesgo aunque hoy escriba tranquilo.
    perfil["riesgo_churn_historico"] = bool(
        perfil.get("riesgo_churn_historico") or state.get("riesgo_churn")
    )

    if state.get("ticket_id"):
        perfil["tickets"] = _recortar([*(perfil.get("tickets") or []), state["ticket_id"]], MAX_ITEMS)
    if state.get("decision") == "escalar" and state.get("area_destino"):
        perfil["areas_escalamiento"] = _recortar(
            [*(perfil.get("areas_escalamiento") or []), state["area_destino"]], MAX_ITEMS
        )

    compromiso = _compromiso(state.get("justificacion") or "")
    if compromiso:
        perfil["compromisos"] = _recortar(
            [*(perfil.get("compromisos") or []), compromiso], MAX_COMPROMISOS
        )

    store.put(NS_PERFILES, identidad, perfil)

    clave = state.get("contacto_id") or f"sin-contacto-{perfil['interacciones']:04d}"
    store.put(
        (NS_HISTORIAL, identidad),
        clave,
        {
            "fecha": ahora,
            "contacto_id": state.get("contacto_id") or "",
            "categoria": state.get("categoria"),
            "urgencia": state.get("urgencia"),
            "tono": state.get("tono"),
            "riesgo_churn": bool(state.get("riesgo_churn")),
            "decision": state.get("decision"),
            "area_destino": state.get("area_destino"),
            "ticket_id": state.get("ticket_id"),
            "telemetria_id": state.get("telemetria_id"),
            "resumen": (state.get("texto_contacto") or "")[:300],
        },
    )

    return perfil
