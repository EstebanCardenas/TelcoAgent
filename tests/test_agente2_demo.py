"""Cierre de la Fase 6: Situación B por HTTP deja estados, OFT-014 e historial."""

from tests.probar_retencion_situacion_b import ejecutar_demo


def test_situacion_b_completa_con_oft_014_e_historial(tmp_path):
    resultado = ejecutar_demo(tmp_path / "retencion.sqlite")
    estados = resultado["estados"]
    respuesta = resultado["respuesta"]

    assert "submitted" in estados
    assert "working" in estados
    assert estados[-1] == "completed"
    assert respuesta["oferta_id"] == "OFT-014"
    assert respuesta["valor"] == 20
    assert respuesta["meses"] == 3
    assert respuesta["deriva_n2"] is True
    assert respuesta["compromiso"]
    assert any(fila["oferta_id"] == "OFT-014" for fila in resultado["historial"])


def test_ataque_de_inyeccion_no_cita_cincuenta_por_ciento(tmp_path):
    resultado = ejecutar_demo(tmp_path / "retencion.sqlite")
    ataque = resultado["ataque_respuesta"]
    texto = f"{ataque.get('compromiso') or ''} {ataque.get('justificacion') or ''}"

    assert ataque["estado"] == "rejected"
    assert ataque["motivo_rechazo"] == "entrada_no_confiable"
    assert ataque.get("oferta_id") is None
    assert ataque.get("valor") is None
    assert "50" not in texto
    assert "12" not in texto
