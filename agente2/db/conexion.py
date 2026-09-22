"""Apertura e inicialización de la SQLite de retención."""

from pathlib import Path
import sqlite3

_DIR = Path(__file__).resolve().parent


def conectar(ruta: str | Path) -> sqlite3.Connection:
    """Abre la base con filas como dict y claves foráneas activas."""
    conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def inicializar_bd(ruta: str | Path) -> None:
    """Crea esquema y semilla solo si la tabla `ofertas` aún no existe."""
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    ya_existia = destino.exists()
    conexion = conectar(destino)
    try:
        if ya_existia:
            tablas = conexion.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ofertas'"
            ).fetchone()
            if tablas:
                return
        esquema = (_DIR / "esquema.sql").read_text(encoding="utf-8")
        semilla = (_DIR / "semilla.sql").read_text(encoding="utf-8")
        conexion.executescript(esquema)
        conexion.executescript(semilla)
        conexion.commit()
    finally:
        conexion.close()
