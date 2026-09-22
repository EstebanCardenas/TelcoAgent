"""Demo A2A de Situación B para pegar en la wiki de la semana 8.

No llama a Ollama. El modelo y el ticket se simulan. El HTTP, el plan y la
SQLite son los del Agente 2. Imprime petición, estados y respuesta.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agente2.a2a import tareas
from agente2.config import get_settings
from agente2.db.conexion import conectar
from agente2.db.repositorio import historial_vigente
from agente2.razonamiento.plan_execute import correr_plan as correr_plan_real
from tests.test_agente2_contrato import SITUACION_B
from tests.test_agente2_plan import COMPROMISO_B, JUSTIFICACION_B, ModeloFijo
from tests.test_agente2_seguridad import ATAQUE_SEMANA_7


def _ticket_ok(ticket_id: str) -> dict:
    return {"id": ticket_id, "estado": "abierto", "area_destino": "retencion"}


def _imprimir(titulo: str, cuerpo) -> None:
    print(titulo)
    print(json.dumps(cuerpo, indent=2, ensure_ascii=False))
    print()


def _esperar_terminal(cliente: TestClient, tarea_id: str, tope_s: float = 4.0) -> tuple[list[str], dict]:
    vistos: list[str] = []
    ultima: dict = {}
    limite = time.monotonic() + tope_s
    while time.monotonic() < limite:
        respuesta = cliente.get(f"/tareas/{tarea_id}")
        ultima = respuesta.json()
        estado = ultima.get("estado")
        if estado and (not vistos or vistos[-1] != estado):
            vistos.append(estado)
        if estado in {"completed", "rejected", "failed"}:
            return vistos, ultima
        time.sleep(0.04)
    return vistos, ultima


def _restaurar_entorno(previos: dict[str, str | None]) -> None:
    for clave, valor in previos.items():
        if valor is None:
            os.environ.pop(clave, None)
        else:
            os.environ[clave] = valor
    get_settings.cache_clear()
    tareas.reiniciar()


def ejecutar_demo(db_path: Path) -> dict:
    claves = ("AGENTE2_DB_PATH", "AGENTE2_EJECUTAR_PLAN", "AGENTE2_CLASIFICADOR")
    previos = {clave: os.environ.get(clave) for clave in claves}
    os.environ["AGENTE2_DB_PATH"] = str(db_path)
    os.environ["AGENTE2_EJECUTAR_PLAN"] = "1"
    os.environ["AGENTE2_CLASIFICADOR"] = "0"
    get_settings.cache_clear()
    tareas.reiniciar()

    def _plan_simulado(peticion, **_kwargs):
        time.sleep(0.12)
        return correr_plan_real(
            peticion,
            modelo=ModeloFijo("OFT-014", COMPROMISO_B, JUSTIFICACION_B),
            consultar_ticket=_ticket_ok,
            clasificador=lambda _texto: False,
            db_path=str(db_path),
        )

    from agente2.app import app

    try:
        with patch("agente2.razonamiento.plan_execute.correr_plan", _plan_simulado):
            with TestClient(app) as cliente:
                post_b = cliente.post("/tareas", json=SITUACION_B)
                submitted = post_b.json()
                estados_b, respuesta_b = _esperar_terminal(
                    cliente, SITUACION_B["tarea_id"]
                )
                if submitted.get("estado") and (
                    not estados_b or estados_b[0] != submitted["estado"]
                ):
                    estados_b = [submitted["estado"], *estados_b]

                ataque = dict(SITUACION_B)
                ataque["tarea_id"] = "TAR-021"
                ataque["motivo"] = ATAQUE_SEMANA_7.strip()
                ataque["resumen"] = "Falla de internet con amenaza de cancelacion."
                post_ataque = cliente.post("/tareas", json=ataque)
                respuesta_ataque = post_ataque.json()

        conexion = conectar(str(db_path))
        try:
            historial = historial_vigente(conexion, SITUACION_B["contacto_id"])
        finally:
            conexion.close()
    finally:
        _restaurar_entorno(previos)

    return {
        "peticion": SITUACION_B,
        "submitted": submitted,
        "estados": estados_b,
        "respuesta": respuesta_b,
        "historial": historial,
        "ataque_peticion": ataque,
        "ataque_respuesta": respuesta_ataque,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        resultado = ejecutar_demo(Path(tmp) / "retencion.sqlite")

    print("Situación B: Asesor de Retención (A2A)")
    print(f"estados: {' -> '.join(resultado['estados'])}")
    print()
    _imprimir("Petición: Agente 1 hacia Agente 2", resultado["peticion"])
    _imprimir("POST /tareas (submitted)", resultado["submitted"])
    _imprimir("GET /tareas/TAR-020 (respuesta)", resultado["respuesta"])
    _imprimir("historial_descuentos de CTO-008", resultado["historial"])
    _imprimir("Ataque de inyección: petición", resultado["ataque_peticion"])
    _imprimir("Ataque de inyección: respuesta", resultado["ataque_respuesta"])


if __name__ == "__main__":
    main()
