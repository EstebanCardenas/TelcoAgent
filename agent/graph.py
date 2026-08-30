"""[SEMANA 2] Grafo del agente (laboratorios 4 y 5).

El grafo sigue el diagrama de la semana 1 y respeta sus tres tipos de caja:

  Pasos deterministas (cajas técnicas del diagrama)
      `recepcion`  obtiene el contacto real del punto de integración.
      `tool_node`  ejecuta las consultas que el modelo pidió.
      `acciones`   registra la telemetría y crea el ticket.

  Pasos de razonamiento (cajas moradas del diagrama)
      `analisis`   lee tono, urgencia, riesgo de cancelación y categoría.
      `consulta`   decide qué herramientas de consulta hacen falta.
      `decision`   resuelve o escala, con área, prioridad y justificación.
      `respuesta`  redacta la respuesta al cliente y el expediente.

Forma del grafo:

    START -> recepcion -> [compresion_contexto] -> analisis -> consulta -> tool_node -> consulta -> ...
                                                                    |
                                                                    v
                                                  decision -> acciones -> respuesta -> END

El código garantiza lo que el caso exige por auditoría: `acciones` corre siempre
entre la decisión y la respuesta, y registra los valores que están en el estado.
Al modelo le quedan las decisiones de criterio, que es lo que el diagrama marca
como agéntico.

Memoria (semana 4). Dos capas ortogonales al flujo:

  Corto plazo   el `checkpointer` guarda el estado por `thread_id`, y
                `compresion_contexto` lo poda cuando la conversación se alarga.
  Largo plazo   el `store` guarda el perfil del cliente entre sesiones distintas.
                `recepcion` lo lee y `respuesta` lo actualiza; LangGraph se lo
                inyecta a los nodos que declaran `store: BaseStore`.
"""

import json
import re

from langchain_ollama.chat_models import ChatOllama
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from agent.memory.store import (
    actualizar_perfil,
    cargar_perfil,
    identidad_cliente,
    perfil_a_texto,
)
from agent.tools import cliente_existe, get_local_tools, obtener_contacto
from agent.state import AgentState
from cli.config import get_settings


# Herramientas que ESCRIBEN en el negocio. Viven en el servidor MCP y las invocan
# los nodos deterministas por su nombre, sin pasar por el modelo.
TOOLS_DE_ACCION = {"registrar_contacto", "crear_ticket_escalamiento", "registrar_telemetria"}

# Red de seguridad del ciclo de consulta: máximo de pasadas por el nodo
# `consulta` antes de seguir a la decisión con lo que ya se recolectó.
MAX_ITERACIONES = 4

TONOS = ("frustrado", "urgente", "agresivo", "neutro", "cordial")
URGENCIAS = ("alta", "media", "baja")
CATEGORIAS = ("tecnica", "facturacion", "retencion", "consulta", "otro")
AREAS = ("soporte_tecnico_n1", "soporte_tecnico_n2", "facturacion", "retencion", "supervision")
PRIORIDADES = ("baja", "media", "alta", "critica")

PROMPT_ANALISIS = """Analiza el mensaje del cliente de Telco Andina y clasifícalo.

Responde SOLO con un JSON, sin texto alrededor, con estas claves:
  "tono": frustrado | urgente | agresivo | neutro | cordial
  "urgencia": alta | media | baja
  "riesgo_churn": true si amenaza con cancelar o irse a la competencia, si no false
  "categoria": tecnica (fallas del servicio) | facturacion (cobros) | retencion (quiere irse) |
               consulta (pregunta por información: planes, tarifas, tiendas, horarios) | otro
  "categoria_secundaria": otra de la misma lista si el mensaje mezcla temas, si no null
  "senales": lista corta de frases textuales del mensaje que sustentan el tono
  "requiere_datos_privados": true si hay que mirar la cuenta del cliente, false si es información pública

Mensaje del cliente:
{mensaje}

{resumen}"""

PROMPT_CONSULTA = """Eres el agente de atención al cliente de Telco Andina. Ya clasificaste el caso:

{resumen}

Decide qué necesitas consultar antes de resolver. Usa las herramientas disponibles:
- Información pública (planes, tarifas, tiendas, horarios, políticas): consultar_base_conocimiento_publica.
- Casos parecidos ya resueltos: consultar_casos_resueltos con la categoría del caso.
- Reglas de la empresa antes de escalar: consultar_politicas_institucionales con tipo 'vip',
  'falla-masiva' o 'palabras-clave'.
{obligatorio}
No repitas una consulta que ya hiciste. Cuando tengas lo necesario, responde en texto plano con un
resumen de una línea de lo que encontraste."""

# Cuando el mensaje trae amenaza de cancelación, la política institucional deja de
# ser opcional: define el área destino y el nivel mínimo de escalamiento.
CONSULTA_OBLIGATORIA_CHURN = (
    "\nEste caso tiene amenaza de cancelación. Antes de decidir, llama\n"
    "consultar_politicas_institucionales con tipo 'vip': esa política fija el nivel mínimo de\n"
    "escalamiento y la asignación a retención.\n"
)

PROMPT_DECISION = """Eres el agente de atención al cliente de Telco Andina. Decide el tratamiento del caso.

{resumen}

Lo consultado hasta ahora:
{hallazgos}
{advertencias}
Responde SOLO con un JSON, sin texto alrededor, con estas claves:
  "decision": resolver | escalar
  "area_destino": soporte_tecnico_n1 | soporte_tecnico_n2 | facturacion | retencion | supervision, o null si resuelves
  "prioridad": baja | media | alta | critica
  "justificacion": una o dos frases explicando por qué, citando lo que sustenta la decisión"""

PROMPT_RESPUESTA = """Eres el agente de atención al cliente de Telco Andina. El caso ya está decidido
y registrado. Redacta la salida final.

{resumen}

Decisión tomada: {decision}
Área destino: {area_destino}
Prioridad: {prioridad}
Justificación: {justificacion}
Constancia de auditoría: {constancia}

Lo consultado:
{hallazgos}
{advertencias}
Escribe primero la respuesta para el cliente, en el tono adecuado a su estado emocional, con un
compromiso concreto y sin prometer nada que la política no autorice. Después el expediente con
estas siete secciones, cada una con su título:

1. Información general de la interacción
2. Análisis de tono y carga emocional, citando las señales del mensaje
3. Clasificación del problema
4. Decisión de resolución o escalamiento, con área, prioridad y motivo
5. Respuesta generada al cliente
6. Acciones recomendadas para el operador humano
7. Recomendaciones y preguntas pendientes

Usa solo información que aparezca arriba. Si un dato no aparece, NO lo inventes: dile al cliente que
lo vas a verificar y anótalo en la sección 7 como pendiente.

El expediente termina en la sección 7. No escribas nada después: ni cierres, ni resúmenes de lo que
acabas de redactar, ni comentarios sobre estas instrucciones."""

PROMPT_COMPRESION = """Eres el sistema de memoria de Telco Andina. Resume el historial de esta conversación para mantener el contexto esencial sin desbordar el límite de tokens.

Historial a resumir:
{historial}

{resumen_anterior}

Escribe un resumen acumulativo y conciso de los hechos clave, problemas reportados, validaciones realizadas y acuerdos hasta este punto. Omite saludos o verificaciones sin importancia. Responde SOLO con el resumen."""


def _texto_del_cliente(messages: list) -> str:
    for mensaje in reversed(messages):
        if isinstance(mensaje, HumanMessage):
            return str(mensaje.content)
    return ""


def _texto_del_resultado(crudo) -> str:
    """Las herramientas locales devuelven texto; las de MCP, bloques de contenido."""
    if isinstance(crudo, str):
        return crudo
    if isinstance(crudo, list):
        partes = []
        for bloque in crudo:
            if isinstance(bloque, dict):
                partes.append(str(bloque.get("text", "")))
            else:
                partes.append(str(getattr(bloque, "text", bloque)))
        return "\n".join(partes)
    return str(crudo)


# Valores de texto sin comillas: `{"tono": consulta}`.
_VALOR_SIN_COMILLAS = re.compile(
    r':(?!\s*(?:true\b|false\b|null\b|["\[{\d-]))\s*([^,}\n\]]+?)\s*(?=[,}\n])'
)
_COMA_SOBRANTE = re.compile(r",\s*([}\]])")

# Dos puntos dentro de las comillas de la clave: `{"tipo: "vip"}`. El JSON
# válido no cumple este patrón, porque ahí van fuera de la cadena.
_DOSPUNTOS_EN_LA_CLAVE = re.compile(r'"([^":{}]+?)\s*:\s*"([^"]*)"')


def _json_de(texto: str) -> dict:
    """Extrae el primer objeto JSON de una respuesta del modelo, reparándolo si hace falta.

    Devuelve un dict vacío cuando no hay nada legible, para que cada campo caiga
    en su valor por defecto.
    """
    if not texto:
        return {}
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin <= inicio:
        return {}
    bruto = texto[inicio : fin + 1]

    reparado = _DOSPUNTOS_EN_LA_CLAVE.sub(r'"\1": "\2"', bruto)
    reparado = _COMA_SOBRANTE.sub(r"\1", _VALOR_SIN_COMILLAS.sub(r': "\1"', reparado))

    for candidato in (bruto, reparado):
        try:
            datos = json.loads(candidato)
        except json.JSONDecodeError:
            continue
        if isinstance(datos, dict):
            return datos
    return {}


def _uno_de(valor, permitidos: tuple, por_defecto: str) -> str:
    """Normaliza un valor del modelo contra una lista cerrada."""
    texto = str(valor or "").strip().lower()
    if texto in permitidos:
        return texto
    # La respuesta puede traer la palabra dentro de una frase.
    return next((p for p in permitidos if p in texto), por_defecto)


# Traza para la persona que mira el CLI. El modelo nunca las ve.
ANOTACIONES = ("[análisis]", "[auditoría]")


def _conversacion(messages: list) -> list:
    """La conversación sin mensajes de sistema ni anotaciones.

    Si el último mensaje es una anotación del asistente, el modelo la lee como
    una frase suya a medio escribir y la continúa en texto plano.
    """
    return [
        m
        for m in messages
        if not isinstance(m, SystemMessage)
        and not str(getattr(m, "content", "")).startswith(ANOTACIONES)
    ]


_TOOL_CALL_EN_TEXTO = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def _rescatar_tool_calls_de_texto(mensaje) -> None:
    """Convierte en llamadas reales las que el modelo escribió como texto.

    Cuando la plantilla de herramientas falla, la llamada llega dentro del
    contenido y el grafo la tomaría como respuesta final.
    """
    if getattr(mensaje, "tool_calls", None) or not isinstance(mensaje.content, str):
        return

    rescatadas = []
    for indice, bloque in enumerate(_TOOL_CALL_EN_TEXTO.findall(mensaje.content)):
        datos = _json_de(bloque)
        nombre = datos.get("name")
        if not nombre:
            continue
        argumentos = datos.get("arguments") or datos.get("args") or {}
        rescatadas.append(
            {
                "name": nombre,
                "args": argumentos if isinstance(argumentos, dict) else {},
                "id": f"rescatada-{indice}",
                "type": "tool_call",
            }
        )

    if rescatadas:
        mensaje.tool_calls = rescatadas
        mensaje.content = _TOOL_CALL_EN_TEXTO.sub("", mensaje.content).strip()


def _reparar_tool_calls(mensaje) -> None:
    """Limpia las claves de los argumentos antes de ejecutar la herramienta.

    Una clave con los dos puntos pegados (`{"tipo: ": "vip"}`) mata la llamada en
    la validación aunque la herramienta y el valor sean correctos. Hacerlo en el
    esquema de Pydantic no sirve: LangChain descarta los campos que no venían en
    la llamada original.
    """
    for llamada in getattr(mensaje, "tool_calls", None) or []:
        argumentos = llamada.get("args") or {}
        limpios = {str(clave).strip().rstrip(":").strip(): valor for clave, valor in argumentos.items()}
        if limpios != argumentos:
            llamada["args"] = limpios


def _resumen_del_caso(state: AgentState) -> str:
    if state.get("cliente_id"):
        cliente = state["cliente_id"]
    elif state.get("cliente_identificado"):
        cliente = "identificado por cédula, perfil sin consultar"
    else:
        cliente = "no identificado"

    base = (
        f"- Contacto: {state.get('contacto_id') or 'sin registrar'}"
        f" · Cliente: {cliente}\n"
        f"- Mensaje: {state.get('texto_contacto', '')}\n"
        f"- Tono: {state.get('tono')} · Urgencia: {state.get('urgencia')}"
        f" · Riesgo de cancelación: {'sí' if state.get('riesgo_churn') else 'no'}\n"
        f"- Categoría: {state.get('categoria')}"
        f" · Secundaria: {state.get('categoria_secundaria') or 'ninguna'}"
    )
    
    if state.get("resumen_contexto"):
        base += f"\n- Resumen Historial Prevío: {state['resumen_contexto']}"

    if state.get("perfil_cliente"):
        base += f"\n- Perfil histórico del cliente (memoria de largo plazo): {state['perfil_cliente']}"

    return base


def _consultas(messages: list) -> tuple[str, str]:
    """Separa lo consultado con éxito de lo que falló.

    Mezclarlos lleva a tratar un error como si fuera un dato, y a responderle al
    cliente información que nadie entregó.
    """
    from langchain.messages import ToolMessage

    exitos, fallas = [], []
    for mensaje in messages:
        if not isinstance(mensaje, ToolMessage):
            continue
        contenido = str(mensaje.content)
        datos = _json_de(contenido)
        if datos.get("estado") == "error" or contenido.startswith("Error"):
            fallas.append(f"- {mensaje.name}: {datos.get('mensaje') or contenido[:200]}")
        else:
            exitos.append(f"- {mensaje.name}: {contenido[:600]}")

    texto_exitos = "\n".join(exitos) if exitos else "- Sin consultas exitosas en este turno."
    if not fallas:
        return texto_exitos, ""
    texto_fallas = (
        "\nATENCIÓN, estas consultas fallaron y su información NO está disponible:\n"
        + "\n".join(fallas)
        + "\nProhibido inventar esos datos. Dile al cliente que los vas a verificar y anótalos en la "
        "sección 7 como pendientes de verificación.\n"
    )
    return texto_exitos, texto_fallas


def build_graph(tools: list | None = None, checkpointer=None, store=None):
    """Compila y devuelve el grafo del agente, listo para invocar.

    Parámetros:
        tools:        herramientas disponibles (locales de consulta + MCP de acción).
                      Se reparten aquí: el modelo solo ve las de consulta.
        checkpointer: memoria de corto plazo (se usa desde la semana 4).
        store:        memoria de largo plazo. Sin él el agente funciona igual,
                      pero sin reconocer clientes de otras sesiones.
    """
    if tools is None:
        tools = get_local_tools()

    tools_consulta = [t for t in tools if t.name not in TOOLS_DE_ACCION]
    tools_accion = {t.name: t for t in tools if t.name in TOOLS_DE_ACCION}

    settings = get_settings()

    # temperature=0: el caso exige que la misma interacción produzca la misma
    # decisión sin importar cuándo se procese, y la selección de herramientas
    # necesita ser determinista. La ventana de contexto se lee de la
    # configuración porque depende del modelo que cada equipo sirva en Ollama,
    # cuyo valor por defecto son 2048 tokens.
    modelo_base = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        num_ctx=settings.ollama_num_ctx,
    )
    modelo_con_tools = modelo_base.bind_tools(tools_consulta)

    def _con_perfil(salida: dict, store, identidad_previa: str | None) -> dict:
        """Añade a la salida de `recepcion` lo que el Store sabe del cliente.

        Corre después de resolver el contacto porque de ahí sale la identidad.
        `salida` todavía no está fusionada con el estado, así que la identidad de
        turnos anteriores llega por parámetro.
        """
        if store is None:
            return salida

        identidad = identidad_cliente({**salida, "identidad_memoria": identidad_previa})
        if not identidad:
            return salida

        salida["identidad_memoria"] = identidad

        perfil = cargar_perfil(store, identidad)
        if not perfil:
            return salida

        salida["perfil_datos"] = perfil
        salida["perfil_cliente"] = perfil_a_texto(perfil)
        return salida

    async def recepcion(state: AgentState, store: BaseStore):
        """Consigue el contacto real del punto de integración y carga su perfil."""
        texto = _texto_del_cliente(state["messages"])
        identidad_previa = state.get("identidad_memoria")

        citado = re.search(r"\bCTO-\d+\b", texto, re.IGNORECASE)
        if citado:
            crudo = await obtener_contacto.ainvoke({"contacto_id": citado.group(0).upper()})
            datos = _json_de(_texto_del_resultado(crudo))
            if datos.get("estado") == "ok":
                contacto = datos["contacto"]
                return _con_perfil(
                    {
                        "contacto_id": contacto["id"],
                        "cliente_id": contacto.get("cliente_id"),
                        "texto_contacto": contacto.get("texto") or texto,
                    },
                    store,
                    identidad_previa,
                )

        # La API confirma que la persona existe sin revelar dato alguno suyo.
        # Consultar su perfil exige autenticación.
        cedula = re.search(r"\b\d{6,12}\b", texto)
        identificado = bool(cedula and cliente_existe(cedula.group(0)))

        # Sin contacto citado se registra el entrante, porque la auditoría
        # necesita un identificador real.
        registrar = tools_accion.get("registrar_contacto")
        if registrar is not None:
            crudo = await registrar.ainvoke({"texto": texto, "canal": "chat"})
            datos = _json_de(_texto_del_resultado(crudo))
            if datos.get("id"):
                return _con_perfil(
                    {
                        "contacto_id": datos["id"],
                        "cliente_id": datos.get("cliente_id"),
                        "texto_contacto": texto,
                        "cliente_identificado": identificado,
                    },
                    store,
                    identidad_previa,
                )

        # El punto de integración no respondió: se atiende igual, sin constancia.
        return _con_perfil(
            {
                "contacto_id": "",
                "cliente_id": None,
                "texto_contacto": texto,
                "cliente_identificado": identificado,
            },
            store,
            identidad_previa,
        )

    def compresion_contexto(state: AgentState):
        """Resume mensajes antiguos para proteger la ventana de contexto."""
        from langchain_core.messages import RemoveMessage

        mensajes = _conversacion(state["messages"])
        
        # Encontrar el índice del último HumanMessage
        ultimo_human_idx = len(mensajes) - 1
        while ultimo_human_idx >= 0 and not isinstance(mensajes[ultimo_human_idx], HumanMessage):
            ultimo_human_idx -= 1
            
        if ultimo_human_idx <= 0:
            return {}
            
        mensajes_a_comprimir = mensajes[:ultimo_human_idx]
        historial_texto = "\n".join([f"{m.type}: {m.content}" for m in mensajes_a_comprimir])
        
        resumen_anterior = state.get("resumen_contexto")
        texto_anterior = f"Resumen acumulado previo:\n{resumen_anterior}" if resumen_anterior else ""
        
        prompt = PROMPT_COMPRESION.format(historial=historial_texto, resumen_anterior=texto_anterior)
        nuevo_resumen = modelo_base.invoke([HumanMessage(content=prompt)]).content
        
        # Generar comandos RemoveMessage usando los IDs reales de los mensajes (incluyendo los ignorados por _conversacion)
        # Queremos eliminar todos los mensajes ANTERIORES al último HumanMessage en state["messages"]
        todos_los_mensajes = state["messages"]
        idx_human_original = len(todos_los_mensajes) - 1
        while idx_human_original >= 0 and not isinstance(todos_los_mensajes[idx_human_original], HumanMessage):
            idx_human_original -= 1
            
        remover = [RemoveMessage(id=m.id) for m in todos_los_mensajes[:idx_human_original] if m.id]
        
        return {
            "resumen_contexto": str(nuevo_resumen).strip(),
            "messages": remover
        }

    def debe_comprimir(state: AgentState):
        """Si hay más de 6 mensajes en la conversación activa, comprime."""
        mensajes = _conversacion(state["messages"])
        if len(mensajes) > 6:
            return "compresion_contexto"
        return "analisis"

    def analisis(state: AgentState):
        """Clasifica el mensaje y escribe el resultado en el estado.

        Cada campo tiene un valor por defecto para que una respuesta inesperada
        no rompa el ruteo.
        """
        contexto = []
        if state.get("resumen_contexto"):
            contexto.append(f"Contexto previo:\n{state['resumen_contexto']}")
        if state.get("perfil_cliente"):
            contexto.append(f"Historial del cliente en sesiones anteriores:\n{state['perfil_cliente']}")
        resumen = "\n\n".join(contexto)
        prompt = PROMPT_ANALISIS.format(mensaje=state.get("texto_contacto", ""), resumen=resumen)
        datos = _json_de(modelo_base.invoke([HumanMessage(content=prompt)]).content)

        secundaria = datos.get("categoria_secundaria")
        secundaria = _uno_de(secundaria, CATEGORIAS, "") if secundaria else None

        senales = datos.get("senales")
        senales = senales if isinstance(senales, list) else []

        return {
            "tono": _uno_de(datos.get("tono"), TONOS, "neutro"),
            "urgencia": _uno_de(datos.get("urgencia"), URGENCIAS, "media"),
            "riesgo_churn": bool(datos.get("riesgo_churn")),
            "categoria": _uno_de(datos.get("categoria"), CATEGORIAS, "otro"),
            "categoria_secundaria": secundaria or None,
            "requiere_datos_privados": bool(datos.get("requiere_datos_privados")),
            "messages": [
                AIMessage(
                    content=(
                        f"[análisis] tono={_uno_de(datos.get('tono'), TONOS, 'neutro')}"
                        f" · urgencia={_uno_de(datos.get('urgencia'), URGENCIAS, 'media')}"
                        f" · riesgo de cancelación={'sí' if datos.get('riesgo_churn') else 'no'}"
                        f" · categoría={_uno_de(datos.get('categoria'), CATEGORIAS, 'otro')}"
                        + (f" · señales: {'; '.join(str(s) for s in senales[:3])}" if senales else "")
                    )
                )
            ],
        }

    def consulta(state: AgentState):
        """El modelo decide qué consultar. Aquí solo ve las herramientas de lectura."""
        iteracion = state.get("iteracion", 0) + 1
        max_iteraciones = state.get("max_iteraciones") or MAX_ITERACIONES

        instrucciones = PROMPT_CONSULTA.format(
            resumen=_resumen_del_caso(state),
            obligatorio=CONSULTA_OBLIGATORIA_CHURN if state.get("riesgo_churn") else "",
        )
        mensajes = [SystemMessage(content=instrucciones), *_conversacion(state["messages"])]

        if iteracion >= max_iteraciones:
            # Sin herramientas vinculadas la única salida es seguir a la decisión.
            respuesta = modelo_base.invoke(
                mensajes
                + [SystemMessage(content="Ya no puedes consultar más. Resume en una línea lo que tienes.")]
            )
        else:
            respuesta = modelo_con_tools.invoke(mensajes)
            _rescatar_tool_calls_de_texto(respuesta)
            _reparar_tool_calls(respuesta)

        return {"messages": [respuesta], "iteracion": iteracion}

    def decision(state: AgentState):
        """Resuelve o escala. Cuando la decisión choca con el estado, gana el estado."""
        exitos, advertencias = _consultas(state["messages"])
        prompt = PROMPT_DECISION.format(
            resumen=_resumen_del_caso(state),
            hallazgos=exitos,
            advertencias=advertencias,
        )
        datos = _json_de(modelo_base.invoke([HumanMessage(content=prompt)]).content)

        eleccion = "escalar" if "escal" in str(datos.get("decision", "")).lower() else "resolver"
        area = _uno_de(datos.get("area_destino"), AREAS, "")
        prioridad = _uno_de(datos.get("prioridad"), PRIORIDADES, "media")
        justificacion = str(datos.get("justificacion") or "").strip()
        correcciones = []

        # Amenaza de cancelación. La política institucional de la empresa asigna
        # retención de forma directa ante cualquier intención de cancelar, sin
        # pasar por el flujo estándar, así que la decisión del modelo no puede
        # dejar el caso en primera línea ni mandarlo a otra área.
        if state.get("riesgo_churn"):
            if eleccion == "resolver":
                eleccion = "escalar"
                correcciones.append("riesgo de cancelación: no se cierra en primera línea")
            if area != "retencion":
                area = "retencion"
                correcciones.append("riesgo de cancelación: retención por política institucional")
            if prioridad in ("baja", "media"):
                prioridad = "alta"
                correcciones.append("prioridad elevada por riesgo de fuga")

        # Un escalamiento sin área no le sirve al operador: se deduce de la categoría.
        if eleccion == "escalar" and not area:
            area = {
                "tecnica": "soporte_tecnico_n2",
                "facturacion": "facturacion",
                "retencion": "retencion",
                "consulta": "soporte_tecnico_n1",
            }.get(state.get("categoria", ""), "supervision")
            correcciones.append(f"área deducida de la categoría {state.get('categoria')}")

        if eleccion == "resolver":
            area = None

        if correcciones:
            justificacion = (justificacion + " ").strip() + f"[corrección: {'; '.join(correcciones)}]"

        return {
            "decision": eleccion,
            "area_destino": area,
            "prioridad": prioridad,
            "justificacion": justificacion or "Sin justificación explícita del modelo.",
        }

    async def acciones(state: AgentState):
        """Registra la auditoría y, si escala, crea el ticket, ambos por MCP.

        Escribe con los valores del estado, así que la telemetría no puede
        contradecir la respuesta que se le entrega al cliente.
        """
        contacto_id = state.get("contacto_id") or ""
        if not contacto_id:
            return {
                "messages": [
                    AIMessage(
                        content="[auditoría] Sin identificador de contacto: el caso se atiende y el "
                        "registro queda pendiente."
                    )
                ]
            }

        constancias = []
        salida = {}

        detalle = state.get("justificacion") or ""
        if state.get("cliente_identificado"):
            detalle = f"{detalle} Cliente identificado con su cédula.".strip()

        telemetria = tools_accion.get("registrar_telemetria")
        if telemetria is not None:
            crudo = await telemetria.ainvoke(
                {
                    "contacto_id": contacto_id,
                    "categoria": state.get("categoria", "otro"),
                    "categoria_secundaria": state.get("categoria_secundaria"),
                    "tono_detectado": state.get("tono", "neutro"),
                    "urgencia": state.get("urgencia", "media"),
                    "riesgo_churn": bool(state.get("riesgo_churn")),
                    "decision": state.get("decision", "resolver"),
                    "detalle": detalle,
                }
            )
            datos = _json_de(_texto_del_resultado(crudo))
            if datos.get("id"):
                salida["telemetria_id"] = datos["id"]
                constancias.append(f"telemetría {datos['id']}")
            else:
                constancias.append("telemetría rechazada por el sistema de auditoría")

        if telemetria is None:
            constancias.append("el sistema de auditoría no está disponible")

        ticket = tools_accion.get("crear_ticket_escalamiento")
        if state.get("decision") == "escalar" and ticket is None:
            constancias.append("el sistema de tickets no está disponible: el escalamiento queda a mano")
        elif state.get("decision") == "escalar":
            crudo = await ticket.ainvoke(
                {
                    "contacto_id": contacto_id,
                    "cliente_id": state.get("cliente_id"),
                    "categoria": state.get("categoria", "otro"),
                    "prioridad": state.get("prioridad", "media"),
                    "area_destino": state.get("area_destino") or "supervision",
                    "resumen": f"{state.get('texto_contacto', '')[:300]} | {state.get('justificacion', '')}",
                }
            )
            datos = _json_de(_texto_del_resultado(crudo))
            if datos.get("id"):
                salida["ticket_id"] = datos["id"]
                constancias.append(f"ticket {datos['id']} a {state.get('area_destino')}")
            else:
                constancias.append("el ticket no pudo crearse")

        resumen = " · ".join(constancias) if constancias else "sin acciones que registrar"
        salida["messages"] = [AIMessage(content=f"[auditoría] {resumen}")]
        return salida

    def respuesta(state: AgentState, store: BaseStore):
        """Redacta la respuesta al cliente y actualiza su perfil de largo plazo.

        La escritura va al cierre del turno porque es el único punto donde ya
        están auditados todos los valores que el perfil guarda: categoría,
        riesgo de cancelación, ticket y área.
        """
        constancia = ", ".join(
            filter(
                None,
                [
                    f"telemetría {state['telemetria_id']}" if state.get("telemetria_id") else "",
                    f"ticket {state['ticket_id']}" if state.get("ticket_id") else "",
                ],
            )
        )
        exitos, advertencias = _consultas(state["messages"])
        prompt = PROMPT_RESPUESTA.format(
            resumen=_resumen_del_caso(state),
            advertencias=advertencias,
            decision=state.get("decision", "resolver"),
            area_destino=state.get("area_destino") or "no aplica",
            prioridad=state.get("prioridad", "media"),
            justificacion=state.get("justificacion", ""),
            constancia=constancia or "sin constancia registrada",
            hallazgos=exitos,
        )
        salida = {"messages": [modelo_base.invoke([HumanMessage(content=prompt)])]}

        identidad = identidad_cliente(state)
        if store is not None and identidad:
            perfil = actualizar_perfil(store, identidad, state)
            if perfil:
                salida["perfil_datos"] = perfil
                salida["perfil_cliente"] = perfil_a_texto(perfil)

        return salida

    def hay_consultas_pendientes(state: AgentState):
        """Arista condicional: ejecutar herramientas o pasar a decidir."""
        if getattr(state["messages"][-1], "tool_calls", None):
            return "tool_node"
        return "decision"

    agent_builder = StateGraph(AgentState)

    agent_builder.add_node("recepcion", recepcion)
    agent_builder.add_node("compresion_contexto", compresion_contexto)
    agent_builder.add_node("analisis", analisis)
    agent_builder.add_node("consulta", consulta)
    agent_builder.add_node("tool_node", ToolNode(tools_consulta))
    agent_builder.add_node("decision", decision)
    agent_builder.add_node("acciones", acciones)
    agent_builder.add_node("respuesta", respuesta)

    agent_builder.add_edge(START, "recepcion")
    agent_builder.add_conditional_edges("recepcion", debe_comprimir, ["compresion_contexto", "analisis"])
    agent_builder.add_edge("compresion_contexto", "analisis")
    agent_builder.add_edge("analisis", "consulta")
    agent_builder.add_conditional_edges("consulta", hay_consultas_pendientes, ["tool_node", "decision"])
    agent_builder.add_edge("tool_node", "consulta")
    agent_builder.add_edge("decision", "acciones")
    agent_builder.add_edge("acciones", "respuesta")
    agent_builder.add_edge("respuesta", END)

    return agent_builder.compile(checkpointer=checkpointer, store=store)
