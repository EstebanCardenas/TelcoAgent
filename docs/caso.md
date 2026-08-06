# Caso de Negocio
## Centro de Atención de Requerimientos
## Telco Andina — Área de Servicio al Cliente

> *“El sistema anterior nos costó más clientes de los que nos ahorró agentes. Le respondía con la plantilla de disculpas estándar a alguien que llevaba cinco días sin internet y ya había llamado tres veces. Eso no es automatización, eso es ignorar al cliente con un bot.”*  
> — **Nicolle Rozo**, Directora de Operaciones, Telco Andina

---

## 1. Contexto

Telco Andina es un operador de telecomunicaciones con servicios de internet, telefonía móvil y televisión. Su centro de atención al cliente recibe entre 600 y 900 contactos diarios a través de tres canales: chat del sitio web, correo electrónico y llamadas telefónicas que llegan al área de análisis ya transcritas a texto.

Cada contacto es un mensaje de un cliente que está molesto, confundido, apurado o, en el peor de los casos, a punto de irse a la competencia. Algunos son triviales. Otros son críticos. La mayoría está en algún punto intermedio, y muchos mezclan varias cosas a la vez: una queja técnica con un reclamo de facturación y una amenaza de cancelación, todo en el mismo párrafo.

Actualmente cada contacto lo lee un agente humano de primera línea que, en cuestión de minutos, tiene que entender qué está pidiendo realmente el cliente, medir qué tan molesto está, decidir si puede resolverlo o debe escalarlo, escribir una respuesta que no empeore la situación y dejar registro de lo que pasó. Con el volumen actual, ese proceso es inconsistente, costoso y difícil de escalar.

---

## 2. El problema

Telco Andina ha identificado que la mayoría de los contactos que llegan al centro presentan el mismo patrón estructural: el cliente expresa varios problemas a la vez y los combina con señales emocionales que determinan la urgencia real del caso. Esta complejidad no es un error del cliente; es la forma natural en que una persona comunica una experiencia de servicio deficiente.

Los agentes expertos resuelven esta complejidad aplicando un criterio que no se puede descomponer en reglas: primero leen el tono del mensaje para calibrar el nivel de urgencia, luego identifican qué categorías de problema están presentes, luego ponderan cuál tiene prioridad según el contexto del mensaje, y finalmente deciden si el caso se resuelve en primera línea o debe escalar, y a quién. Cada uno de esos pasos depende del anterior, y el resultado correcto varía caso a caso.

Este proceso de análisis contextual y toma de decisión adaptativa es lo que el sistema actual no puede replicar de manera consistente a escala. Las reglas fijas pueden detectar palabras clave como “cancelar” o “sin internet”, pero no pueden ponderar el conjunto de señales que determinan la decisión correcta: el tono acumulado, la presencia de múltiples problemas y el riesgo implícito de churn. El resultado es una atención inconsistente entre agentes y una incapacidad real para auditar si las decisiones tomadas fueron las correctas.

---

## 3. Actores y fuentes de información

* **Cliente digital — usuario del agente:** Persona que se comunica con Telco Andina por el canal conversacional (chat). Es quien interactúa directamente con el agente. Puede estar en cualquier estado emocional y su mensaje puede mezclar múltiples temas; no tiene por qué expresarse con claridad ni usar la terminología técnica de la empresa.
* **Áreas de atención humana — destino de escalamiento:** Cuando un caso supera lo que el agente puede resolver, se transfiere a un área humana especializada: soporte técnico de primer y segundo nivel, facturación, retención y supervisión. Reciben el caso ya analizado y estructurado (mediante un ticket) para resolverlo sin releer la conversación. *No son usuarios del agente*: son el destino de sus decisiones de escalamiento, y la dirección es explícita en que el agente no busca reemplazarlas, sino filtrarles y estructurarles el trabajo.
* **Base de conocimiento institucional — información pública:** Documentación de la empresa que no depende de ningún cliente y cualquiera puede consultar sin identificarse: catálogo de planes, tarifas y promociones; tiendas y horarios; canales de atención; y políticas institucionales (PQR, clientes VIP, compensaciones por falla, protocolo de falla masiva, cancelación). Son textos libres que el agente recupera por búsqueda semántica sobre una base documental (RAG), no por consulta estructurada.
* **Sistema de información del cliente — datos privados:** Repositorio con el perfil de cada cliente: plan y servicios contratados, líneas telefónicas, facturación, antigüedad, condición VIP, riesgo de fuga y estado de cuenta, además de su historial de reclamos y sus tickets. Solo puede consultarse *después de autenticar al cliente* (cédula + clave del portal), y nunca se exponen los datos de una persona a otra.
* **Base de conocimiento histórico:** Repositorio de casos previamente resueltos por la empresa (síntoma → solución aplicada). Permite proponer soluciones ya probadas y mantener consistencia en las decisiones, en lugar de evaluar cada caso como si fuera el primero. Es conocimiento operativo de la empresa —no datos de un cliente particular—, por lo que puede consultarse sin autenticación.
* **Sistema de telemetría:** Registro operativo y regulatorio de toda interacción procesada. Por exigencia de auditoría, cada caso atendido debe quedar registrado antes de que se emita cualquier respuesta al cliente.

---

## 4. Flujo actual y sus limitaciones

Cuando un contacto llega al centro de atención, el proceso actual funciona así:
- Un agente de primera línea lee el mensaje completo e intenta identificar de qué se trata y cuál es el estado emocional del cliente.
- Con base en esa lectura, decide si puede resolver el caso directamente o si debe transferirlo a un área especializada.
- Redacta una respuesta al cliente o prepara el expediente para la transferencia.
- Registra lo ocurrido en el sistema de la operación para trazabilidad.

Las limitaciones son estructurales. La lectura e interpretación de cada mensaje depende enteramente del criterio del agente, que varía según experiencia, carga de trabajo y estado de ánimo. Los mensajes mixtos, que combinan varios tipos de problema en un mismo texto, son especialmente problemáticos porque no hay una regla clara de cómo priorizarlos. Y la trazabilidad es incompleta: el registro refleja la decisión final pero no el razonamiento que la produjo, lo que dificulta la auditoría y el aprendizaje organizacional.

---

## 5. Situaciones representativas

Las siguientes situaciones ilustran el tipo de casos que el centro recibe a diario y que el flujo actual no resuelve de manera consistente:

* **Situación A**  
  Lo que el cliente escribe: *“¿A qué hora cierra la tienda de Chapinero?”*  
  Este caso es trivial en contenido pero igual requiere una decisión: ¿es una consulta que se resuelve directamente con información pública, o hay alguna señal en el tono o el contexto que sugiera que hay algo más detrás? Es también el ejemplo más claro de una consulta que *no requiere identificar al cliente*: cualquiera puede preguntar por el horario de una tienda sin autenticarse. El sistema debe reconocer cuándo un mensaje es genuinamente simple y de información pública, resolverlo sin escalarlo ni pedir datos personales, algo que el sistema anterior con reglas fijas no hacía bien porque no distinguía entre urgencia real y vocabulario de urgencia.

* **Situación B**  
  Lo que el cliente escribe: *“Llevo cinco días sin internet, ya llamé tres veces, si no me resuelven hoy cancelo todo y me llevo las tres líneas a la competencia.”*  
  Este mensaje combina una falla técnica (cinco días sin internet), un historial de reclamos previos (ya llamó tres veces), una amenaza explícita de cancelación y un nivel de urgencia alto que se expresa en el tono. Cada una de esas dimensiones cambia la decisión correcta: el caso no puede resolverse en primera línea, debe escalar a retención con prioridad alta, y la respuesta al cliente no puede ser una plantilla genérica de disculpas. Un sistema que solo clasifica por palabras clave puede detectar “cancelar” pero no puede ponderar el conjunto.

* **Situación C**  
  Lo que el cliente escribe: *“Me cobraron dos veces el mes pasado, el servicio de internet lleva lento tres días y encima el técnico que mandaron la semana pasada fue muy grosero. No sé si seguir con ustedes.”*  
  Este es el caso más frecuente y el más difícil: un mensaje que mezcla tres problemas distintos (facturación, técnico y calidad del servicio) con un tono de frustración acumulada y una amenaza implícita de cancelación. La decisión correcta implica identificar qué problema es el más urgente, cómo priorizarlos, a qué área o áreas escalar, y cómo redactar una respuesta que reconozca los tres problemas sin prometer lo que no se puede cumplir. Ninguna regla fija puede capturar esa ponderación.

---

## 6. Lo que la empresa necesita

Telco Andina requiere una solución que procese cada contacto de forma autónoma y sea capaz de:
- Comprender el contenido real del mensaje aunque el cliente lo exprese de forma desordenada, indirecta o mezclando varios temas. Distinguir entre fallas técnicas, disputas de facturación, intenciones de cancelar, consultas de información y otras categorías, incluidos los casos que combinan varias a la vez.
- Evaluar desde el primer momento si la solicitud puede resolverse con información pública (planes, tarifas, tiendas, horarios, políticas) o si toca la cuenta del cliente (su factura, sus cobros, su plan, su historial). Lo primero se responde sin identificar a nadie; lo segundo exige autenticar al cliente antes de acceder a sus datos. Esa distinción debe surgir del análisis del mensaje, no de reglas fijas por palabra clave.
- Leer el estado emocional del cliente y sustentar esa lectura en señales concretas del texto: mayúsculas sostenidas, repeticiones, palabras cargadas, amenazas explícitas o veladas de cancelación, expresiones de gratitud. Estimar la urgencia del caso y el riesgo de que el cliente se vaya.
- Decidir el tratamiento correcto estableciendo si el caso puede resolverse en primera línea o debe escalarse, a qué área y con qué prioridad, con una justificación explícita de la decisión que el equipo pueda revisar y auditar.
- Producir una respuesta apropiada al tono detectado: la misma información no se le escribe igual a un cliente cordial que a uno furioso. La respuesta debe entregar compromisos concretos y respetar las políticas de la empresa.
- Dejar un expediente completo para la operación que cubra obligatoriamente siete secciones: información general de la interacción, análisis de tono y carga emocional, clasificación del problema, decisión de resolución o escalamiento, respuesta al cliente, acciones recomendadas para el operador humano, y recomendaciones y pendientes.

La dirección es explícita en un punto: no quiere reemplazar a los agentes humanos. Quiere que el sistema haga el trabajo analítico repetitivo para que los agentes puedan concentrarse en los casos que de verdad necesitan criterio humano. La consistencia y la auditabilidad son tan importantes como la calidad del análisis.

---

## 7. Restricciones y consideraciones

* **Canales de entrada:** Chat del sitio web, correo electrónico y llamadas telefónicas transcritas a texto. El sistema trabaja exclusivamente con texto; no hay voz ni video. La solución se construye y evalúa sobre el *canal conversacional (chat)*, donde el cliente interactúa en vivo; el correo y las llamadas transcritas se mencionan como contexto del negocio y se simulan (llegan como contactos ya registrados), pero no se desarrollan como canales independientes.
* **Alcance de la primera fase:** El sistema trabaja únicamente con el mensaje del cliente y sus metadatos: canal de entrada, timestamp e identificador de sesión. No tiene acceso al perfil del cliente ni a su historial en esta fase.
* **Acceso al contenido:** El contenido de cada contacto se obtiene a través de un punto de integración interno que entrega el mensaje y sus metadatos. No puede recibirse por otro medio.
* **Registro obligatorio:** Por exigencia de auditoría regulatoria, toda interacción procesada debe quedar registrada en el sistema de telemetría de la operación antes de que se emita cualquier respuesta. Si el sistema atendió un caso, debe existir constancia verificable de que lo atendió.
* **Coherencia interna:** La clasificación del problema, la decisión de escalamiento y la respuesta al cliente no pueden contradecirse entre sí dentro de un mismo caso.
* **Alcance de la segunda fase:** En la segunda fase el sistema incorpora acceso al perfil del cliente (plan, servicios y líneas contratadas, facturación, antigüedad, condición VIP, riesgo de fuga previo, estado de cuenta), su historial de reclamos, el sistema de tickets, un repositorio de casos resueltos para consultar precedentes, y el canal de notificaciones al cliente. El acceso a estos datos privados exige autenticación previa del cliente (ver *Privacidad y autenticación*).
* **Privacidad y autenticación:** Los datos de un cliente son privados: el sistema solo puede consultarlos o verificarlos después de que el cliente se autentique con su número de cédula y su clave de canal digital (4 dígitos, la misma del portal). Nadie puede consultar los datos de otra persona. Las consultas de información pública (planes, tarifas, tiendas, horarios, cobertura, políticas) no requieren autenticación y deben poder resolverse para clientes anónimos. Por eso el sistema debe evaluar primero la solicitud y pedir credenciales únicamente cuando la gestión toque la cuenta del cliente —por ejemplo, verificar un cobro que el cliente disputa contra su facturación real.
* **Políticas institucionales:** Existen políticas declaradas que el sistema debe respetar: clientes VIP con un nivel mínimo de escalamiento garantizado, productos con falla masiva conocida que activan un protocolo especial, y palabras clave que obligan a revisión por supervisión.

---

## 8. Estructura del análisis

El agente debe producir un análisis completo que cubra obligatoriamente las siguientes 7 secciones, organizadas de forma clara y diferenciada en su output:

### 1. Información general de la interacción
- Identificador de la sesión, canal (chat, correo, llamada transcrita) y timestamp.
- Resumen del mensaje del cliente en máximo dos líneas, en lenguaje neutro.
- Idioma detectado y, si aplica, presencia de mezcla de idiomas o jerga regional relevante.

### 2. Análisis de tono y carga emocional
- Tono dominante: frustrado, urgente, agresivo, neutro o cordial.
- Señales lingüísticas que sustentan la clasificación: uso de mayúsculas sostenidas, repetición, palabras cargadas, amenazas explícitas, expresiones de gratitud.
- Nivel de urgencia percibido (alto, medio, bajo) y justificación.
- Indicador de riesgo de churn: si el mensaje contiene amenazas explícitas o implícitas de cancelación.

### 3. Clasificación del problema
- Categoría principal: técnica, facturación, retención/cancelación, consulta de información, otro.
- Categoría secundaria si el mensaje es mixto.
- Subtipo dentro de la categoría principal (por ejemplo, en técnica: falla de conexión, lentitud, falla de servicio de TV, problema con el equipo).
- Componentes o servicios mencionados explícitamente por el cliente.

### 4. Decisión de resolución vs. escalamiento
- Recomendación: resolver en primera línea o escalar.
- Si escala: nivel destino (soporte técnico N1, soporte técnico N2, facturación, retención, supervisión) y motivo explícito.
- Prioridad asignada al caso (alta, media, baja).
- Tiempo estimado de respuesta esperado por el cliente según el tono detectado.

### 5. Respuesta generada al cliente
- Texto completo de la respuesta sugerida, redactada en el tono apropiado para el cliente.
- Información concreta que se entrega (compromiso, plazo, próximo paso).
- Elementos explícitamente omitidos por política (por ejemplo, no prometer compensaciones sin autorización) y justificación.

### 6. Acciones recomendadas para el operador humano
- Si el caso se escala: información clave que el operador receptor debe tener antes de tomar el caso.
- Si el caso se resuelve: confirmación que debe registrarse en el sistema.
- Alertas especiales: cliente en riesgo de churn, cliente potencialmente agresivo, posible caso regulatorio.

### 7. Recomendaciones y preguntas pendientes
- Lista de las recomendaciones más relevantes para la operación antes de cerrar el caso.
- Lista de información faltante que debería solicitarse al cliente en un siguiente turno para resolver de manera definitiva (por ejemplo, número de cuenta, dirección de instalación, modelo del equipo).

---

## 9. Criterios de éxito

Telco Andina considerará exitosa la solución si cumple los siguientes criterios:
- El sistema identifica correctamente el tipo de problema del cliente, incluyendo los casos mixtos con múltiples categorías, en al menos el 80% de los casos de prueba.
- La lectura del estado emocional está sustentada en señales concretas del texto, no en una clasificación genérica sin respaldo.
- La decisión de escalamiento incluye siempre el área de destino, la prioridad y la justificación explícita. El mismo caso produce la misma decisión independientemente de cuándo se procesa.
- La respuesta al cliente varía en tono según el estado emocional detectado: la misma información se expresa de manera diferente para un cliente cordial y para uno furioso.
- El expediente cubre las siete secciones obligatorias en el mismo formato para todos los casos, de manera que la operación pueda auditar cualquier interacción sin necesidad de releer el mensaje original.
- En la segunda fase, el sistema demuestra con evidencia cuantitativa que el acceso al perfil e historial del cliente cambia la decisión de escalamiento en al menos un porcentaje medible de los casos, y que el tratamiento es diferenciado según quién es el cliente.
