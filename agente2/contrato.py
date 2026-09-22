"""Esquemas de la tarea A2A entre el Agente 1 y el Asesor de Retención."""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, ValidationError

_TAR = re.compile(r"^TAR-\d+$")
_TKT = re.compile(r"^TKT-\d+$")
_CTO = re.compile(r"^CTO-\d+$")

Segmento = Literal["regular", "VIP"]
Categoria = Literal["tecnica", "facturacion", "retencion", "consulta", "otro"]
Prioridad = Literal["baja", "media", "alta", "critica"]
Tono = Literal["frustrado", "urgente", "agresivo", "neutro", "cordial"]
Urgencia = Literal["alta", "media", "baja"]
AreaDestino = Literal[
    "soporte_tecnico_n1",
    "soporte_tecnico_n2",
    "facturacion",
    "retencion",
    "supervision",
]
EstadoTarea = Literal["submitted", "working", "completed", "rejected", "failed"]
TipoOferta = Literal["descuento_porcentaje", "meses_sin_cargo"]
MotivoRechazo = Literal[
    "esquema_invalido",
    "fuera_de_retencion",
    "ticket_desconocido",
    "entrada_no_confiable",
    "segmento_no_coincide",
]


class PeticionRetencion(BaseModel):
    tarea_id: str
    ticket_id: str
    contacto_id: str
    area_destino: AreaDestino
    segmento: Segmento
    categoria: Categoria
    motivo: str
    resumen: str = Field(max_length=500)
    prioridad: Prioridad
    riesgo_churn: bool
    tono: Tono
    urgencia: Urgencia

    @field_validator("tarea_id")
    @classmethod
    def formato_tarea(cls, valor: str) -> str:
        if not _TAR.fullmatch(valor):
            raise ValueError("tarea_id debe tener formato TAR-digitos")
        return valor

    @field_validator("ticket_id")
    @classmethod
    def formato_ticket(cls, valor: str) -> str:
        if not _TKT.fullmatch(valor):
            raise ValueError("ticket_id debe tener formato TKT-digitos")
        return valor

    @field_validator("contacto_id")
    @classmethod
    def formato_contacto(cls, valor: str) -> str:
        if not _CTO.fullmatch(valor):
            raise ValueError("contacto_id debe tener formato CTO-digitos")
        return valor


class RespuestaTarea(BaseModel):
    tarea_id: Optional[str] = None
    estado: EstadoTarea
    oferta_id: Optional[str] = None
    tipo: Optional[TipoOferta] = None
    valor: Optional[int] = None
    meses: Optional[int] = None
    deriva_n2: bool = False
    compromiso: str = ""
    justificacion: str = ""
    motivo_rechazo: Optional[MotivoRechazo] = None


def parsear_peticion(cuerpo: dict) -> tuple[PeticionRetencion | None, RespuestaTarea | None]:
    """Valida el expediente. Si falla, devuelve un rechazo de esquema."""
    try:
        peticion = PeticionRetencion.model_validate(cuerpo)
    except ValidationError:
        tarea_id = cuerpo.get("tarea_id") if isinstance(cuerpo, dict) else None
        if not isinstance(tarea_id, str) or not _TAR.fullmatch(tarea_id):
            tarea_id = None
        return None, RespuestaTarea(
            tarea_id=tarea_id,
            estado="rejected",
            motivo_rechazo="esquema_invalido",
        )
    return peticion, None


def rechazo_fuera_de_retencion(peticion: PeticionRetencion) -> RespuestaTarea:
    return RespuestaTarea(
        tarea_id=peticion.tarea_id,
        estado="rejected",
        motivo_rechazo="fuera_de_retencion",
    )
