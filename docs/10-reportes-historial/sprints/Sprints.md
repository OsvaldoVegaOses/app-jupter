Backend CLI
                                                                                
  - Activa tu entorno: source .venv/bin/activate (Linux/macOS)                  
    o .venv\Scripts\Activate.ps1 (Windows PowerShell).                          
  - Exporta variables si necesitas un .env: export ENV_FILE=.env.               
  - Verifica dependencias: pip install -e . (usa requirements.txt si prefieres  
    pip install -r requirements.txt).                                           
  - Ejecuta diagnósticos/flujo:                                                 
      - python main.py status --project <id> (actualiza metadata/projects/<id>.json).          
      - python main.py status --json --no-update (snapshot solo lectura).       
      - Otros comandos según etapa (python main.py ingest …, python main.py     
        transversal dashboard …, etc.).                                         
                                                                                
  Frontend React                                                                
                                                                                
  - Ir al directorio: cd frontend.                                              
  - Instalar dependencias: npm install (o pnpm install/yarn install si usas     
    otro gestor).
  - Lanzar en desarrollo: npm run dev.
  - Abre el dashboard en el link que entrega Vite (normalmente http://
    localhost:5173/); usa el botón “Refrescar estado”.

  Configuración adicional

  - Si tu intérprete no es python, exporta PROJECT_PYTHON=/ruta/a/python antes   
    de npm run dev para que el proxy del frontend ejecute el binario correcto.   
  - Asegúrate de haber corrido python main.py status sin --no-update antes de    
    abrir el dashboard para persistir metadata/projects/<id>.json e informes/    
    report_manifest.json actualizados.



1.- Reflexion:  a)  Etapa 0 – Preparación, Reflexividad y Configuración del Análisis

Datos y PostgreSQL: En la fase preparatoria se recopilan y organizan los datos brutos. Si se trata de entrevistas transcritas, PostgreSQL es útil para almacenarlas de forma estructurada y confiable, preservando la integridad de la información
postgresql.org
. Esta base de datos relacional, conocida por su robustez y rendimiento, servirá como repositorio central de los textos a analizar.

Reflexividad: Aún no se explotan herramientas avanzadas como Qdrant o Neo4j en esta etapa, pero sí se planifica su uso. Por ejemplo, conviene pensar en cómo se vectorizarán luego las transcripciones para cargas en Qdrant (búsqueda semántica) o cómo se podrían modelar conceptos en un grafo de Neo4j. Documentar notas reflexivas sobre posibles incoherencias o dudas de la transcripción también prepara el camino conceptual para el análisis posterior.

Configuración del análisis: Se definen las unidades de análisis (p.ej., fragmentos de texto que luego podrían codificarse) y la metadata relevante (fecha de entrevista, rol del entrevistado, etc.). Estos metadatos podrán almacenarse como columnas en PostgreSQL y también asociarse como payload JSON a cada vector en Qdrant más adelante
oracle.com
, facilitando filtrados por atributo durante búsquedas vectoriales. Conceptualmente, esta planificación asegura que desde el inicio consideremos cómo las herramientas técnicas encajarán en el flujo metodológico.; b) Revisión critica y adaptación desde a) la Etapa 0 – Preparación, reflexividad y configuración

Valor del informe. Correcto al usar PostgreSQL como repositorio confiable y ACID para textos y metadatos (entrevista, rol, fecha), y al planificar de antemano cómo se vectorizará y graficará.
Ajustes metodológicos. Añade un diccionario de datos (definiciones operacionales de unidad de análisis, código, categoría axial, criterios de inclusión/exclusión) y un diario de reflexividad versionado (git/LFS) para capturar supuestos y decisiones.
Alineación técnica.

PostgreSQL: usa DOUBLE PRECISION[] para embeddings (vectores numéricos de 3072 si text-embedding-3-large) y columnas normalizadas para area_tematica, actor_principal, requiere_protocolo_lluvia, created_at/updated_at. Arrays están bien soportados y no exigen tamaño prefijado. 
PostgreSQL

Qdrant: define payload canónico (campos y tipos) y plan de índices de payload (keyword / full‑text) para acelerar filtros semánticos‑por‑atributo. 
api.qdrant.tech
+1

Neo4j: crea constraints de unicidad para (:Entrevista{nombre}) y (:Fragmento{id}) como base de integridad relacional. 
Graph Database & Analytics; c) Sprint: Sprint 0 — Endurecimiento y gobernanza de datos

Objetivo: seguridad, configuraciones, reproducibilidad.

Entregables:

.env completo; rotación de todas las claves expuestas; verificación endpoint Azure *.openai.azure.com;

DDL ampliado en PG: entrevista_fragmentos con id, archivo, par_idx, fragmento, embedding DOUBLE PRECISION[], char_len, sha256, area_tematica, actor_principal, requiere_protocolo_lluvia, created_at, updated_at; índices por area_tematica, actor_principal, created_at;

Constraints Neo4j (Entrevista.nombre y Fragmento.id únicos);

Payload schema Qdrant + creación de payload indexes (keyword/full‑text).

DoD: healthchecks verdes (PG/Neo4j/Qdrant/Azure), colección Qdrant con size=EMBED_DIMS, Query API operativa con filtro por payload. 
api.qdrant.tech
+2
Graph Database & Analytics
+2

Riesgos: drift de dimensiones → validar len(embedding)==EMBED_DIMS en ingestión.

 Pendiente: Siguientes Pasos                                                                    
                                                                                      
  1. Completar un archivo JSON de metadatos y ejecutar python main.py --env .env      
     ingest … --meta-json … para poblar los nuevos campos.                            
  2. Lanzar python -m scripts.healthcheck --env .env y revisar docs/reflexividad.md   
     para registrar los resultados y ajustes operativos. 


# Reflexión: Etapa 1 – Transcripción y Resumen

PostgreSQL (literalidad y resumen): Tras transcribir las entrevistas verbatim, PostgreSQL permite verificar y corregir la literalidad almacenando texto original junto a su resumen en una tabla. Podemos consultar rápida y textualmente las transcripciones para detectar errores de transcripción o incoherencias, gracias a la potencia de SQL para búsquedas exactas o filtrado por entrevistado/fecha. La capacidad ACID de PostgreSQL garantiza que cualquier corrección quede registrada confiablemente
postgresql.org
. Conceptualmente, en esta etapa predomina el trabajo humano (asegurar que el texto refleja fielmente lo dicho), con la tecnología respaldando la calidad de datos.

Qdrant (preparación semántica): Aunque el resumen lo elabora el investigador, Qdrant puede comenzar a aportar en segundo plano. Por ejemplo, se pueden generar embeddings vectoriales de cada párrafo de las transcripciones y cargarlos en Qdrant. Esto no impacta inmediatamente el resumen, pero prepara el terreno para búsquedas semánticas posteriores
qdrant.tech
. También podría ayudar a verificar la coherencia: si cierto fragmento aparece repetido o muy similar en varias entrevistas, una búsqueda por similitud en Qdrant lo revelará aunque se usen sinónimos o expresiones distintas (algo difícil de detectar con solo lectura manual). En resumen, técnicamente Qdrant empieza a armar un índice semántico del corpus, aunque conceptualmente en Etapa 1 el análisis sigue siendo un resumen narrativo básico.

Neo4j: En esta fase temprana Neo4j no juega un rol activo, ya que aún no existen “códigos” ni relaciones conceptuales definidas para mapear. No obstante, desde la perspectiva reflexiva, el analista puede ir imaginando posibles conexiones entre ideas que surgen en los resúmenes. Estas intuiciones luego podrán representarse fácilmente como nodos y relaciones en un grafo. Por ejemplo, si en varios resúmenes iniciales se menciona “falta de participación” junto a “problemas urbanísticos”, uno podría anotar esa posible relación, anticipando que Neo4j ayudará a explorarla formalmente en las etapas de codificación axial o el modelo explicativo.; b) Etapa 1 – Transcripción y resumen

Valor del informe. Correcto: verificación de literalidad y resúmenes breves respaldados por SQL.
Ajustes metodológicos. Integra una lista de verificación de coherencia (marcas dudosas, muletillas, segmentos inaudibles).
Alineación técnica.

Genera embeddings en lote y carga temprana a Qdrant: esto habilita chequeos de duplicidad y similitud no obvia (sinónimos). Usa la Query API unificada query_points (en lugar de endpoints deprecados) para búsquedas y hybrid/multi‑stage queries. 
api.qdrant.tech
+2
qdrant.tech; c) Sprint 1 — Ingesta DOCX → fragmentos → embeddings → 3 almacenes (Etapas 0–1)

Objetivo: pipeline reproducible con coalescing y control de calidad.

Entregables: orquestador que: (i) lee DOCX, (ii) coalesce 200–1200 chars, (iii) genera embeddings (batch), (iv) upsert Qdrant (payload completo + índices), (v) MERGE Neo4j, (vi) UPSERT PG, (vii) run_id y logs.

DoD: >99% fragmentos con sha256, char_len>0, dims==EMBED_DIMS; query_points retorna top‑K con filtros. 
api.qdrant.tech

Riesgos: timeouts → retry/backoff + lotes pequeños.


# Reflexión Etapa 2 – a)Análisis Descriptivo Inicial

Análisis superficial y PostgreSQL: En esta etapa se revisan las transcripciones para extraer primeras impresiones y temas superficiales. PostgreSQL permite consultas simples para conteos de palabras clave o filtrados – por ejemplo, ¿cuántas entrevistas mencionan “espacio público” o “organización vecinal”? Estas consultas cuantitativas rápidas complementan la lectura cualitativa, dando pistas de frecuencia o distribución de temas. Técnicamente, la base de datos relacional actúa como herramienta de overview, ayudando a justificar por qué ciertos códigos iniciales son relevantes (p. ej., un término recurrente en muchos documentos).

Qdrant (búsqueda semántica inicial): Más allá de conteos literales, Qdrant añade una capa semántica al análisis inicial. Con los embeddings ya cargados, el investigador puede hacer búsquedas por similitud para agrupar fragmentos que, aunque no compartan las mismas palabras, tratan de un tema parecido
qdrant.tech
. Por ejemplo, al intuir un tema superficial como “conflicto vecinal”, se podría tomar un fragmento ilustrativo y pedir a Qdrant los Top-K fragmentos más similares en el resto del corpus. Esto podría destapar otras secciones de texto que reflejan el mismo tema aunque usen vocabulario distinto (sin depender de un keyword exacto)
qdrant.tech
. Conceptualmente, esto enriquece el análisis descriptivo porque asegura que las convergencias temáticas iniciales no se limiten a palabras textuales sino a significados subyacentes. Qdrant actúa entonces como un “buscador de patrones” implícitos en el discurso, apoyando al analista en justificar códigos iniciales basados en agrupaciones semánticas, no solo literales.

Neo4j (registro incipiente de conexiones): Aún estamos en un nivel descriptivo y no en la formalización de relaciones, pero si ya se identifican códigos iniciales (etiquetas para ideas recurrentes), se podría opcionalmente comenzar a modelarlos. Por ejemplo, crear un nodo para cada código inicial e ir conectando manualmente entrevistas o fragmentos a esos nodos en Neo4j. Esto equivale a una matriz de código en formato grafo: cada fragmento (nodo de tipo Fragmento) “tiene” un código (relación :TIENE_CODIGO hacia un nodo Codigo). Aunque este registro podría llevarse también en tablas relacionales, usar Neo4j desde temprano tiene un papel conceptual: visualizar un grafo simple de qué entrevistas están asociadas a cuáles códigos puede revelar patrones (p. ej., tal código solo aparece en entrevistas de mujeres, o estos dos códigos siempre coaparecen en los mismos casos). Esta mirada relacional preliminar prepara la mente del investigador para la siguiente fase de codificación abierta; b) Etapa 2 – Análisis descriptivo inicial

Valor del informe. Adecuado: conteos y filtros en SQL + agrupación semántica inicial con Qdrant.
Ajustes metodológicos. Acompaña las “primeras impresiones” con evidencia negativa (qué no aparece) y registra criterios de saturación preliminares.
Alineación técnica.

Qdrant: consolida consultas semánticas con filtros de payload (p. ej., subgrupo/época) y configura full‑text index si necesitas filtrar por términos exactos además de similitud vectorial. 
qdrant.tech; c: Sprint 2 — Matrices de codificación abierta (Etapa 3)

Objetivo: matriz código–cita y apoyo semántico.

Entregables:

Tabla analisis_codigos_abiertos en PG;

Flujo semi‑asistido: al asignar un código semilla, Qdrant sugiere candidatos similares no codificados;

Grafo bipartito en Neo4j Fragmento–Codigo.

DoD: recuperar en <2s todas las citas por código; sugerencias semánticas restringibles por payload; payload index activo. 
api.qdrant.tech
ok

# Reflexión Etapa 3 – a) Etapa 3 – Codificación Abierta

PostgreSQL (tabla de códigos abiertos): En la codificación abierta se asignan etiquetas (códigos) a fragmentos de datos de manera extensa y line-by-line. PostgreSQL resulta muy práctico aquí para gestionar la matriz código-citas clásica: podemos tener una tabla donde cada fila sea un fragmento codificado, con columnas como id_entrevista, texto_fragmento, codigo_asignado, etc. Consultas SQL permiten, por ejemplo, obtener rápidamente todas las citas etiquetadas con cierto código o contar cuántos fragmentos tiene cada código (facilitando la posterior depuración de códigos redundantes o poco sustentados). Este almacenamiento estructurado asegura trazabilidad: cada código abierto queda respaldado por varias ocurrencias localizables
postgresql.org
. Conceptualmente, Postgres aquí da soporte técnico a la apertura del análisis, evitando caos en la gestión de decenas de códigos y cientos de segmentos.

Qdrant (asistencia a la codificación): La etapa de codificación abierta puede volverse abrumadora; Qdrant funciona como un asistente semántico para el investigador. Por ejemplo, al definir un nuevo código, es posible inmediatamente buscar en Qdrant otros fragmentos similares para ver si también deberían llevar ese código. Esto significa que en cuanto se codifica un fragmento representativo de “falta de alumbrado público”, se le puede preguntar a Qdrant “¿qué otros fragmentos se parecen a este semanticamente?” y obtener candidatos a codificar igual, aunque no contengan literalmente “alumbrado” pero tal vez “luz” o “oscuridad en las calles”. De este modo, Qdrant expande la cobertura del código de forma sistemática
oracle.com
. Técnicamente, esto es posible porque cada punto (fragmento) en Qdrant puede llevar un payload indicando si ya fue codificado y con qué etiqueta; se pueden filtrar búsquedas para encontrar similares entre los no codificados aún
oracle.com
. En resumen, Qdrant agiliza y uniformiza la codificación abierta, reduciendo sesgos de memoria del analista y asegurando que segmentos conceptualmente equivalentes reciban un tratamiento similar.

Neo4j (códigos como nodos): A medida que los códigos abiertos proliferan, Neo4j puede emplearse para organizar la codificación abierta en red. Cada código se modela como un nodo (tipo Codigo), y cada fragmento (nodo Fragmento o Cita) se conecta a su(s) código(s) mediante relaciones :ETIQUETADO_CON. Esto genera un grafo bipartito básico fragmento-código. La utilidad de hacerlo en Neo4j radica en que podemos explorar las conexiones entre códigos de manera emergente: dos códigos que comparten muchos fragmentos tendrán varios nodos de fragmento apuntando a ambos, lo que en un grafo equivale a que están cercanos (posiblemente un indicio de solapamiento o relación). Un analista podría ejecutar una consulta Cypher para encontrar pares de códigos que coaparecen en el mismo fragmento o en la misma entrevista, revelando agrupaciones tempranas. Aunque esto también podría calcularse con JOINs en SQL, la representación gráfica directa de “códigos conectados por co-ocurrencia” es más intuitiva en Neo4j. En otras palabras, en la codificación abierta Neo4j proporciona un mapa visual de cómo las etiquetas se distribuyen y empiezan a relacionarse en la práctica, alimentando reflexiones para la siguiente etapa; b) Etapa 3 – Codificación abierta

Valor del informe. Muy sólido: PostgreSQL como matriz código–cita, Qdrant para propagación semántica de códigos (encontrar candidatos similares).
Ajustes metodológicos. Documenta criterios de asignación por código (definición, inclusiones, exclusiones, ejemplos limítrofes) y agrega confianza del codificador (1–3).
Alineación técnica.

PG: tabla analisis_codigos_abiertos con FK a entrevista_fragmentos.

Qdrant: usa payload codigos_ancla y filtros para “no codificados aún”. Crea payload index keyword en area_tematica, actor_principal, codigos_ancla para filtros eficientes. 
api.qdrant.tech

Neo4j: modela grafo bipartito (:Fragmento)-[:ETIQUETADO_CON]->(:Codigo); prepara queries de co‑ocurrencia para detectar solapamientos. ; c) Sprint 2 — Matrices de codificación abierta (Etapa 3)

Objetivo: matriz código–cita y apoyo semántico.

Entregables:

Tabla analisis_codigos_abiertos en PG;

Flujo semi‑asistido: al asignar un código semilla, Qdrant sugiere candidatos similares no codificados;

Grafo bipartito en Neo4j Fragmento–Codigo.

DoD: recuperar en <2s todas las citas por código; sugerencias semánticas restringibles por payload; payload index activo. 
api.qdrant.tech


# Reflexión Etapa 4 – a) Etapa 4 – Codificación Axial

Neo4j (relacionando categorías y subcategorías): La codificación axial implica reanudar los datos conectando códigos en categorías más amplias y estableciendo relaciones (causa-efecto, parte-todo, contexto-condición, etc.). Aquí Neo4j brilla conceptualmente y técnicamente: es una base de datos diseñada precisamente para almacenar relaciones explícitas entre entidades
neo4j.com
. Cada categoría axial identificada puede ser un nodo (Categoria), y las relaciones axiales que el investigador propone (p. ej. “contribuye a”, “es un tipo de”, “contrasta con”) se registran como aristas nombradas entre códigos o entre códigos y categorías. A diferencia de una base relacional que requeriría complejos JOINs para cruzar tablas, Neo4j permite navegar estas conexiones de forma natural y rápida, ya que almacena adyacencias directamente junto a los nodos
neo4j.com
. Por ejemplo, si “Falta de iluminación” y “Percepción de inseguridad” se determinó que están vinculados, en Neo4j simplemente se crea (FaltaIlum)-[:CAUSA]->(InseguridadPercibida) y esa relación es un ciudadano de primera clase en la BD. Esta representación de la estructura temática en un grafo facilita consultas como “mostrar todas las consecuencias de X” o “qué factores rodean al problema Y”, alineándose perfectamente con el objetivo axial de explorar interrelaciones profundas entre conceptos.

Memos y notas: Durante la axial, el investigador escribe muchas notas teóricas o memos sobre por qué ciertos códigos se agrupan o cómo se relacionan. Neo4j admite propiedades en nodos y relaciones, de modo que se podría adjuntar el texto de un memo directamente a la relación correspondiente (por ejemplo, la arista CAUSA mencionada podría tener una propiedad explicacion="los vecinos asocian calles oscuras con más delitos"). Esto integra las reflexiones cualitativas dentro de la estructura de datos, manteniendo el contexto conceptual accesible mientras se consulta el grafo.

Qdrant (verificación empírica de relaciones): Si bien las relaciones axiales se basan en la interpretación del investigador, Qdrant puede servir para triangular empíricamente esas conexiones. Supongamos que se propone la categoría axial “Desconfianza en autoridades” que agrupa códigos abiertos como “promesas incumplidas” y “falta de participación ciudadana”. Con Qdrant se podría buscar si fragmentos vinculados a estos códigos comparten vectorialmente similitud, lo cual reforzaría que efectivamente aparecen en contextos semánticos parecidos (indicando coherencia de la categoría). Además, gracias al payload podemos filtrar: “dame ejemplos vectorialmente cercanos a este fragmento que estén codificados con diferentes códigos abiertos”, para descubrir si quizás dos códigos que pensábamos distintos en realidad siempre aparecen juntos y podrían unificarse en una sola categoría. En resumen, Qdrant actúa como comprobador semántico: ayuda a validar que las agrupaciones axiales propuestas tienen sentido en los datos brutos, no solo en la cabeza del investigador
oracle.com
.

PostgreSQL (integración con datos originales): Aunque Neo4j lleve la batuta en lo axial, PostgreSQL sigue aportando en cuanto a acceso a datos originales. Por ejemplo, una vez definidas categorías y relaciones, podríamos querer listar todas las citas que caen bajo cierta categoría axial para revisar la consistencia. Una consulta SQL puede unir la tabla de fragmentos con la de códigos y categorías para obtener ese listado. Esto garantiza que, pese a elevar el nivel de abstracción en lo axial, cada categoría sigue anclada a evidencia concreta recuperable al instante. La solidez transaccional de PostgreSQL asegura además que cualquier reorganización (p. ej., si movemos un código a otra categoría) pueda actualizarse en lote con consistencia.
; b) Etapa 4 – Codificación axial

Valor del informe. Excelente: Neo4j es el soporte natural para relaciones causa/condición/medio/resultado.
Ajustes metodológicos. Cada relación axial debe portar evidencia: añade propiedad evidencia=[ids_fragmento] y un memo justificatorio en la arista.
Alineación técnica.

Neo4j GDS: aplica Louvain (agrupación por comunidades) y PageRank/betweenness (centralidad/puentes) sobre un grafo de códigos y categorías para priorizar revisión, no para decidir teoría (human‑in‑the‑loop). 
Graph Database & Analytics
+1; c) Sprint 3 — Axial con evidencia (Etapa 4)

Objetivo: categorías axiales y relaciones con memo y evidencia.

Entregables:

Esquema de grafo (:Categoria)-[:REL]->(:Codigo) con relacion.tipo ∈ {causa, condición, consecuencia, parte‑de};

Propiedades en aristas: evidencia:[ids_fragmento], memo:texto;

Pipelines GDS (Louvain, PageRank, betweenness) para priorizar revisión.

DoD: cada relación axial tiene ≥2 citas únicas en evidencia; resultados GDS reproducibles (notebook + parámetros). 
Graph Database & Analytics;

Verificación Recomendada                                                                                        
                                                                                                                  
  1. Ejecuta python -m scripts.healthcheck --env .env.                                                            
  2. Usa main.py --env .env coding assign … para codificar fragmentos (asegúrate de tener ≥2 evidencias) y luego  
     main.py --env .env axial relate … para registrar la relación.                                                
  3. Opcional: python main.py --env .env axial gds --algorithm louvain o python -m scripts.gds_analysis --env .env
     --algorithm pagerank para revisar comunidades/centralidades y registrar hallazgos en docs/reflexividad.md. 

# reflexión Etapa 5 – a) Etapa 5 – Modelo Explicativo: Etapa 5 – Codificación Selectiva

Identificación del núcleo (Neo4j): En la codificación selectiva se busca el tema central que integra la teoría emergente. Habiendo modelado un grafo de códigos y categorías, es natural pensar que el núcleo temático será aquel nodo altamente conectado o que actúa como eje en el grafo. Neo4j permite detectar esto tanto visualmente como mediante algoritmos: por ejemplo, aplicando medidas de centralidad o simplemente observando qué nodo categoría tiene mayor número de relaciones entrantes/salientes. Debido a que las relaciones fueron almacenadas nativamente, dichas consultas son eficientes incluso en un grafo grande
neo4j.com
neo4j.com
. Si, por decir, “Participación Ciudadana” resulta estar vinculada con la mayoría de los otros conceptos (problemas urbanos, instituciones, resultados históricos), Neo4j lo mostrará claramente, respaldando la decisión de seleccionarla como la categoría central de la teoría. Conceptualmente, la herramienta aquí cumple un rol confirmatorio: lo que el análisis interpretativo sugiere como núcleo, el grafo lo refleja estructuralmente.

Qdrant (cobertura del núcleo): Una vez propuesto el núcleo temático integrador, Qdrant puede ayudar a verificar que esté suficientemente sustentado en los datos. El investigador puede tomar la definición del núcleo (p.ej., una descripción en lenguaje natural de esa categoría central) y usar Qdrant para buscar en todas las entrevistas fragmentos semánticamente relacionados. Si el núcleo realmente permea el corpus, Qdrant devolverá coincidencias de múltiples entrevistas, evidenciando su omnipresencia. Si en cambio apenas aparecen resultados, podría ser señal de que el núcleo no está tan “grounded” en los datos y tal vez se requiera revisar su formulación. Además, Qdrant asegura que se capturen las distintas formas de expresar el núcleo: por ejemplo, si el núcleo es “Sentido de comunidad”, la gente podría expresarlo de formas variadas; la búsqueda vectorial recuperará frases equivalentes (como “sentimiento de pertenencia al barrio” o “solidaridad entre vecinos”) que confirman que la idea subyacente está en los datos aunque con distintas palabras. Esto da confianza de saturación del núcleo en la teoría.

PostgreSQL (frecuencias y distribución): En paralelo, se puede usar PostgreSQL para análisis cuantitativos sencillos que apoyen la selección del núcleo. Por ejemplo, una consulta que cuente en cuántas entrevistas aparece cada categoría axial puede mostrar que justamente la categoría candidata a núcleo está presente en el 100% de las entrevistas, mientras que otras categorías importantes quizá solo en el 60%. Si bien la teoría fundamentada no se basa en frecuencia bruta, este tipo de información cuantitativa aportada por SQL puede respaldar con números la centralidad de un concepto.; b) Etapa 5 – Codificación selectiva

Valor del informe. Muy buena articulación entre elección del núcleo y respaldo empírico.
Ajustes metodológicos. Exige triangulación cruzada: 1) centralidad en Neo4j; 2) cobertura semántica en Qdrant por múltiples entrevistas; 3) distribución en PG (presencia por caso/rol/tiempo).
Alineación técnica.

Neo4j: identifica candidatos a núcleo por centralidad y densidad de vínculos.

Qdrant: prompt‑probes para el núcleo (“sentido de comunidad” → recupera pasajes variados semánticamente).

PG: reportes de cobertura (porcentaje de entrevistas donde aparece). ; c) Sprint 4 — Selectiva y núcleo (Etapa 5)

Objetivo: identificar y validar el fenómeno central.

Entregables:

Reporte de centralidad/cobertura del núcleo (Neo4j+PG);

Probe queries en Qdrant para “extender” cobertura del núcleo con citas variadas (≥3 entrevistas diferentes).

DoD: núcleo con (i) centralidad alta, (ii) presencia transversal, (iii) ≥5 citas icónicas.

Herramienta CLI: `python main.py nucleus report --categoria "Participación Ciudadana" --prompt "sentido de comunidad como eje articulador"`
- Ejecuta PageRank/betweenness/louvain en Neo4j y devuelve el ranking con el `rank` del candidato.
- Calcula cobertura en PostgreSQL (entrevistas, roles, áreas y conteo de citas) y verifica umbrales (`min_interviews`, `min_roles`, `min_quotes`).
- Lanza probes semánticas en Qdrant y comprueba presencia en ≥3 entrevistas distintas. El JSON final expone `checks` y `done` para documentar el DoD.

#   Next                                                                        
                                                                              
  1. Install project deps (pip install -r requirements.txt or equivalent)     
     and run python3 main.py nucleus report --categoria ... --prompt ... to   
     generate the JSON report.                                                
  2. Optional: clean up the indentation glitch in app/axial.py so compileall  
     can pass and catch future syntax regressions.   

# Reflexión Etapa 6 – Análisis Temático Transversal

Comparativas en PostgreSQL: Con las categorías definidas, es útil comparar su aparición o manifestación según atributos como rol de entrevistado, género, o momento temporal (p. ej., entrevistas de 2010 vs 2020). PostgreSQL es ideal para estas comparativas transversales: mediante consultas con GROUP BY o filtros podemos obtener, por ejemplo, una tabla cruzada de categorías por género (¿qué categorías mencionan más las mujeres que los hombres?), o listar qué códigos emergieron en entrevistas de líderes comunitarios versus ciudadanos de a pie. Estas salidas tabulares ofrecen evidencia de convergencias y divergencias: quizá todos los grupos mencionan el problema X (convergencia), pero solo los jóvenes mencionan el tema Y (divergencia). Técnicamente, la base relacional facilita el análisis multivariable de la información codificada que sustenta las afirmaciones sobre variaciones por rol/género/tiempo.

Qdrant (búsquedas filtradas por subconjunto): Más allá de conteos, podemos explorar diferencias cualitativas en cómo se habla de un tema entre subgrupos, utilizando Qdrant con filtros. Dado que Qdrant permite adjuntar metadatos a cada vector (por ejemplo, indicando el grupo demográfico o la época de cada fragmento)
oracle.com
, podemos hacer búsquedas semánticas dentro de subconjuntos específicos. Por ejemplo: buscar los fragmentos más similares a “falta de áreas verdes” pero solo entre entrevistas de mujeres, y luego repetir la búsqueda solo entre entrevistas de hombres, para ver si los contextos difieren. Quizá para mujeres ese concepto se asocia más a seguridad (p. ej. parques oscuros), mientras que para hombres se asocia a recreación deportiva – diferencias sutiles que Qdrant podría revelar al comparar los resultados semánticos por filtro. Igualmente, podríamos filtrar por época: ¿cómo describían “participación ciudadana” los entrevistados en los años 90 vs en los 2020? Si el lenguaje o el énfasis cambió, una búsqueda vectorial segmentada lo destacará. En suma, Qdrant aporta una lente semántica fina para ver variaciones contextuales de los temas a través de distintos grupos o tiempos, complementando la visión general obtenida con SQL.

Neo4j (subgrafos por grupo): Neo4j permite efectuar cortes del grafo para cada subgrupo y comparar su estructura. Por ejemplo, si en el modelo de datos cada entrevista tiene un atributo de tipo de actor (vecino, autoridad, etc.) o género, se puede escribir una consulta que genere el subgrafo de categorías y relaciones fundamentadas solo por entrevistas de mujeres, y otro solo por entrevistas de hombres. Visualizando ambos, podríamos notar que tal conexión conceptual existe en ambos (convergencia), mientras que cierta relación (p. ej., “Conflicto con autoridades” -> “Acción colectiva”) aparece fuertemente en el subgrafo de líderes vecinales pero es débil o ausente en el de otros vecinos (divergencia). Esta comparación gráfica es una forma potente de análisis transversal: resalta no solo qué categorías aparecen, sino cómo se conectan de manera distinta según el contexto. Neo4j maneja eficientemente estas consultas de patrones gracias a su modelo flexible; a diferencia de cruzar múltiples tablas por cada segmento de datos, aquí simplemente consultamos la existencia de caminos en el grafo segmentado
neo4j.com
. Conceptualmente, esto apoya la narrativa de convergencias/divergencias con un mapeo visual e intuitivo de las diferencias relacionales entre subgrupos.

Integración de hallazgos: Al final de esta etapa transversal, las tres herramientas se complementan: Postgres entrega estadísticas y distribución de códigos por grupo, Qdrant aporta matices semánticos en el discurso de cada grupo, y Neo4j muestra estructuras relacionales diferenciadas. Juntas pintan un cuadro robusto de cómo varían (o se mantienen) los temas a lo largo de distintas dimensiones, reforzando la credibilidad de las conclusiones; b) Etapa 6 – Análisis temático transversal

Valor del informe. Muy completo: cortes por rol/género/época, subgrafos en Neo4j, segmentación por filtros en Qdrant, cross‑tabs en PG.
Ajustes metodológicos. Añade análisis de divergencias conceptuales (misma palabra, distinto uso) apoyado por resultados semánticos con filtros de subconjuntos.
Alineación técnica.

Qdrant: filtros de payload + query_points para comparar resultados entre subgrupos. 
api.qdrant.tech

Neo4j: genera subgrafos por grupo para comparar patrones y rutas diferenciales.; c) Sprint 5 — Transversalidad (Etapa 6)

Objetivo: convergencias/divergencias por grupo/tiempo.

Entregables:

Vistas/materialized views en PG (por rol/género/época);

Subgrafos comparativos (Neo4j) y consultas por grupo;

Búsquedas semánticas segmentadas (Qdrant) por filtros.

DoD: dashboard con 3 vistas: cross‑tab PG, subgrafo Neo4j y top‑K Qdrant filtrado por subgrupo; latencia <3s por vista. 
api.qdrant.tech.

CLI de soporte:
- `python main.py transversal pg --dimension genero --categoria "Participación Ciudadana" --refresh` refresca y devuelve la vista materializada (`mv_categoria_por_genero`).
- `python main.py transversal qdrant --prompt "falta de áreas verdes" --segment "Mujeres|genero=F" --segment "Hombres|genero=M"` compara segmentos vectoriales.
- `python main.py transversal neo4j --attribute genero --values F M` resume subgrafos por atributo.
- `python main.py transversal dashboard --prompt "participación ciudadana" --attribute genero --values F M --segment "Mujeres|genero=F" --segment "Hombres|genero=M" --dimension genero` genera el payload integrado (verifica SLA <3s por vista).

# Reflexión Etapa 7 – Modelo Explicativo

Neo4j (mapa conceptual): El modelo explicativo es la teoría final integrada, a menudo expresada como un diagrama conceptual que enlaza problemas, categorías centrales, condiciones y consecuencias. Dado que en Neo4j ya tenemos representados los conceptos (nodos) y sus relaciones, básicamente el grafo es el modelo teórico. Podemos extraer de Neo4j un subgrafo simplificado que contenga solo los nodos principales (p. ej., “Problemas Urbanos”, “Participación Ciudadana”, “Transformación Histórica”, junto con las conexiones entre ellos descubiertas). Este subgrafo puede traducirse fácilmente en un diagrama ASCII o un dibujo para el informe final. Por ejemplo, si el grafo muestra que Participación actúa como puente entre Problemas y Soluciones históricas, el diagrama ASCII podría reflejar:

[Problemas Urbanos] <-- influencia --> [Participación Ciudadana] <-- motor --> [Transformación Histórica]  
       ^________________ (agravados por falta de) ________________^  


Lo importante es que Neo4j garantiza que cualquier relación plasmada en el modelo está respaldada por datos (puesto que cada arista del grafo proviene de la codificación axial/selectiva basada en evidencias). A diferencia de dibujar el modelo “a mano alzada” desde memorias, aquí aprovechamos la estructura ya construida en Neo4j para asegurar coherencia interna: no se introducen relaciones arbitrarias, solo las que fueron identificadas y registradas durante el análisis. Además, Neo4j puede exportar visualizaciones directamente o integrarse con herramientas de graficación, reduciendo el esfuerzo de crear el mapa conceptual final.

Qdrant (ejemplos para el modelo): Aunque Qdrant no participa en el diagrama estructural, su contribución en esta etapa es proveer evidencias textuales ilustrativas para cada parte del modelo. Por ejemplo, para cada flecha o relación importante del modelo, podemos usar Qdrant para encontrar rápidamente una cita representativa donde ese vínculo se manifieste en los datos (gracias a la búsqueda semántica, no tenemos que recordar palabras exactas dichas, Qdrant nos las encuentra). Esto permite acompañar cada elemento del modelo con citas anónimas de los entrevistados que le den vida en el informe (“como dijo un participante: ‘...’), demostrando cómo de la base empírica surgió ese elemento teórico. Qdrant asegura que hallamos las mejores y más variadas citas para cada concepto, incluso si se formularon de maneras diversas en distintas entrevistas.

PostgreSQL (trazabilidad y consistencia): Antes de finalizar, es prudente usar PostgreSQL para una verificación final de trazabilidad: por ejemplo, listar todas las categorías y subcategorías con sus respectivas citas fuente, asegurando que no falte respaldo para algún componente del modelo. También puede emplearse para compilar tablas resumen (matrices) que se incluirán en anexos o en el cuerpo del informe final, como una matriz de códigos versus casos que muestre brevemente la densidad de cada código por entrevista (información que se extrajo fácilmente mediante SQL durante el análisis). Esto complementa el modelo conceptual con datos duros que al lector del informe le demuestren el alcance y profundidad del trabajo (cantidad de entrevistas, citas utilizadas, etc.). En esta etapa final, PostgreSQL actúa como garante de integridad: cualquier elemento del modelo explicativo puede rastrearse mediante una consulta hasta las palabras originales de los participantes.; B) Etapa 7 – Modelo explicativo

Valor del informe. Muy bueno al proponer el diagrama final a partir del grafo.
Ajustes metodológicos. Conservar trazabilidad invertible: de cada arista del diagrama al set de citas (fragment IDs) y a memos.
Alineación técnica.

Neo4j: el subgrafo final es el modelo; exporta para visualización.

Qdrant: búsqueda de citas icónicas por cada relación del diagrama.

PG: anexos tabulares (matrices y métricas) reproducibles.; c) Sprint 6 — Modelo explicativo (Etapa 7)

Objetivo: consolidar el diagrama (subgrafo) con citas “evidence‑at‑hand”.

Entregables:

Export del subgrafo final (Neo4j) + JSON con arista→[ids_fragmento];

Generación del diagrama ASCII y versión gráfica.

DoD: cada arista del diagrama enlaza a ≥2 citas; click‑through desde informe a evidencia.


 Next                                                                        
                                                                              
  1. Populate/verify ingest metadata (e.g., genero, periodo) so the new views 
     and filters return meaningful slices before running the transversal      
     commands.
  2. Refresh the materialized views and exercise python main.py transversal   
     dashboard … (or the report script) against a representative dataset to   
     confirm each pane stays under the 3 s DoD target.    

# Reflexión Etapa 8 – Verificación/Validación/Saturación

Saturación teórica (PostgreSQL & Qdrant): Para evaluar la saturación de la teoría, podemos aprovechar ambas facetas: cuantitativa y cualitativa. Por el lado de PostgreSQL, se puede generar un gráfico o reporte del número de códigos nuevos aparecidos a medida que avanzaban las entrevistas (usando una consulta acumulativa). Si las últimas entrevistas no aportaron códigos novedosos, eso cuantitativamente indica saturación. Desde lo cualitativo, una técnica interesante es usar Qdrant para detectar outliers: insertar los vectores de los últimos fragmentos/entrevistas y ver si aparecen muy distantes de los clusters existentes (lo que significaría ideas completamente nuevas) o si caen cerca de clusters ya formados (lo que sugiere que refuerzan lo ya conocido). Si prácticamente todos los fragmentos nuevos se ubican cerca de algún cluster temático existente en el espacio vectorial, podemos afirmar que el espacio conceptual está colmado (saturado) y nuevos datos sólo redundan en lo mismo. Esta comprobación semántica adiciona confianza en que no se dejó ningún fenómeno relevante sin descubrir.

Triangulación de datos (Neo4j & Qdrant): Si la investigación incluyó múltiples fuentes de datos (entrevistas, observaciones, documentos), estas herramientas ayudan a comprobar la consistencia entre fuentes. Por ejemplo, podríamos haber cargado también documentos de políticas urbanas en Qdrant; entonces podríamos buscar en ellos los mismos conceptos hallados en las entrevistas para ver si se reflejan. Qdrant, mediante búsquedas semánticas entre colecciones diferentes, revelaría correspondencias o discrepancias de lenguaje/contenido entre lo dicho por participantes y lo escrito en documentos oficiales. Neo4j, si se modelaron distintas fuentes en el grafo (p. ej., nodos Entrevista y nodos Documento vinculados a códigos comunes), permite consultar rápidamente ¿qué categorías emergen solo en las entrevistas ciudadanas y no tienen ningún vínculo con los documentos técnicos?, lo cual señalaría brechas de percepción dignas de mención. Esta triangulación asegurada por el grafo y el vector DB fortalece la validez del modelo: muestra que se contrastaron perspectivas y se identificaron tanto coincidencias como ausencias entre fuentes.

Member checking (PostgreSQL): La factibilidad de member checking (consulta a participantes sobre los hallazgos) se ve facilitada por tener los datos organizados. Con PostgreSQL, podríamos extraer un resumen por participante de lo que aportó a cada categoría (p. ej., “usted mencionó X, Y, Z, que se agrupan bajo el tema A”). Al tener cada cita ligada a entrevistado y código, es trivial compilar esta retroalimentación personalizada. Si se decide realizar sesiones de validación con algunos entrevistados, contar con la base de datos permite mostrar ejemplos anónimos de forma rápida para preguntar “¿refleja esto su experiencia?”. Además, gracias a la estructura establecida, cualquier ajuste sugerido por los participantes (por ejemplo, renombrar una categoría para que sea más fiel a su visión) se puede incorporar de regreso al sistema (actualizando nombres de nodos en Neo4j, por ejemplo) de forma consistente en todo el análisis. En resumen, la infraestructura de datos creada no solo sirvió al análisis interno sino que agiliza la validación externa, aumentando la credibilidad y transparencia del estudio.; b) Etapa 8 – Verificación, validación y saturación

Valor del informe. Muy sólido: mezcla verificación cuantitativa (PG) y cualitativa/semántica (Qdrant).
Ajustes metodológicos. Define umbrales explícitos (nuevos códigos por entrevista tendiendo a cero; outliers semánticos en Qdrant).
Alineación técnica.

Qdrant: outlier scan por distancia; si nuevos fragmentos caen en clústeres ya formados, es señal de saturación temática.

Neo4j: triangula fuentes (entrevistas/documentos) por vínculos a categorías.; c) Sprint 7 — Validación y saturación (Etapa 8)

Objetivo: demostrar saturación y triangulación.

Entregables:

Curva “nuevos códigos por entrevista” (PG);

Detección de outliers semánticos (Qdrant);

Diseño de member checking con paquetes por actor/tema.

DoD: saturación argumentada con (i) curva plana, (ii) ausencia de outliers sustantivos, (iii) paquete de validación listo. 

CLI de soporte:
- `python main.py validation curve --window 3 --threshold 0` calcula la curva acumulada de códigos y evalúa el plateau.
- `python main.py validation outliers --archivo "Entrevista_Final.docx" --limit 30 --threshold 0.8` contrasta los últimos fragmentos en Qdrant para detectar ideas disruptivas.
- `python main.py validation overlap --limit 20` resume la cobertura de categorías por fuente (`Entrevista` vs `Documento`) en Neo4j.
- `python main.py validation member --actor "dirigente vecinal" --limit 10` genera paquetes de member checking (códigos, categorías y citas relevantes).

# Next                                                                        
                                                                              
  - Load real data and run validation curve/outliers/overlap/member to confirm    plateau and outlier thresholds align with your analytic expectations      
    (adjust --threshold if cosine scores differ).                             
  - Populate metadata (e.g., participante, genero, periodo) before generating 
    member-checking packets so summaries reflect participants accurately.     
 
 

# Reflexión Etapa 9 – Hacia el Informe Final

Estructura del informe informada por las herramientas: La escritura del informe final se beneficia directamente de todo el trabajo apoyado por las tres herramientas. La estructura suele reflejar la jerarquía de categorías y el modelo explicativo (por ejemplo, secciones por cada categoría principal, subsecciones por subcategorías, seguidas del núcleo integrador y conclusiones). Dicha estructura prácticamente ya fue prototipada en Neo4j durante el análisis – es cuestión de traducir del grafo a secciones del texto.

Uso de citas variadas y anonimizadas: Gracias a PostgreSQL y Qdrant, disponemos de un amplio abanico de citas para escoger las más ilustrativas de cada hallazgo. Podemos consultar en PostgreSQL todas las citas bajo cierta categoría y luego utilizar Qdrant para ordenar o buscar aquellas que aporten matices diferentes (evitando repetitividad). Esto garantiza que en el informe final cada afirmación vaya acompañada de evidencias cualitativas ricas, con voz de distintos participantes (debidamente anonimizados). Por ejemplo, si la categoría es “Desconfianza en autoridades”, quizás incluiremos una cita de un vecino joven y otra de un vecino mayor, ambas relevantes – facilmente identificables mediante filtros por edad en las consultas. Las fuentes de cada cita están claramente registradas, lo que facilita anonimizarlas (sustituyendo identificadores por pseudónimos) sin riesgo de confusión.

Referencias a matrices y anexos: Si el informe requiere presentar matrices de datos (p. ej., un cuadro resumen de categorías por tipo de participante, o una tabla de frecuencia de códigos), estos resultados ya los habremos generado con PostgreSQL durante el análisis transversal. Simplemente se refinan y se incluyen como tablas o figuras, ahorrando tiempo y asegurando consistencia entre lo que se encontró analíticamente y lo que se reporta. La confiabilidad de PostgreSQL en manejar datos estructurados significa que podemos confiar en que esas tablas reflejan fielmente la base de datos analizada
postgresql.org
.

Limitaciones y recomendaciones: Al redactar limitaciones, podemos mencionar, por ejemplo, qué aspectos no fueron capturados en los datos – y aquí nuevamente Qdrant pudo ayudar a confirmar ausencias. Si Qdrant no encontró fragmentos relacionados a un tema que se esperaba (señalando un posible vacío en los datos), esto se consigna como limitación o área para investigar más. En cuanto a recomendaciones metodológicas, podríamos señalar la utilidad que tuvo combinar bases de datos tradicionales, de grafos y vectoriales en este estudio. Nuestra experiencia integrada demuestra cómo cada herramienta ocupó un rol complementario: Postgres garantizando orden y acceso rápido a datos textuales y numéricos, Neo4j facilitando la conceptualización de relaciones complejas, y Qdrant asegurando un análisis profundo de patrones de lenguaje y significado en el texto
qdrant.tech
neo4j.com
. Esta recomendación puede ser valiosa para futuros investigadores que busquen aprovechar tecnologías en investigación cualitativa.; b) Etapa 9 – Informe final

Valor del informe. Muy completo: estructura por categorías, citas variadas, limitaciones y recomendaciones.
Ajustes metodológicos. Añade “evidence‑at‑hand” en el reporte (cada afirmación con IDs de fragmento y enlaces internos de auditoría).
Alineación técnica.

PG: genera tablas y anexos reproducibles.

Neo4j/Qdrant: recuperación de citas y relaciones on‑demand para revisión por pares.; c) Sprint 8 — Informe final y empaquetado (Etapa 9)

Objetivo: redacción, anexos y reproducibilidad.

Entregables:

informe_integrado.md con enlaces a matrices (PG), subgrafo (Neo4j) y citas (Qdrant/PG);

Notebooks de export reproducibles con hash de versión de datos;

Resumen ejecutivo, limitaciones y recomendaciones operativas.

DoD: revisión por pares interna superada; artifact registry con versionado y checksums.

CLI de soporte:
- `python main.py report outline` exporta la jerarquía Categoria→Codigo desde Neo4j (base para la estructura del informe).
- `python main.py report build --output informes/informe_integrado.md --annex-dir informes/anexos --manifest informes/report_manifest.json` genera el informe, anexos (PG) y manifiesto con hashes y metadatos.

  Next                                                                        
                                                                              
  1. Run python main.py --env .env report build --output informes/            
     informe_integrado.md --annex-dir informes/anexos --manifest informes/    
     report_manifest.json on the latest dataset, then verify the annex hashes 
     stored in report_manifest.json.                                          
  2. Share informe_integrado.md with internal reviewers and iterate on        
     wording/structure; regenerate the report after adjustments so hashes stay
     in sync with the final submission.                                       
 



 ## Correcciones

 1) Hallazgos verificados (indicadores en verde)

Azure OpenAI embeddings OK: se confirman dims=3072 para text-embedding-3-large. Esto es un excelente “sanity check” de compatibilidad entre deployment y colección vectorial. 

app_anal_ent_Qdr_N4j (1)


Salida: 🟢 Azure OpenAI OK | deployment='text-embedding-3-large' | dims=3072

Qdrant “query_points” funcional (API unificada, resultados Top‑k): se observa búsqueda por vector con with_payload=True, y top‑2 esperado en healthcheck. 

app_anal_ent_Qdr_N4j (1)


Salida: query_points top-2: [(1, 0.994), (2, 0.11)]

PostgreSQL OK: conexión, creación de tabla temporal y DML básica funcionando (versión 17.6); codificación UTF‑8 fijada. 

app_anal_ent_Qdr_N4j (1)


Salida: Postgres version: 17.6 … 🟢 Postgres OK

Neo4j OK: RETURN 'pong', MERGE y DETACH DELETE funcionan correctamente (sesión con base ‘neo4j’). 

app_anal_ent_Qdr_N4j (1)


Salida: Ping Neo4j: pong … 🟢 Neo4j OK

IDs determinísticos (UUIDv5 en string) unificados para Qdrant / Neo4j / PG (clave para trazabilidad en RAG/QA). 

app_anal_ent_Qdr_N4j (1)


Ejemplo: make_fragment_id("synthetic.docx", 1) → "554f0d43-…-f111d"

Alias consistente del cliente Qdrant y helper de colección ensure_qdrant_collection(...) sin deprecaciones (bien). 

app_anal_ent_Qdr_N4j (1)

2) Riesgos y brechas (corregir ahora)

app_anal_ent_Qdr_N4j (1)


app_anal_ent_Qdr_N4j (1)

Bug menor en instalación: en Sprints.md hay un pip install con comilla sobrante:
!pip install openai>=1.52.2" → debe ser !pip install openai>=1.52.2. 

app_anal_ent_Qdr_N4j (1)

Uso puntual de método deprecado en Qdrant (recreate_collection) en un mini‑bloque de demo; ya te avisa DeprecationWarning. Sustituye por collection_exists + create_collection. (El resto del documento ya usa el enfoque correcto, pero hay que limpiar ese bloque). 

app_anal_ent_Qdr_N4j (1)

Esquema de PG aún minimalista en algunos bloques (id, archivo, fragmento, embedding): faltan par_idx, char_len, sha256, area_tematica, actor_principal, requiere_protocolo_lluvia, created_at, updated_at. Son columnas clave para auditoría, filtros, y series temporales. 

app_anal_ent_Qdr_N4j (1)

UPSERT en PG “DO NOTHING” (pierdes sincronización si hay cambios de texto/embedding). Cambia a ON CONFLICT (id) DO UPDATE SET …, updated_at=NOW(). 

app_anal_ent_Qdr_N4j (1)

Orden de definición/uso de interview_files: en un bloque, la lista se usa antes de definirse, pese a la nota de que “debe ir antes”. Ordena las celdas para evitar intermitencias. (En la ejecución real te salió OK, pero en un notebook distinto puede fallar). 

app_anal_ent_Qdr_N4j (1)

Falta “coalesce” de párrafos cortos (200–1200 chars): el orquestador actual ingesta cada párrafo “crudo”; esto suele degradar la señal semántica (chunks demasiado cortos). Añade coalesce_small(...). 

app_anal_ent_Qdr_N4j (1)

Payload Qdrant minimal: hoy solo envías {archivo, fragmento} en qdrant_upsert_batch (no guardas par_idx, char_len, area_tematica, actor_principal, requiere_protocolo_lluvia, codigos_ancla). Pierdes filtros y segmentación. Extiende payload e indiza area_tematica / actor_principal / codigos_ancla. 

app_anal_ent_Qdr_N4j (1)

Constraints de Neo4j ausentes en Sprints.md (aunque tus notebooks previos los tenían): añade CREATE CONSTRAINT para (:Entrevista{nombre}) y (:Fragmento{id}) en el documento base. 

app_anal_ent_Qdr_N4j (1)

3) Parches de código (copiar‑y‑pegar)

Los siguientes reemplazos/añadidos corrigen los puntos 1–10 y dejan Sprints.md coherente y reproducible.



app_anal_ent_Qdr_N4j (1)

3.2 Fix del comando pip
# Antes:
# !pip install openai>=1.52.2"
# Ahora:
!pip install "openai>=1.52.2"


app_anal_ent_Qdr_N4j (1)

3.3 Evitar deprecations en Qdrant
from qdrant_client.models import VectorParams, Distance

def ensure_qdrant_collection(client, name: str, dims: int, distance=Distance.COSINE):
    if client.collection_exists(name):
        info = client.get_collection(name)
        current = info.config.params.vectors.size
        if current != dims:
            raise RuntimeError(f"La colección '{name}' existe con size={current}; necesitas {dims}.")
        return False
    client.create_collection(name, vectors_config=VectorParams(size=dims, distance=distance))
    return True

# Elimina toda llamada a `recreate_collection(...)` en demos y tests.


app_anal_ent_Qdr_N4j (1)

3.4 DDL ampliado en PostgreSQL (auditoría + filtros + tiempo)
ALTER TABLE entrevista_fragmentos
  ADD COLUMN IF NOT EXISTS par_idx INT,
  ADD COLUMN IF NOT EXISTS char_len INT,
  ADD COLUMN IF NOT EXISTS sha256 TEXT,
  ADD COLUMN IF NOT EXISTS area_tematica TEXT,
  ADD COLUMN IF NOT EXISTS actor_principal TEXT,
  ADD COLUMN IF NOT EXISTS requiere_protocolo_lluvia BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS ix_ef_area   ON entrevista_fragmentos(area_tematica);
CREATE INDEX IF NOT EXISTS ix_ef_actor  ON entrevista_fragmentos(actor_principal);
CREATE INDEX IF NOT EXISTS ix_ef_created ON entrevista_fragmentos(created_at);


app_anal_ent_Qdr_N4j (1)

3.5 UPSERT correcto en PG (sin pérdida de sincronía)
from psycopg2.extras import execute_values

def pg_upsert_batch(pg_cursor, rows, table="entrevista_fragmentos"):
    """
    rows: list[tuple] -> (id, archivo, par_idx, fragmento, embedding, char_len, sha256,
                          area_tematica, actor_principal, requiere_protocolo_lluvia)
    """
    sql = f"""
      INSERT INTO {table}
        (id, archivo, par_idx, fragmento, embedding, char_len, sha256,
         area_tematica, actor_principal, requiere_protocolo_lluvia)
      VALUES %s
      ON CONFLICT (id) DO UPDATE SET
        archivo=EXCLUDED.archivo,
        par_idx=EXCLUDED.par_idx,
        fragmento=EXCLUDED.fragmento,
        embedding=EXCLUDED.embedding,
        char_len=EXCLUDED.char_len,
        sha256=EXCLUDED.sha256,
        area_tematica=EXCLUDED.area_tematica,
        actor_principal=EXCLUDED.actor_principal,
        requiere_protocolo_lluvia=EXCLUDED.requiere_protocolo_lluvia,
        updated_at=NOW();
    """
    execute_values(pg_cursor, sql, rows, page_size=200)


(Sustituye el bloque que hoy usa ON CONFLICT DO NOTHING.) 

app_anal_ent_Qdr_N4j (1)

3.6 Coalesce de párrafos + metadatos técnicos
import re, hashlib

def normalize_text(s: str) -> str:
    s = s.replace("\u00A0", " ")
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s

def coalesce_small(paragraphs, min_chars=200, max_chars=1200):
    acc, buf = [], ""
    for p in paragraphs:
        p = normalize_text(p)
        if not p: 
            continue
        if not buf:
            buf = p; continue
        if len(buf) < min_chars and len(buf) + 1 + len(p) <= max_chars:
            buf = f"{buf} {p}"
        else:
            acc.append(buf); buf = p
    if buf: acc.append(buf)
    return acc

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


app_anal_ent_Qdr_N4j (1)

3.7 Payload Qdrant enriquecido + índices de payload
from qdrant_client.models import PointStruct
from qdrant_client.http.models import PayloadSchemaType  # qdrant-client 1.15.x

# Crear índices de payload (una vez por campo)
def ensure_payload_indexes(client, collection):
    client.create_payload_index(collection_name=collection, field_name="area_tematica",
                                field_schema=PayloadSchemaType.KEYWORD)
    client.create_payload_index(collection_name=collection, field_name="actor_principal",
                                field_schema=PayloadSchemaType.KEYWORD)
    client.create_payload_index(collection_name=collection, field_name="codigos_ancla",
                                field_schema=PayloadSchemaType.KEYWORD)

def qdrant_upsert_batch(qc, collection, ids, triples, embeddings):
    """
    triples: list[(archivo, par_idx, frag, char_len, area_tematica, actor_principal, requiere_protocolo_lluvia, codigos_ancla:list)]
    """
    points = []
    for _id, (archivo, par_idx, frag, char_len, area, actor, lluvia, anclas), emb in zip(ids, triples, embeddings):
        points.append(PointStruct(
            id=str(_id),
            vector=emb,
            payload={
                "archivo": archivo,
                "par_idx": par_idx,
                "fragmento": frag,
                "char_len": char_len,
                "area_tematica": area,
                "actor_principal": actor,
                "requiere_protocolo_lluvia": bool(lluvia),
                "codigos_ancla": anclas or []
            }
        ))
    qc.upsert(collection_name=collection, points=points)

# En el arranque de la ingesta:
ensure_payload_indexes(qdrant_client, qdrant_collection)


(Reemplaza el payload minimal {archivo, fragmento} y habilita filtros por atributo.) 

app_anal_ent_Qdr_N4j (1)

3.8 Orquestador (fragmentos coalescidos + metadatos + UPSERT)
def ingest_files(files, batch_size=64):
    created = ensure_qdrant_collection(qdrant_client, qdrant_collection, EMBED_DIMS)
    ensure_payload_indexes(qdrant_client, qdrant_collection)
    total = 0

    for path in files:
        archivo = os.path.basename(path)
        raw_paras = extract_paragraphs(path)
        paras = coalesce_small(raw_paras)  # ← mejora de señal semántica
        if not paras:
            print(f"⚠️  {archivo}: sin texto útil"); continue

        ids, triples, texts = [], [], []
        for i, frag in enumerate(paras):
            pid = make_fragment_id(archivo, i)
            ids.append(pid)
            char_len = len(frag)
            # agrega tus reglas/etiquetado (si ya las tienes) o deja None/False/[]
            area, actor, lluvia, anclas = None, None, False, []
            triples.append((archivo, i, frag, char_len, area, actor, lluvia, anclas))
            texts.append(frag)

        # embeddings
        embeddings = []
        for chunk in batched(texts, batch_size):
            embeddings.extend(embed_batch(chunk))
        assert all(len(v)==EMBED_DIMS for v in embeddings), "Dims no coinciden"

        # Qdrant / Neo4j / PG
        qdrant_upsert_batch(qdrant_client, qdrant_collection, ids, triples, embeddings)

        neo_rows = [{"id": _id, "archivo": archivo, "fragmento": frag} 
                    for _id, (_, _, frag, *_rest) in zip(ids, triples)]
        neo4j_merge_batch(neo4j_driver, neo4j_database, neo_rows)

        pg_rows = [(_id, archivo, par_idx, frag, emb, char_len, sha256_text(frag), area, actor, lluvia)
                   for _id, (archivo, par_idx, frag, char_len, area, actor, lluvia, anclas), emb
                   in zip(ids, triples, embeddings)]
        pg_upsert_batch(pg_cursor, pg_rows)
        pg_conn.commit()

        total += len(paras)
        print(f"✔️  {archivo}: {len(paras)} fragmentos cargados")

    print(f"\n✅ Ingesta finalizada. Total fragmentos: {total}")


app_anal_ent_Qdr_N4j (1)

3.9 Constraints de Neo4j (añadir al documento base)
CREATE CONSTRAINT ent_unique IF NOT EXISTS FOR (e:Entrevista) REQUIRE e.nombre IS UNIQUE;
CREATE CONSTRAINT frag_unique IF NOT EXISTS FOR (f:Fragmento) REQUIRE f.id IS UNIQUE;


app_anal_ent_Qdr_N4j (1)

4) Gate de aceptación por sprint
Sprint	Objetivo	Estado	Evidencia / Observaciones
0	Seguridad y gobernanza	AT‑RISK	Claves expuestas y endpoint Azure inválido en fallback; aplicar 3.1 y rotar credenciales. 

app_anal_ent_Qdr_N4j (1)


1	Ingesta E2E	PASS (parcial)	Healthchecks OK y upserts funcionan; falta coalesce + metadatos completos + UPSERT en PG (3.4–3.8). 

app_anal_ent_Qdr_N4j (1)


2	Abierta (matriz)	AT‑RISK	Matriz en PG viable, pero ON CONFLICT DO NOTHING puede “congelar” filas; cambiar a DO UPDATE. 

app_anal_ent_Qdr_N4j (1)


3	Axial (relaciones)	AT‑RISK	Neo4j OK pero faltan constraints en Sprints.md y evidencia/memo en aristas (documentar). 

app_anal_ent_Qdr_N4j (1)


4	Selectiva	PASS	Insumos técnicos listos (Qdrant top‑K, Neo4j, PG); requiere solo disciplina analítica. 

app_anal_ent_Qdr_N4j (1)


5	Transversal	AT‑RISK	Sin payload enriquecido e índices, los filtros semánticos por subgrupo se limitan. Aplicar 3.7. 

app_anal_ent_Qdr_N4j (1)


6	Modelo explicativo	PASS (parcial)	Grafo listo; falta formalizar subgrafo final y enlaces a citas (IDs) en el doc. 

app_anal_ent_Qdr_N4j (1)


7	Validación / Saturación	AT‑RISK	Falta curva de “nuevos códigos por entrevista” y verificación de outliers en Qdrant; fácil de añadir. 

app_anal_ent_Qdr_N4j (1)


8	Informe final	PASS (parcial)	Generación de anexos en PG y citas vía Qdrant posible; vincular diagrama→citas. 

app_anal_ent_Qdr_N4j (1)

5) Verificación rápida post‑parche (3 checks)

Azure config (hard‑fail si endpoint no Azure): ejecutar el bloque 3.1 y comprobar que falla si el endpoint termina en cognitive.microsoft.com (corregir en .env y repetir). 

app_anal_ent_Qdr_N4j (1)

Qdrant filtros por payload: tras 3.7–3.8, correr una búsqueda semántica con filter={"must":[{"key":"area_tematica","match":{"value":"APS"}}]} y verificar top‑K semántico segmentado. 

app_anal_ent_Qdr_N4j (1)

UPSERT PG: re‑ingestar un archivo cambiando un fragmento; verifica que updated_at y sha256 cambian para ese id (no hay duplicados). 

app_anal_ent_Qdr_N4j (1)

Cierre

Tu Sprints.md está muy avanzado: validaste los 4 pilares (Azure/Qdrant/Neo4j/PG) y ya dejaste micro‑bloques de salud y orquestación. Con los parches mínimos anteriores:

garantizas seguridad y endpoint correcto,

ganas filtros semánticos realistas (payload/índices),

aseguras trazabilidad y sincronía (UPSERT/sha256/updated_at),

y mejoras calidad de chunking (coalesce).

Queda la base perfecta para las Etapas 3–7 (matrices, axial, selectiva y modelo) con evidencia enlazada (IDs → citas). Si te parece, puedo devolverte Sprints.md (v2.1) consolidado con estos diffs ya incorporados para que lo reemplaces 1:1. 

app_anal_ent_Qdr_N4j (1)



###
