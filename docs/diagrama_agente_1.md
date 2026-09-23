# Diagrama del Agente 1 final

Grafo compilado en `agent/graph.py`. El ciclo `reason` / `act` sale de `agent/reasoning/react.py`. La llamada al Asesor de Retención sale de `acciones` por `agent/a2a_cliente.py` y no es un nodo del grafo.

El detalle del Agente 2 está en `diagrama_agente_2.md`. Aquí ese proceso es una caja: el Agente 1 le manda el expediente y solo cita el `compromiso` si el código lo revalida.

## Qué hace cada tramo

- `recepcion` consigue el contacto. Si el mensaje cita un `CTO-xxx`, llama a `obtener_contacto`. Si no, registra el entrante con `registrar_contacto`. Si hay cédula, `cliente_existe` solo dice si la persona existe. El perfil del Store entra en este nodo.
- `compresion_contexto` resume los mensajes anteriores al último del cliente cuando la conversación activa pasa de 6 mensajes.
- `analisis` clasifica tono, urgencia, categoría y `riesgo_churn`.
- `reason` y `act` son el ciclo ReAct. Thought en `reason`, Action en `act`, Observation de vuelta a `reason`. El tope es 4 pasos (`max_iterations`). Al llegar, el modelo ya no puede llamar herramientas.
- `decision` propone resolver o escalar. Si hay `riesgo_churn`, el código fuerza `escalar`, área `retencion` y prioridad al menos `alta`.
- `acciones` escribe telemetría y, si escala, el ticket. Los dos salen del estado, no del texto que el modelo acaba de redactar. Solo si la decisión es escalar a retención, hay riesgo de cancelación y el ticket existe, arma el expediente y llama al Agente 2.
- `respuesta` redacta lo que oye el cliente y actualiza el perfil en el Store. Si el artefacto no pasó la revalidación, informa el escalamiento y no nombra cifras.

## Fuentes

| Fuente | Quién la toca | Qué saca |
| ----- | ----- | ----- |
| RAG institucional | `consultar_base_conocimiento_publica`, desde `act` | Planes, tarifas, tiendas, horarios, políticas públicas |
| API empresarial | `consultar_politicas_institucionales`, `consultar_casos_resueltos`, `obtener_contacto` | Políticas, precedentes y el contacto citado |
| API empresarial, vía MCP | `registrar_contacto`, `registrar_telemetria`, `crear_ticket_escalamiento` | Escrituras de auditoría y tickets |
| Checkpointer (`data/checkpoints.sqlite`) | El grafo, por `thread_id` | El turno en curso |
| Store (`data/memoria_largo_plazo.sqlite`) | `recepcion` lee, `respuesta` escribe | Perfil del cliente entre conversaciones |
| Agente 2, HTTP en el puerto 8090 | `acciones`, cliente A2A | `compromiso` ya filtrado. La revalidación lee `GET /ofertas/{id}` y `GET /topes/{segmento}` |

El `segmento` del expediente sale del perfil o de una herramienta que marcó VIP. El chat no lo mueve. `motivo` y `resumen` salen de la clasificación, no del mensaje crudo.

## Convenciones

- Óvalos: entrada del cliente y fin del turno.
- Rectángulos: nodos de código (`recepcion`, `act`, `acciones`).
- Rectángulos de borde grueso morado: nodos donde habla el modelo.
- Rombos: aristas del grafo.
- Cilindros verde azulado: memoria del Agente 1 (Checkpointer y Store).
- Cilindros verdes: fuentes de datos (RAG y API empresarial).
- Caja azul: el Agente 2, otro proceso. El trazo punteado es una llamada, no una arista de LangGraph.

```mermaid
flowchart TD
    classDef ovalo fill:#2d2d2d,stroke:#a0a0a0,stroke-width:2px,color:#ffffff;
    classDef rectangulo fill:#1e1e1e,stroke:#a0a0a0,stroke-width:2px,color:#ffffff;
    classDef nodoLLM fill:#4a148c,stroke:#ce93d8,stroke-width:4px,color:#ffffff;
    classDef rombo fill:#1e1e1e,stroke:#a0a0a0,stroke-width:2px,color:#ffffff;
    classDef memoria fill:#004d40,stroke:#80cbc4,stroke-width:2px,color:#ffffff;
    classDef externo fill:#0d47a1,stroke:#90caf9,stroke-width:2px,color:#ffffff;
    classDef fuente fill:#1b5e20,stroke:#a5d6a7,stroke-width:2px,color:#ffffff;

    START(["START<br>Mensaje del cliente y thread_id"])
    CARGA[("Checkpointer<br>carga el turno desde checkpoints.sqlite")]
    GUARDA[("Checkpointer<br>guarda el estado del turno")]
    STORE[("Store<br>perfil e historial en memoria_largo_plazo.sqlite")]

    RECEPCION["recepcion<br>Contacto citado o registro del entrante.<br>Carga el perfil del Store."]
    DEC_COMP{"¿Más de 6 mensajes<br>en la conversación activa?"}
    COMPRESION["compresion_contexto<br>Resume lo anterior al último mensaje<br>y borra esos mensajes del estado"]
    ANALISIS["analisis<br>Tono, urgencia, categoría<br>y riesgo de cancelación"]

    REASON["reason<br>Thought: siguiente consulta o cierre del ciclo"]
    DEC_ACT{"¿Pidió una herramienta<br>y aún no llega a 4 pasos?"}
    ACT["act<br>Ejecuta la herramienta pedida"]

    subgraph LECTURA ["Lecturas en el proceso del Agente 1"]
        T1["consultar_base_conocimiento_publica<br>RAG"]
        T2["consultar_politicas_institucionales<br>vip, falla-masiva, palabras-clave"]
        T3["consultar_casos_resueltos<br>precedentes por categoría"]
        T4["obtener_contacto<br>GET /telecom/contactos"]
    end

    DECISION["decision<br>Resolver o escalar.<br>Si hay riesgo de cancelación, el código<br>fuerza retención y sube la prioridad."]
    ACCIONES["acciones<br>Telemetría y ticket con los valores del estado."]

    subgraph MCP ["Servidor MCP, proceso aparte por stdio"]
        REG["registrar_contacto"]
        TEL["registrar_telemetria"]
        TKT["crear_ticket_escalamiento"]
    end

    subgraph A2 ["Agente 2 en el puerto 8090. Ver diagrama_agente_2.md"]
        ARM["Arma el expediente en código.<br>segmento desde el perfil.<br>motivo y resumen desde la clasificación."]
        ESPERA["POST /tareas y sondeo GET.<br>2 s para submitted, 8 s en working."]
        REV["Revalida oferta_id, valor y meses<br>con GET /ofertas y GET /topes.<br>Si no pasa, descarta sin reintento."]
    end

    RESPUESTA["respuesta<br>Texto al cliente.<br>Cita el compromiso solo si quedó autorizado.<br>Actualiza el perfil en el Store."]
    FIN(["END<br>Respuesta del turno"])

    RAG[("RAG institucional")]
    API[("API empresarial del curso")]

    START --> CARGA --> RECEPCION
    STORE -.->|"lee el perfil"| RECEPCION
    RECEPCION --> DEC_COMP
    DEC_COMP -- "sí" --> COMPRESION --> ANALISIS
    DEC_COMP -- "no" --> ANALISIS
    ANALISIS --> REASON
    REASON --> DEC_ACT
    DEC_ACT -- "sí" --> ACT
    DEC_ACT -- "no" --> DECISION
    ACT --> LECTURA
    LECTURA --> REASON

    DECISION --> ACCIONES
    ACCIONES --> RESPUESTA
    RESPUESTA -.->|"escribe perfil e historial"| STORE
    RESPUESTA --> GUARDA --> FIN

    RECEPCION -.->|"sin CTO citado"| REG
    RECEPCION -.->|"CTO citado"| T4
    ACCIONES -.-> TEL
    ACCIONES -.-> TKT
    ACCIONES -.->|"escalar a retención,<br>con riesgo de cancelación<br>y ticket creado"| ARM
    ARM --> ESPERA --> REV
    REV -.->|"compromiso validado,<br>o escalamiento sin cifra"| RESPUESTA
    REV -.->|"si deriva_n2, otro ticket<br>a soporte_tecnico_n2"| TKT

    T1 -.-> RAG
    T2 -.-> API
    T3 -.-> API
    T4 -.-> API
    REG -.-> API
    TEL -.-> API
    TKT -.-> API

    class START,FIN ovalo;
    class RECEPCION,ACT,ACCIONES,T1,T2,T3,T4,REG,TEL,TKT rectangulo;
    class COMPRESION,ANALISIS,REASON,DECISION,RESPUESTA nodoLLM;
    class DEC_COMP,DEC_ACT rombo;
    class CARGA,GUARDA,STORE memoria;
    class RAG,API fuente;
    class ARM,ESPERA,REV externo;
```
