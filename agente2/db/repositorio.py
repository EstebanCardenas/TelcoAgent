"""Consultas deterministas sobre catálogo, topes e historial.

El modelo no escribe SQL. Los valores llegan como parámetros enlazados.
"""

import sqlite3

TIPOS_OFERTA = ("descuento_porcentaje", "meses_sin_cargo")


def _dict(fila: sqlite3.Row | None) -> dict | None:
    return dict(fila) if fila is not None else None


def obtener_tope(
    conexion: sqlite3.Connection, segmento: str, tipo_oferta: str
) -> dict | None:
    fila = conexion.execute(
        """
        SELECT valor_maximo, meses_maximo
        FROM topes_segmento
        WHERE segmento = ? AND tipo_oferta = ?
        """,
        (segmento, tipo_oferta),
    ).fetchone()
    return _dict(fila)


def listar_topes(conexion: sqlite3.Connection, segmento: str) -> list[dict]:
    filas = conexion.execute(
        """
        SELECT segmento, tipo_oferta, valor_maximo, meses_maximo
        FROM topes_segmento
        WHERE segmento = ?
        ORDER BY tipo_oferta
        """,
        (segmento,),
    ).fetchall()
    return [dict(fila) for fila in filas]


def listar_catalogo(
    conexion: sqlite3.Connection, segmento: str, motivo: str
) -> list[dict]:
    """Ofertas activas del segmento y motivo, sin aplicar tope todavía."""
    filas = conexion.execute(
        """
        SELECT oferta_id, tipo, valor, meses, segmento_aplicable, motivo_aplicable
        FROM ofertas
        WHERE activa = 1
          AND segmento_aplicable IN (?, 'todos')
          AND motivo_aplicable IN (?, 'todos')
        ORDER BY valor DESC, meses DESC
        """,
        (segmento, motivo),
    ).fetchall()
    return [dict(fila) for fila in filas]


def listar_candidatas(
    conexion: sqlite3.Connection,
    segmento: str,
    motivo: str,
    valor_maximo: int,
    meses_maximo: int,
) -> list[dict]:
    filas = conexion.execute(
        """
        SELECT oferta_id, tipo, valor, meses, segmento_aplicable, motivo_aplicable
        FROM ofertas
        WHERE activa = 1
          AND segmento_aplicable IN (?, 'todos')
          AND motivo_aplicable IN (?, 'todos')
          AND valor <= ?
          AND meses <= ?
        ORDER BY valor DESC, meses DESC
        """,
        (segmento, motivo, valor_maximo, meses_maximo),
    ).fetchall()
    return [dict(fila) for fila in filas]


def historial_vigente(conexion: sqlite3.Connection, contacto_id: str) -> list[dict]:
    filas = conexion.execute(
        """
        SELECT oferta_id, vigente_hasta
        FROM historial_descuentos
        WHERE contacto_id = ? AND vigente_hasta >= DATE('now')
        """,
        (contacto_id,),
    ).fetchall()
    return [dict(fila) for fila in filas]


def obtener_oferta(conexion: sqlite3.Connection, oferta_id: str) -> dict | None:
    fila = conexion.execute(
        """
        SELECT oferta_id, tipo, valor, meses, segmento_aplicable, motivo_aplicable, activa
        FROM ofertas
        WHERE oferta_id = ? AND activa = 1
        """,
        (oferta_id,),
    ).fetchone()
    return _dict(fila)


def registrar_descuento(
    conexion: sqlite3.Connection, contacto_id: str, oferta_id: str, meses: int
) -> None:
    vigencia = f"+{int(meses)} months"
    conexion.execute(
        """
        INSERT INTO historial_descuentos
            (contacto_id, oferta_id, fecha_otorgado, vigente_hasta)
        VALUES (?, ?, DATE('now'), DATE('now', ?))
        """,
        (contacto_id, oferta_id, vigencia),
    )
    conexion.commit()


def ofertas_elegibles(
    conexion: sqlite3.Connection, contacto_id: str, segmento: str, motivo: str
) -> list[dict]:
    """Cruza catálogo, tope por tipo e historial vigente."""
    otorgadas = {fila["oferta_id"] for fila in historial_vigente(conexion, contacto_id)}
    vistas: dict[str, dict] = {}
    for tipo in TIPOS_OFERTA:
        tope = obtener_tope(conexion, segmento, tipo)
        if tope is None:
            continue
        for oferta in listar_candidatas(
            conexion,
            segmento,
            motivo,
            tope["valor_maximo"],
            tope["meses_maximo"],
        ):
            if oferta["tipo"] != tipo:
                continue
            if oferta["oferta_id"] in otorgadas:
                continue
            vistas[oferta["oferta_id"]] = oferta
    return sorted(
        vistas.values(),
        key=lambda oferta: (oferta["valor"], oferta["meses"]),
        reverse=True,
    )
