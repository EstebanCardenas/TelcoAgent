INSERT INTO topes_segmento (segmento, tipo_oferta, valor_maximo, meses_maximo) VALUES
    ('regular', 'descuento_porcentaje', 20, 3),
    ('regular', 'meses_sin_cargo', 1, 1),
    ('VIP', 'descuento_porcentaje', 35, 6),
    ('VIP', 'meses_sin_cargo', 2, 2);

INSERT INTO ofertas (
    oferta_id, tipo, valor, meses, segmento_aplicable, motivo_aplicable, activa
) VALUES
    ('OFT-010', 'descuento_porcentaje', 10, 1, 'todos', 'todos', 1),
    ('OFT-011', 'descuento_porcentaje', 15, 2, 'regular', 'facturacion', 1),
    ('OFT-012', 'meses_sin_cargo', 1, 1, 'regular', 'facturacion', 1),
    ('OFT-013', 'descuento_porcentaje', 10, 2, 'regular', 'tecnica', 1),
    ('OFT-014', 'descuento_porcentaje', 20, 3, 'regular', 'tecnica', 1),
    ('OFT-020', 'descuento_porcentaje', 25, 3, 'VIP', 'tecnica', 1),
    ('OFT-021', 'descuento_porcentaje', 35, 6, 'VIP', 'tecnica', 1),
    ('OFT-022', 'descuento_porcentaje', 30, 4, 'VIP', 'facturacion', 1),
    ('OFT-023', 'meses_sin_cargo', 2, 2, 'VIP', 'todos', 1),
    ('OFT-090', 'descuento_porcentaje', 50, 12, 'todos', 'todos', 0);

INSERT INTO historial_descuentos (contacto_id, oferta_id, fecha_otorgado, vigente_hasta) VALUES
    ('CTO-001', 'OFT-014', DATE('now'), DATE('now', '+6 months')),
    ('CTO-004', 'OFT-011', DATE('now'), DATE('now', '+2 months'));
