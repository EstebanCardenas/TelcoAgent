from langchain.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated


class AgentState(TypedDict, total=False):
    """Estado compartido del agente de Telco Andina.

    LangGraph pasa este dict a cada nodo y mezcla el valor de retorno de vuelta
    en él. Los campos están agrupados por el nodo que los escribe.

    `messages` crece con cada turno mediante el reductor `add_messages`: cada nodo
    devuelve solo los mensajes que produce y LangGraph los agrega al historial. A
    diferencia de `operator.add`, este reductor identifica los mensajes por id, así
    que reenviar la conversación completa en el turno siguiente no duplica nada.

    Que los campos de recepción, análisis y decisión vivan aquí es lo que hace
    coherente el expediente: el nodo `acciones` registra la telemetría y el ticket
    leyendo estos valores, así que la auditoría siempre coincide con la respuesta
    que recibe el cliente.

    `total=False`: todos los campos son opcionales al invocar. El grafo arranca
    con solo `messages` y cada nodo va llenando lo suyo.
    """

    messages: Annotated[list[AnyMessage], add_messages]

    # Compresión de contexto
    resumen_contexto: str

    # Memoria de largo plazo (Store)
    identidad_memoria: str
    perfil_cliente: str

    # Recepción (punto de integración)
    contacto_id: str
    cliente_id: str | None
    cliente_identificado: bool
    texto_contacto: str

    # Análisis del mensaje
    tono: str
    urgencia: str
    riesgo_churn: bool
    categoria: str
    categoria_secundaria: str | None
    requiere_datos_privados: bool

    # Decisión de tratamiento
    decision: str
    area_destino: str | None
    prioridad: str
    justificacion: str

    # Resultado de las acciones sobre el negocio
    telemetria_id: str | None
    ticket_id: str | None
    ticket_n2_id: str | None

    # A2A con el Asesor de Retención
    segmento: str
    tarea_id: str
    compromiso_retencion: str
    oferta_retencion: str | None
    deriva_n2: bool
    estado_tarea_a2a: str

    # ReAct (semana 5): último Thought y red de seguridad del ciclo reason ⇄ act
    razonamiento: str
    iteracion: int
    max_iteraciones: int
