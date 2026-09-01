"""[SEMANA 5] ReAct: descomposición explícita de tareas (laboratorio 13).

El ciclo reason ⇄ act es el que ya existía como consulta ⇄ tool_node, ahora
con nombres y traza de Thought propios del patrón:

    Thought  →  el nodo `reason` decide la siguiente consulta o concluye
    Action   →  el nodo `act` ejecuta la herramienta pedida (ToolNode)
    Observation  →  el resultado vuelve a `reason` como ToolMessage

Red de seguridad: `max_iterations` acota las pasadas por `reason`. Al llegar
al límite el modelo ya no puede llamar herramientas y el ciclo termina.
"""

from langchain.messages import SystemMessage
from langchain_ollama.chat_models import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agent.state import AgentState
from agent.tools import get_local_tools
from cli.config import get_settings

# Identificador que busca test_semana5 por AST. No puede vivir solo en un
# comentario: tiene que aparecer en el código.
max_iterations = 4

PROMPT_REASON = """Eres el agente de atención al cliente de Telco Andina. Razonas con el patrón ReAct:
en cada paso piensas (Thought), actuas con una herramienta (Action) y observas el resultado antes
del siguiente paso.

Caso clasificado:
{resumen}

Herramientas de consulta. Invócalas con tool calling, no las describas en texto:
- consultar_base_conocimiento_publica: planes, tarifas, tiendas, horarios, políticas públicas.
- consultar_casos_resueltos: precedentes ya resueltos, filtrados por la categoría del caso.
- consultar_politicas_institucionales: tipo 'vip', 'falla-masiva' o 'palabras-clave', antes de escalar.
{obligatorio}
En cada paso:
1. Escribe un Thought breve (una o dos frases) con lo que vas a hacer y por qué.
2. Llama UNA sola herramienta. No repitas una consulta que ya hiciste.
3. Si el mensaje mezcla temas (facturación, técnico, consulta pública, cancelación), resuelve
   cada fuente en un paso distinto: no concluyas tras la primera observación.
4. Solo cuando ya consultaste todo lo obligatorio, responde sin tool calling: Thought y un
   resumen de una línea de lo encontrado.

El Thought queda en el expediente de auditoría. No inventes datos que una herramienta no devolvió."""

OBLIGATORIO_CHURN = (
    "\nEste caso tiene amenaza de cancelación y puede mezclar varios problemas. Completa estos\n"
    "pasos en este orden, uno por vuelta, antes de concluir:\n"
    "1. consultar_politicas_institucionales con tipo 'vip' (nivel mínimo de escalamiento y retención).\n"
    "2. consultar_casos_resueltos con la categoría principal del caso (precedentes).\n"
    "3. Si el cliente pide información pública (tienda, horario, plan, tarifa),\n"
    "   consultar_base_conocimiento_publica con esa pregunta concreta.\n"
)


def _limite_de(state: AgentState) -> int:
    return int(state.get("max_iteraciones") or max_iterations)


def _anotar_pensamiento(respuesta) -> str:
    """Deja el Thought visible en el mensaje sin romper las tool_calls."""
    pensamiento = str(respuesta.content or "").strip()
    if not pensamiento:
        llamadas = getattr(respuesta, "tool_calls", None) or []
        pensamiento = "; ".join(
            f"{c.get('name')}({', '.join(f'{k}={v}' for k, v in (c.get('args') or {}).items())})"
            for c in llamadas
        )
    if pensamiento and not pensamiento.startswith("[razonamiento]"):
        respuesta.content = f"[razonamiento] {pensamiento}"
        return pensamiento
    return pensamiento.removeprefix("[razonamiento]").strip()


def build_react_nodes(modelo_base, modelo_con_tools, tools_consulta: list):
    """Nodos `reason` y `act` listos para enchufar en cualquier grafo.

    `hay_accion_pendiente` devuelve las claves 'act' | 'continuar' para que el
    grafo anfitrión mapee 'continuar' a `decision` o a END.
    """
    from agent.graph import (
        _conversacion,
        _reparar_tool_calls,
        _rescatar_tool_calls_de_texto,
        _resumen_del_caso,
    )

    def reason(state: AgentState):
        """Thought: decide la siguiente Action o concluye el ciclo."""
        iteracion = state.get("iteracion", 0) + 1
        limite = _limite_de(state)

        instrucciones = PROMPT_REASON.format(
            resumen=_resumen_del_caso(state),
            obligatorio=OBLIGATORIO_CHURN if state.get("riesgo_churn") else "",
        )
        mensajes = [SystemMessage(content=instrucciones), *_conversacion(state["messages"])]

        if iteracion >= limite:
            respuesta = modelo_base.invoke(
                mensajes
                + [
                    SystemMessage(
                        content="Alcanzaste el límite de pasos ReAct. No llames herramientas. "
                        "Cierra con el Thought y un resumen de una línea de lo que tienes."
                    )
                ]
            )
            # Sin Act posterior: una tool_call huérfana rompería el expediente.
            if getattr(respuesta, "tool_calls", None):
                respuesta.tool_calls = []
        else:
            respuesta = modelo_con_tools.invoke(mensajes)
            _rescatar_tool_calls_de_texto(respuesta)
            _reparar_tool_calls(respuesta)

        pensamiento = _anotar_pensamiento(respuesta)
        return {
            "messages": [respuesta],
            "iteracion": iteracion,
            "max_iteraciones": limite,
            "razonamiento": pensamiento,
        }

    act = ToolNode(tools_consulta)

    def hay_accion_pendiente(state: AgentState):
        """Arista condicional: ejecutar la Action o salir del ciclo ReAct."""
        if getattr(state["messages"][-1], "tool_calls", None):
            if state.get("iteracion", 0) >= _limite_de(state):
                return "continuar"
            return "act"
        return "continuar"

    return reason, act, hay_accion_pendiente


def build_reasoning_graph(tools: list | None = None):
    """Compila el grafo ReAct autónomo que exige el contrato de la semana 5.

    Forma:

        START -> reason -> act -> reason -> ... -> END
                              |
                              +-> END  (sin tool_calls o al alcanzar max_iterations)
    """
    from agent.graph import TOOLS_DE_ACCION

    if tools is None:
        tools = get_local_tools()

    tools_consulta = [t for t in tools if getattr(t, "name", "") not in TOOLS_DE_ACCION]
    settings = get_settings()
    modelo_base = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        num_ctx=settings.ollama_num_ctx,
    )
    modelo_con_tools = modelo_base.bind_tools(tools_consulta) if tools_consulta else modelo_base

    reason, act, hay_accion_pendiente = build_react_nodes(
        modelo_base, modelo_con_tools, tools_consulta
    )

    builder = StateGraph(AgentState)
    builder.add_node("reason", reason)
    builder.add_node("act", act)
    builder.add_edge(START, "reason")
    builder.add_conditional_edges(
        "reason", hay_accion_pendiente, {"act": "act", "continuar": END}
    )
    builder.add_edge("act", "reason")
    return builder.compile()
