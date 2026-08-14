"""[SEMANA 2] Grafo del agente (laboratorios 4 y 5).

Aquí se construye el agente como un grafo de LangGraph. En la primera etapa el
agente es LINEAL: un nodo que invoca al LLM (con las herramientas vinculadas) y
un nodo que ejecuta las herramientas que el modelo pida, conectados en un ciclo
`agente ⇄ herramientas` hasta que el modelo responde sin pedir más herramientas.
"""

from langchain_ollama.chat_models import ChatOllama
from langchain.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from agent.tools import get_local_tools
from agent.state import AgentState
from cli.config import get_settings


def should_continue(state: AgentState):
    """
    Decide si el agente debe continuar hacia la ejecución de herramientas
    o si debe terminar y retornar la respuesta final al usuario.
    """
    messages = state['messages']
    last_msg = messages[-1]

    if getattr(last_msg, "tool_calls", None):
        return 'tool_node'

    return END


def build_graph(tools: list | None = None, checkpointer=None):
    """Compila y devuelve el grafo del agente, listo para invocar.

    Parámetros:
        tools:        herramientas disponibles para el agente (locales + MCP).
        checkpointer: memoria de corto plazo (se usa desde la semana 4). Si es
                      None, el grafo funciona igual pero sin persistencia.

    Debe devolver un grafo YA COMPILADO (el resultado de `.compile(...)`).
    """
    if tools is None:
        tools = get_local_tools()
        
    settings = get_settings()
    
    # Inicializar el modelo con los parámetros centralizados
    model = ChatOllama(
        model=settings.ollama_model, 
        base_url=settings.ollama_base_url, 
        temperature=0.3
    ).bind_tools(tools)

    # Definir el nodo de llamada al LLM localmente para capturar el 'model'
    def llm_call(state: AgentState):
        """
        Nodo en el que el modelo decide si hacer llamadas a herramientas o responder al usuario.
        """
        messages = state['messages']
        # Nos aseguramos de inyectar el SystemMessage si no está presente
        if not messages or not isinstance(messages[0], SystemMessage):
            system_prompt = SystemMessage(content=(
                "Eres un asistente de atención al cliente de Telco Andina. "
                "Responde a las solicitudes utilizando las herramientas disponibles para consultar la base "
                "de conocimiento, verificar clientes o crear tickets de escalamiento."
            ))
            messages = [system_prompt] + messages
            
        response = model.invoke(messages)
        return {"messages": [response]}

    agent_builder = StateGraph(AgentState)

    # Añadir nodos
    agent_builder.add_node('llm_call', llm_call)
    
    # Usar el ToolNode de langgraph.prebuilt que maneja eficientemente
    # las herramientas síncronas y asíncronas (como las de MCP)
    agent_builder.add_node('tool_node', ToolNode(tools))

    # Definir la lógica de transiciones
    agent_builder.add_edge(START, 'llm_call')
    agent_builder.add_conditional_edges(
        'llm_call',
        should_continue,
        ['tool_node', END]
    )
    agent_builder.add_edge('tool_node', 'llm_call')

    return agent_builder.compile(checkpointer=checkpointer)
