"""Contrato HTTP del Agente 2: salud, esquema A2A y lecturas del catálogo.

Sin Ollama. La base se siembra en un archivo temporal.
"""

import pytest
from starlette.testclient import TestClient

from agente2.a2a import tareas
from agente2.config import get_settings

SITUACION_B = {
    "tarea_id": "TAR-020",
    "ticket_id": "TKT-020",
    "contacto_id": "CTO-008",
    "area_destino": "retencion",
    "prioridad": "alta",
    "riesgo_churn": True,
    "categoria": "tecnica",
    "motivo": "internet caido 5 dias, tres contactos previos, amenaza de llevarse tres lineas",
    "tono": "frustrado",
    "urgencia": "alta",
    "segmento": "regular",
    "resumen": "Falla de internet reiterada con intencion explicita de cancelar.",
}


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE2_DB_PATH", str(tmp_path / "retencion.sqlite"))
    monkeypatch.setenv("AGENTE2_EJECUTAR_PLAN", "0")
    monkeypatch.setenv("AGENTE2_CLASIFICADOR", "0")
    get_settings.cache_clear()
    tareas.reiniciar()
    from agente2.app import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
    tareas.reiniciar()


def test_health(cliente):
    respuesta = cliente.get("/health")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ok"
    assert cuerpo["servicio"] == "asesor-retencion"


def test_post_situacion_b_acepta_el_expediente(cliente):
    respuesta = cliente.post("/tareas", json=SITUACION_B)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tarea_id"] == "TAR-020"
    assert cuerpo["estado"] == "submitted"


def test_get_tarea_devuelve_la_aceptada(cliente):
    cliente.post("/tareas", json=SITUACION_B)
    respuesta = cliente.get("/tareas/TAR-020")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "submitted"


def test_sin_ticket_id_rechaza_sin_escribir_historial(cliente):
    cuerpo = dict(SITUACION_B)
    del cuerpo["ticket_id"]
    respuesta = cliente.post("/tareas", json=cuerpo)
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "rejected"
    assert respuesta.json()["motivo_rechazo"] == "esquema_invalido"
    vigentes = cliente.get("/ofertas/OFT-014")
    assert vigentes.status_code == 200


def test_riesgo_churn_falso_queda_fuera_de_retencion(cliente):
    cuerpo = dict(SITUACION_B)
    cuerpo["riesgo_churn"] = False
    respuesta = cliente.post("/tareas", json=cuerpo)
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "rejected"
    assert respuesta.json()["motivo_rechazo"] == "fuera_de_retencion"


def test_area_distinta_de_retencion_se_rechaza(cliente):
    cuerpo = dict(SITUACION_B)
    cuerpo["area_destino"] = "facturacion"
    respuesta = cliente.post("/tareas", json=cuerpo)
    assert respuesta.status_code == 200
    assert respuesta.json()["motivo_rechazo"] == "fuera_de_retencion"


def test_get_oferta_014(cliente):
    respuesta = cliente.get("/ofertas/OFT-014")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "descuento_porcentaje"
    assert cuerpo["valor"] == 20
    assert cuerpo["meses"] == 3


def test_get_oferta_inactiva_no_aparece(cliente):
    respuesta = cliente.get("/ofertas/OFT-090")
    assert respuesta.status_code == 404


def test_get_topes_regular(cliente):
    respuesta = cliente.get("/topes/regular")
    assert respuesta.status_code == 200
    topes = {fila["tipo_oferta"]: fila for fila in respuesta.json()["topes"]}
    assert topes["descuento_porcentaje"]["valor_maximo"] == 20
    assert topes["descuento_porcentaje"]["meses_maximo"] == 3
