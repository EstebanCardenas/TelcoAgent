CREATE TABLE ofertas (
    oferta_id TEXT PRIMARY KEY,
    tipo TEXT NOT NULL CHECK (tipo IN ('descuento_porcentaje', 'meses_sin_cargo')),
    valor INTEGER NOT NULL,
    meses INTEGER NOT NULL,
    segmento_aplicable TEXT NOT NULL CHECK (segmento_aplicable IN ('regular', 'VIP', 'todos')),
    motivo_aplicable TEXT NOT NULL CHECK (motivo_aplicable IN ('tecnica', 'facturacion', 'todos')),
    activa INTEGER NOT NULL CHECK (activa IN (0, 1))
);

CREATE TABLE topes_segmento (
    segmento TEXT NOT NULL CHECK (segmento IN ('regular', 'VIP')),
    tipo_oferta TEXT NOT NULL CHECK (tipo_oferta IN ('descuento_porcentaje', 'meses_sin_cargo')),
    valor_maximo INTEGER NOT NULL,
    meses_maximo INTEGER NOT NULL,
    PRIMARY KEY (segmento, tipo_oferta)
);

CREATE TABLE historial_descuentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contacto_id TEXT NOT NULL,
    oferta_id TEXT NOT NULL,
    fecha_otorgado TEXT NOT NULL,
    vigente_hasta TEXT NOT NULL,
    FOREIGN KEY (oferta_id) REFERENCES ofertas(oferta_id)
);

CREATE INDEX idx_historial_contacto
    ON historial_descuentos (contacto_id, vigente_hasta);
