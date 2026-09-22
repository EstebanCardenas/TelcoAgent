"""Fuentes propias del Agente 2: catálogo, topes e historial.

Sin Ollama y sin la API empresarial. La base es un archivo temporal.
"""

from pathlib import Path

from agente2.db.conexion import conectar, inicializar_bd
from agente2.db.repositorio import (
    historial_vigente,
    listar_candidatas,
    obtener_tope,
    ofertas_elegibles,
    registrar_descuento,
)


def _abrir(tmp_path: Path):
    ruta = tmp_path / "retencion.sqlite"
    inicializar_bd(ruta)
    return conectar(ruta)


def test_inicializar_crea_las_tres_tablas(tmp_path):
    conexion = _abrir(tmp_path)
    try:
        nombres = {
            fila[0]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        conexion.close()
    assert {"ofertas", "topes_segmento", "historial_descuentos"} <= nombres


def test_tope_regular_descuento_es_20_y_3(tmp_path):
    conexion = _abrir(tmp_path)
    try:
        tope = obtener_tope(conexion, "regular", "descuento_porcentaje")
    finally:
        conexion.close()
    assert tope == {"valor_maximo": 20, "meses_maximo": 3}


def test_tope_vip_descuento_es_35_y_6(tmp_path):
    conexion = _abrir(tmp_path)
    try:
        tope = obtener_tope(conexion, "VIP", "descuento_porcentaje")
    finally:
        conexion.close()
    assert tope == {"valor_maximo": 35, "meses_maximo": 6}


def test_situacion_b_incluye_oft_014_y_excluye_fuera_de_politica(tmp_path):
    conexion = _abrir(tmp_path)
    try:
        tope = obtener_tope(conexion, "regular", "descuento_porcentaje")
        candidatas = listar_candidatas(
            conexion, "regular", "tecnica", tope["valor_maximo"], tope["meses_maximo"]
        )
        ids = [fila["oferta_id"] for fila in candidatas]
    finally:
        conexion.close()
    assert "OFT-014" in ids
    assert "OFT-090" not in ids
    assert "OFT-021" not in ids
    assert ids[0] == "OFT-014"


def test_historial_vigente_saca_oft_014_de_cto_001(tmp_path):
    conexion = _abrir(tmp_path)
    try:
        elegibles = ofertas_elegibles(conexion, "CTO-001", "regular", "tecnica")
        ids = [fila["oferta_id"] for fila in elegibles]
        vigentes = {fila["oferta_id"] for fila in historial_vigente(conexion, "CTO-001")}
    finally:
        conexion.close()
    assert "OFT-014" in vigentes
    assert "OFT-014" not in ids


def test_registrar_descuento_impide_repetir(tmp_path):
    conexion = _abrir(tmp_path)
    try:
        antes = ofertas_elegibles(conexion, "CTO-008", "regular", "tecnica")
        assert any(fila["oferta_id"] == "OFT-014" for fila in antes)
        registrar_descuento(conexion, "CTO-008", "OFT-014", 3)
        despues = ofertas_elegibles(conexion, "CTO-008", "regular", "tecnica")
        vigentes = {fila["oferta_id"] for fila in historial_vigente(conexion, "CTO-008")}
    finally:
        conexion.close()
    assert "OFT-014" in vigentes
    assert all(fila["oferta_id"] != "OFT-014" for fila in despues)


def test_sql_usa_parametros_enlazados():
    texto = (
        Path(__file__).resolve().parent.parent / "agente2" / "db" / "repositorio.py"
    ).read_text(encoding="utf-8")
    assert "execute(f\"" not in texto
    assert "execute(f'" not in texto
    assert ".format(" not in texto
