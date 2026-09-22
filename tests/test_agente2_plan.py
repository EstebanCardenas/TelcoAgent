"""Plan-and-Execute del Agente 2. Modelo y ticket simulados: no llama a Ollama."""

import json

from langchain.messages import AIMessage

from agente2.contrato import PeticionRetencion
from agente2.db.conexion import conectar, inicializar_bd
from agente2.db.repositorio import historial_vigente, registrar_descuento
from agente2.razonamiento.plan_execute import build_grafo, correr_plan, max_pasos
from tests.test_agente2_contrato import SITUACION_B
from tests.utiles import nombres_de_nodos

COMPROMISO_B = (
    "20% de descuento en el cargo fijo de internet durante 3 meses, "
    "vigente al restablecer el servicio. Soporte N2 queda a cargo de la falla "
    "de planta. No se promete hora de restablecimiento."
)
JUSTIFICACION_B = (
    "El motivo de desercion es la falla tecnica reiterada, no una inconformidad "
    "tarifaria. OFT-014 respeta el tope del segmento regular y no figura en el "
    "historial de CTO-008."
)


def _ticket_ok(_ticket_id: str) -> dict:
    return {"id": _ticket_id, "estado": "abierto", "area_destino": "retencion"}


class ModeloFijo:
    """Devuelve JSON fijo. Distingue elegir de redactar por la marca del prompt."""

    def __init__(self, oferta_id: str, compromiso: str = "", justificacion: str = ""):
        self.oferta_id = oferta_id
        self.compromiso = compromiso
        self.justificacion = justificacion
        self.llamadas = 0

    def invoke(self, mensajes, **_kwargs):
        self.llamadas += 1
        texto = " ".join(str(getattr(m, "content", m)) for m in mensajes)
        if "PASO_ELEGIR" in texto:
            cuerpo = json.dumps({"oferta_id": self.oferta_id})
        else:
            cuerpo = json.dumps(
                {"compromiso": self.compromiso, "justificacion": self.justificacion}
            )
        return AIMessage(content=cuerpo)


def _correr(tmp_path, cuerpo: dict, modelo: ModeloFijo, ticket=None):
    ruta = tmp_path / "retencion.sqlite"
    inicializar_bd(ruta)
    peticion = PeticionRetencion.model_validate(cuerpo)
    return correr_plan(
        peticion,
        modelo=modelo,
        consultar_ticket=ticket or _ticket_ok,
        db_path=str(ruta),
    ), ruta


def test_el_grafo_compila_con_nodos_de_plan():
    grafo = build_grafo(
        modelo=ModeloFijo("OFT-014"),
        consultar_ticket=_ticket_ok,
        db_path=":memory:",
    )
    nodos = nombres_de_nodos(grafo)
    assert "planificar" in nodos
    assert "elegir_oferta" in nodos
    assert "recuperar" in nodos
    assert max_pasos >= 10


def test_situacion_b_otorga_oft_014(tmp_path):
    modelo = ModeloFijo("OFT-014", COMPROMISO_B, JUSTIFICACION_B)
    resultado, ruta = _correr(tmp_path, SITUACION_B, modelo)

    assert resultado.estado == "completed"
    assert resultado.oferta_id == "OFT-014"
    assert resultado.tipo == "descuento_porcentaje"
    assert resultado.valor == 20
    assert resultado.meses == 3
    assert resultado.deriva_n2 is True
    assert resultado.compromiso
    assert "20%" in resultado.compromiso
    assert modelo.llamadas == 2

    conexion = conectar(ruta)
    try:
        vigentes = {fila["oferta_id"] for fila in historial_vigente(conexion, "CTO-008")}
    finally:
        conexion.close()
    assert "OFT-014" in vigentes


def test_historial_de_cto_001_no_repite_oft_014(tmp_path):
    cuerpo = dict(SITUACION_B)
    cuerpo["tarea_id"] = "TAR-001"
    cuerpo["ticket_id"] = "TKT-001"
    cuerpo["contacto_id"] = "CTO-001"
    modelo = ModeloFijo("OFT-014", "10% por 2 meses.", "Siguiente elegible.")
    resultado, _ruta = _correr(tmp_path, cuerpo, modelo)

    assert resultado.estado == "completed"
    assert resultado.oferta_id != "OFT-014"
    assert resultado.oferta_id == "OFT-013"
    assert resultado.valor == 10
    assert resultado.meses == 2


def test_conjunto_vacio_no_entrega_cifras(tmp_path):
    ruta = tmp_path / "retencion.sqlite"
    inicializar_bd(ruta)
    conexion = conectar(ruta)
    try:
        for oferta_id, meses in (("OFT-010", 1), ("OFT-013", 2), ("OFT-014", 3)):
            registrar_descuento(conexion, "CTO-099", oferta_id, meses)
    finally:
        conexion.close()

    cuerpo = dict(SITUACION_B)
    cuerpo["tarea_id"] = "TAR-099"
    cuerpo["ticket_id"] = "TKT-099"
    cuerpo["contacto_id"] = "CTO-099"
    modelo = ModeloFijo("OFT-014", "no deberia usarse", "no")
    peticion = PeticionRetencion.model_validate(cuerpo)
    resultado = correr_plan(
        peticion,
        modelo=modelo,
        consultar_ticket=_ticket_ok,
        db_path=str(ruta),
    )

    assert resultado.oferta_id is None
    assert resultado.valor is None
    assert resultado.meses is None
    assert resultado.compromiso == ""
    assert modelo.llamadas == 0


def test_el_modelo_no_puede_otorgar_oft_090(tmp_path):
    modelo = ModeloFijo("OFT-090", COMPROMISO_B, JUSTIFICACION_B)
    resultado, _ruta = _correr(tmp_path, SITUACION_B, modelo)

    assert resultado.oferta_id != "OFT-090"
    assert resultado.oferta_id == "OFT-014"
    assert resultado.valor == 20
    assert resultado.meses == 3


def test_ticket_desconocido_no_ejecuta_el_plan_comercial(tmp_path):
    modelo = ModeloFijo("OFT-014", COMPROMISO_B, JUSTIFICACION_B)
    resultado, ruta = _correr(tmp_path, SITUACION_B, modelo, ticket=lambda _id: None)

    assert resultado.estado == "rejected"
    assert resultado.motivo_rechazo == "ticket_desconocido"
    assert resultado.oferta_id is None
    assert modelo.llamadas == 0

    conexion = conectar(ruta)
    try:
        vigentes = historial_vigente(conexion, "CTO-008")
    finally:
        conexion.close()
    assert vigentes == []
