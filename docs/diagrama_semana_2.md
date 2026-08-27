# Diagrama del Agente Propuesto — Semana 2 (Tool Calling y MCP)

Este diagrama corresponde a la implementación del agente con tool calling e integración de herramientas locales y del servidor MCP.

Las convenciones son las mismas: las cajas técnicas son pasos deterministas del código, las moradas son pasos donde razona el modelo y los rombos son decisiones agénticas.

```mermaid
flowchart TD
    classDef ovalo fill:#2d2d2d,stroke:#a0a0a0,stroke-width:2px,color:#ffffff;
    classDef rectangulo fill:#1e1e1e,stroke:#a0a0a0,stroke-width:2px,color:#ffffff;
    classDef nodoLLM fill:#4a148c,stroke:#ce93d8,stroke-width:4px,color:#ffffff;
    classDef rombo fill:#1e1e1e,stroke:#a0a0a0,stroke-width:2px,color:#ffffff;
    classDef fase2 fill:#1e1e1e,stroke:#666,stroke-width:2px,color:#888888,stroke-dasharray: 5 5;

    INICIO(["Mensaje del cliente<br>+ metadatos (canal, timestamp, sesión)"])

    RECEPCION["recepcion<br>Obtiene el contacto real del punto de integración:<br>lo trae si el cliente lo citó, o lo registra"]

    ANALISIS["analisis<br>Tono, urgencia, riesgo de cancelación,<br>categoría y señales del texto"]

    CONSULTA["consulta<br>Decide qué información necesita"]

    DEC_TOOLS{"¿Pidió herramientas?"}

    TOOLS["tool_node<br>Ejecuta las consultas pedidas"]

    subgraph LECTURA ["Herramientas de consulta"]
        T1["consultar_base_conocimiento_publica<br>RAG institucional"]
        T2["consultar_politicas_institucionales<br>vip · falla-masiva · palabras-clave"]
        T3["consultar_casos_resueltos<br>Precedentes"]
        T4["obtener_contacto<br>Punto de integración"]
    end

    DECISION["decision<br>Resolver o escalar, con área,<br>prioridad y justificación"]

    ACCIONES["acciones<br>Registra la telemetría y crea el ticket<br>con los valores del estado"]

    subgraph ESCRITURA ["Servidor MCP · proceso independiente por stdio"]
        T5["registrar_contacto"]
        T6["registrar_telemetria"]
        T7["crear_ticket_escalamiento"]
    end

    RESPUESTA["respuesta<br>Respuesta al cliente en el tono adecuado<br>+ expediente de siete secciones"]

    AUTH["Autenticación del cliente y acceso al perfil<br>Alcance de la fase dos"]

    FIN(["Expediente auditable<br>+ respuesta al cliente"])

    INICIO --> RECEPCION
    RECEPCION --> ANALISIS
    ANALISIS --> CONSULTA
    CONSULTA --> DEC_TOOLS
    DEC_TOOLS -- "Sí" --> TOOLS
    DEC_TOOLS -- "No" --> DECISION
    TOOLS --> LECTURA
    LECTURA --> CONSULTA
    DECISION --> ACCIONES
    ACCIONES --> ESCRITURA
    ESCRITURA --> RESPUESTA
    RECEPCION -.-> T5
    RESPUESTA --> FIN
    AUTH -.-> ESCRITURA

    class INICIO,FIN ovalo;
    class RECEPCION,TOOLS,ACCIONES,T1,T2,T3,T4,T5,T6,T7 rectangulo;
    class ANALISIS,CONSULTA,DECISION,RESPUESTA nodoLLM;
    class DEC_TOOLS rombo;
    class AUTH fase2;
```

Diferencias con el diagrama de la semana 1:

- El flujo dejó de ser una secuencia única. El tramo `consulta ⇄ tool_node` es un ciclo, y el modelo decide en cada vuelta qué consulta.
- El registro de auditoría y la creación del ticket quedaron dentro de un paso determinista (`acciones`), que corre siempre entre la decisión y la respuesta.
- Las herramientas quedaron separadas por su efecto: las de lectura corren en el proceso del agente y las tres que escriben viven en el servidor MCP.
- La red de seguridad del ciclo vive en el estado (`iteracion`, `max_iteraciones`).
- La rama de autenticación queda marcada como alcance de la fase dos.
