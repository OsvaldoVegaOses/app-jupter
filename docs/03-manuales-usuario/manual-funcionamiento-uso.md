# Manual de funcionamiento y uso — APP_Jupter

**Fecha:** 2026-01-16

Este manual describe el funcionamiento operativo y el uso diario de la app. Está alineado con el código actual y la estructura de módulos (app/backend/frontend).

---

## 1) Objetivo del sistema

APP_Jupter es una plataforma de análisis cualitativo con GraphRAG que operacionaliza etapas de Teoría Fundamentada con soporte de:
- **Codificación abierta, axial y núcleo selectivo**.
- **Búsqueda semántica (Discovery)** y sugerencias de códigos.
- **Grafo de conocimiento** (Neo4j/Memgraph/NetworkX) y analítica GDS.
- **Persistencia multialmacén**: PostgreSQL, Qdrant, Neo4j y almacenamiento de archivos.

---

## 2) Perfiles y permisos

- **Admin:** administración de usuarios y salud del sistema, control total del proyecto.
- **Analyst:** operación principal del análisis (ingesta, codificación, discovery, reportes).
- **Viewer:** lectura de resultados y reportes.

**Multi-tenant:** los datos se segmentan por organización y proyecto. Las APIs verifican pertenencia y roles.

---

## 3) Flujo operativo recomendado

### 3.1 Crear proyecto
1. Iniciar sesión.
2. Crear proyecto desde la vista de proyectos.
3. El creador queda como **admin del proyecto**.

### 3.2 Ingesta de documentos
1. Subir archivos (DOCX/audio según módulos habilitados).
2. El sistema fragmenta, normaliza y almacena:
   - PostgreSQL (metadatos/fragmentos)
   - Qdrant (embeddings)
   - Neo4j (nodos/relaciones base)

### 3.2.1 Plantilla de formato para entrevistas (DOCX)

**Objetivo:** asegurar que el inicio real del diálogo sea reconocido y que el orden de segmentos se mantenga correcto.

**Reglas simples:**
- Una intervención por línea (párrafo).
- Prefijo de hablante obligatorio: `Entrevistador:` / `Entrevistada:` / `Entrevistado:` / `Moderador:`.
- Timestamps opcionales al inicio de línea (ej. `00:01:12 Entrevistador:`).
- Evitar títulos largos o metadatos mezclados con el diálogo.

**Sección de metadatos (opcional, antes del diálogo):**
- Mantenerla corta (máx. 3–5 líneas).
- Usar campos simples y evitar párrafos largos.

**Plantilla sugerida:**

**METADATOS**
- Entrevista: <nombre>
- Fecha: <YYYY-MM-DD>
- Lugar: <comuna/ciudad>
- Participantes: <roles>

**DIÁLOGO**
00:00:05 Entrevistador: <presentación breve>
00:00:12 Entrevistada: <respuesta>
00:00:20 Entrevistador: <pregunta>
00:00:30 Entrevistada: <respuesta>

**Notas de formato:**
- Si no hay timestamps, omitirlos completamente, pero mantener el prefijo.
- Evitar encabezados extensos tipo “Transcripción” o “Archivo de audio…” dentro del diálogo.
- Si hay cambio de hablante, siempre repetir el prefijo.
### 3.3 Codificación Abierta (Etapa 3)

La codificación abierta es el proceso de asignar códigos conceptuales a fragmentos de texto. El sistema ofrece múltiples herramientas para acelerar este proceso.

#### 3.3.1 Panel de Codificación Abierta

Accede desde el menú lateral: **Codificación** → **Abierta**

**Pestañas disponibles:**

| Pestaña | Función | Cuándo usar |
|---------|---------|-------------|
| 🧭 **Siguiente recomendado** | Flujo guiado: el sistema propone el siguiente fragmento | Codificación sistemática |
| 📝 **Asignar código** | Asignación manual con selección de fragmento | Control total del proceso |
| 🔍 **Sugerencias semánticas** | Encuentra fragmentos similares para comparación constante | Validar saturación |
| 📊 **Cobertura y avance** | Métricas de progreso (% codificado) | Monitoreo de avance |
| 📎 **Citas por código** | Ver todas las citas de un código | Verificar densidad |

#### 3.3.2 Flujo Guiado (Recomendado)

1. **Seleccionar entrevista activa** (opcional pero recomendado)
2. **Clic en "🔄 Siguiente recomendado"**
3. El sistema muestra:
   - Fragmento pendiente de codificar
   - Códigos sugeridos (si existen similares)
   - Pendientes en entrevista y total
4. **Opciones de decisión:**
   - ✅ **Aceptar código sugerido** → Asigna automáticamente
   - 📝 **Código nuevo** → Crear código con nombre y cita
   - ⏭️ **Saltar** → Pasar al siguiente (el fragmento vuelve a la cola)

**Estrategias de selección:**
- **Recientes:** Prioriza entrevistas actualizadas recientemente
- **Antiguas:** Comienza por las primeras entrevistas
- **Aleatoria:** Selección al azar (útil para muestreo)

#### 3.3.3 Análisis con IA (Runner Automatizado)

Para procesar múltiples fragmentos automáticamente:

1. Ir a **Asignar código** o **Sugerencias semánticas**
2. Configurar parámetros:
   - **Pasos:** Número de fragmentos a procesar (ej. 50)
   - **Incluir ya codificados:** Generalmente ❌ desactivado
3. **Clic en "🚀 Runner"**
4. El sistema:
   - Procesa cada fragmento con LLM
   - Genera memos analíticos
   - Envía códigos candidatos a la bandeja de validación

**Monitoreo del Runner:**
```
Estado: running
Paso: 45/50
Entrevista: Entrevista_Maria.docx (3/20)
Memos guardados: 42
Candidatos enviados: 40
```

#### 3.3.4 Sugerencias Semánticas

Usa embeddings para encontrar fragmentos similares:

1. **Ingresar fragmento semilla** (o dejar vacío para selección automática)
2. **Configurar filtros:**
   - Top-K: Número de resultados (5-20 recomendado)
   - Archivo: Filtrar por entrevista
   - Área temática: Filtrar por metadato
   - Actor principal: Filtrar por rol del entrevistado
3. **Buscar sugerencias**
4. **Para cada fragmento similar:**
   - Ver score de similitud (0-1)
   - Propagar código existente, o
   - Crear código nuevo

**Uso ideal:** Cuando tienes un código y quieres encontrar todas las instancias similares en el corpus.

#### 3.3.5 Validación de Códigos Candidatos

Los códigos generados por IA van a una "bandeja de validación":

1. Ir a **Bandeja de Validación** (en el menú)
2. **Refrescar bandeja** para ver candidatos pendientes
3. **Para cada candidato:**
   - ✅ **Aprobar:** Promover a código definitivo
   - ❌ **Rechazar:** Descartar
   - 🔀 **Fusionar:** Combinar con código existente
4. **Operaciones en lote:**
   - "Validar todos" para aprobar masivamente
   - Filtrar por fuente (LLM, Discovery, Manual)

#### 3.3.6 Métricas de Cobertura

En la pestaña **📊 Cobertura y avance**:

| Métrica | Descripción | Objetivo |
|---------|-------------|----------|
| **Fragmentos codificados** | Fragmentos con al menos un código | Maximizar |
| **Fragmentos sin código** | Pendientes de codificar | Minimizar (→0) |
| **Cobertura %** | Porcentaje codificado | >90% ideal |
| **Códigos únicos** | Total de códigos creados | Depende del corpus |
| **Total de citas** | Asignaciones código-fragmento | >1 cita/código ideal |

**Exportación:**
- 📦 **REFI-QDA:** Formato compatible con Atlas.ti
- 📊 **CSV (MAXQDA):** Formato tabular para MAXQDA

---

### 3.4 Codificación Axial (Etapa 4)

La codificación axial establece relaciones entre códigos y los agrupa en categorías de mayor abstracción.

#### 3.4.1 Prerrequisitos

Antes de iniciar codificación axial:

- [ ] Cobertura de codificación abierta ≥70%
- [ ] Infraestructura lista (pre-axialidad): `GET /api/admin/code-id/status` reporta `axial_ready=true`
- [ ] Códigos sincronizados en Neo4j
- [ ] Al menos 50 códigos únicos (masa crítica)

> Nota: `axial_ready` valida **consistencia estructural** (identidad/canonicidad/ausencia de ciclos no triviales).
> No evalúa teoría, importancia, centralidad ni “calidad” del codebook.

#### 3.4.2 Tipos de Relaciones Axiales

| Tipo | Descripción | Ejemplo |
|------|-------------|---------|
| **causa** | Un código causa/origina otro | `pobreza` → causa → `exclusion_social` |
| **condicion** | Contexto que habilita/restringe | `educacion_formal` → condicion → `movilidad_social` |
| **consecuencia** | Resultado o efecto | `participacion` → consecuencia → `empoderamiento` |
| **parte-de** | Componente de una categoría | `asamblea_vecinal` → parte-de → `Organizacion_Comunitaria` |

#### 3.4.3 Crear Relaciones Axiales

**Desde CLI:**
```powershell
python main.py --env .env axial relate \
    --categoria "Participación Ciudadana" \
    --codigo "asamblea_vecinal" \
    --tipo parte-de \
    --evidencia <fragment_id_1> <fragment_id_2> \
    --memo "Las asambleas son el mecanismo principal de participación"
```

**Desde Frontend (Neo4j Explorer):**
1. Abrir **Explorador de Grafo**
2. Seleccionar nodo código (clic)
3. **Crear relación** → Seleccionar tipo y destino
4. Agregar evidencia (fragmentos que sustentan la relación)

#### 3.4.4 Análisis GDS (Graph Data Science)

Neo4j GDS calcula métricas sobre el grafo de códigos:

**Desde el panel Neo4j Explorer:**
1. Clic en **"⚙️ Calcular GDS"**
2. Seleccionar algoritmos:
   - **Louvain:** Detecta comunidades (clusters de códigos relacionados)
   - **PageRank:** Calcula centralidad (qué códigos son más "importantes")
3. **Aplicar al grafo** → Los nodos se colorean por comunidad

**Desde CLI:**
```powershell
python main.py --env .env axial gds --algorithm louvain
python main.py --env .env axial gds --algorithm pagerank
```

**Interpretación de resultados:**

| Métrica | Significado | Uso analítico |
|---------|-------------|---------------|
| **community_id** | Cluster al que pertenece el código | Identificar categorías emergentes |
| **pagerank** | Centralidad (0-1, mayor = más central) | Códigos candidatos a núcleo |
| **betweenness** | Puente entre comunidades | Códigos conectores |

#### 3.4.5 Predicción de Enlaces

El sistema puede sugerir relaciones probables entre códigos:

1. Ir a **Explorador de Grafo** → **Predicción de Enlaces**
2. Seleccionar código de origen
3. Ver códigos sugeridos con probabilidad
4. **Confirmar o rechazar** cada predicción

**Algoritmos de predicción:**
- **Adamic-Adar:** Basado en vecinos comunes
- **Preferential Attachment:** Códigos populares atraen más conexiones
- **Common Neighbors:** Similitud estructural

#### 3.4.6 Visualización del Grafo

**Controles de visualización:**
- **Zoom:** Rueda del mouse
- **Pan:** Arrastrar fondo
- **Selección:** Clic en nodo
- **Multi-selección:** Ctrl+Clic
- **Centrar:** Doble-clic en nodo

**Filtros:**
- Por proyecto
- Por comunidad (post-GDS)
- Por tipo de nodo (Código, Categoría, Fragmento)

**Coloreado:**
- Sin GDS: Color uniforme
- Post-GDS: Color por comunidad
- Tamaño: Proporcional a PageRank

#### 3.4.7 Sincronización PostgreSQL ↔ Neo4j

Si hay discrepancias entre bases de datos:

1. Ir a **Admin** → **Sincronización**
2. **Auditar:** Comparar conteos PG vs Neo4j
3. **Sincronizar fragmentos:** Enviar fragmentos faltantes a Neo4j
4. **Sincronizar axial:** Enviar relaciones axiales a Neo4j

**Desde CLI:**
```powershell
# Ver diferencias
python main.py --env .env neo4j audit --project jd-007

# Sincronizar
python main.py --env .env neo4j sync --project jd-007
```

#### 3.4.8 Tabla de Estado Axial

| Componente | Ubicación | Propósito |
|------------|-----------|-----------|
| `analisis_codigos_abiertos` | PostgreSQL | Códigos asignados a fragmentos |
| `analisis_axial` | PostgreSQL | Relaciones categoría-código |
| `Codigo` (nodo) | Neo4j | Representación en grafo |
| `Categoria` (nodo) | Neo4j | Agrupaciones de códigos |
| `RELACIONADO_CON` | Neo4j | Relaciones entre códigos |
| `TIENE_CODIGO` | Neo4j | Fragmento → Código |

---

### 3.5 Núcleo selectivo
1. Consolidar categorías centrales.
2. Evaluar centralidad y cobertura.
3. Ajustar núcleo y reportar.

### 3.6 Discovery (búsqueda semántica)
1. Buscar conceptos y fragmentos relacionados.
2. Proponer códigos candidatos.
3. Enviar candidatos a validación.

### 3.7 Validación de códigos candidatos
1. Ir al panel de validación.
2. **Aprobar, rechazar o fusionar** candidatos.
3. Promover a códigos definitivos.

### 3.8 Grafo y GDS
1. Abrir el explorador Neo4j.
2. Ejecutar cálculos GDS (comunidades, centralidad).
3. Aplicar coloración/tamaños en visualización.

### 3.9 Reportes
1. Generar reportes de etapa.
2. Exportar resultados y manifiestos.

---

## 4) Paneles principales (Frontend)

- **Neo4jExplorer:** visualización del grafo, controles GDS.
- **CodingPanel:** codificación abierta y sugerencias.
- **DiscoveryPanel:** búsqueda semántica y proposición de códigos.
- **CodeValidationPanel:** validación y promoción de códigos candidatos.
- **ReportsPanel:** reportes y resultados.
- **SystemHealthDashboard:** estado de servicios (PostgreSQL/Neo4j/Qdrant/LLM).
- **BackendStatus:** conectividad básica con `/healthz`.
- **ApiErrorToast / PanelErrorBoundary / Skeleton:** UX resiliente.

---

## 5) Endpoints esenciales (Backend)

- **Health:**
  - `GET /healthz` → OK básico.
  - `GET /api/health/full` → salud detallada (requiere auth).
- **Auth:** `/api/auth/*`
- **Projects:** `/api/projects/*`
- **Ingesta:** `/api/ingest`
- **Discovery:** `/api/discover`
- **Códigos candidatos:** `/api/codes/candidates/*`
- **Admin:** `/api/admin/*`

---

## 6) Operación técnica (resumen)

- **PostgreSQL:** almacenamiento principal de usuarios, proyectos y fragmentos.
- **Qdrant:** embeddings y búsqueda semántica.
- **Neo4j/Memgraph:** grafo de conocimiento y analítica GDS.
- **Celery + Redis:** tareas largas (análisis LLM asíncrono).

### 6.1 Flujo de datos hacia Neo4j (multi-tenant)

**Fuentes principales:**
- **Ingesta** crea Entrevista/Fragmento en Neo4j.
- **Sync diferido** reingesta desde PostgreSQL cuando Neo4j estuvo offline.
- **Axial** crea Categoria/Codigo/REL desde `analisis_axial`.
- **Codificación abierta** crea `TIENE_CODIGO` en Neo4j.

**Diagrama (alto nivel):**

```mermaid
flowchart TD
  A[DOCX/Audio] --> B[Ingesta: app/ingestion.py]
  B -->|PostgreSQL| PG[(entrevista_fragmentos)]
  B -->|Qdrant| QD[(embeddings)]
  B -->|Neo4j (si disponible)| N1[(Entrevista/Fragmento)]

  PG -->|/api/admin/sync-neo4j| S1[Sync diferido: app/neo4j_sync.py]
  S1 --> N1

  PG -->|analisis_axial| AX[(analisis_axial)]
  AX -->|/api/admin/sync-neo4j/axial| S2[Sync axial]
  S2 --> N2[(Categoria/Codigo/REL)]

  PG -->|analisis_codigos_abiertos| OC[(codificación)]
  OC -->|merge_fragment_code| N3[(TIENE_CODIGO)]
```

**Claves de aislamiento:** todos los nodos y relaciones se persisten con `project_id`.

### 6.2 Auditoría Neo4j vs PostgreSQL (admin)

Usa el botón **🧭 Audit Neo4j vs PG** para comparar conteos básicos:
- PostgreSQL: fragmentos, archivos, códigos abiertos, relaciones axiales.
- Neo4j: entrevistas, fragmentos, códigos, categorías, relaciones.
- Indicadores legacy: `nodes_sin_project_id` y `rels_sin_project_id`.

Si Neo4j está vacío pero los flags `neo4j_synced` están en TRUE:
1) **Resetear flags de sincronización**.
2) **Sincronizar fragmentos**.
3) **Sincronizar relaciones axiales**.

---

## 7) Salud del sistema

- Verificar conectividad rápida: `GET /healthz`.
- Verificar salud completa: `GET /api/health/full` (autenticado).
- Revisar logs en `logs/app.jsonl`.

---

## 8) Seguridad y claves

- JWT con expiración configurada en variables de entorno.
- API Key soporta `API_KEY_ORG_ID` para multi-tenant estricto.
- Recomendado: usar secretos fuertes y rotación periódica.

---

## 9) Troubleshooting rápido

- **Timeouts:** revisar servicios externos.
- **401/403:** revisar roles, organización y API key.
- **Errores de pool:** reiniciar backend y revisar conexiones.

### 9.1 Problemas comunes en Codificación

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| Runner se detiene con timeout | Timeout de 30s muy corto | Actualizado a 60s en Sprint 31 |
| Discovery retorna 0 resultados | Umbral de anclas muy alto | Ajustado a 0.40 (era 0.55) |
| Error LLM "JSON inválido" | Respuesta truncada de Azure | Reintentar; max_tokens aumentado a 400 |
| Códigos no aparecen en Neo4j | Falta sincronización | Admin → Sincronizar Neo4j |
| GDS sin comunidades | No se ha ejecutado Louvain | Calcular GDS desde Neo4j Explorer |
| Múltiples errores 401 | Token expirado durante runner largo | Singleton refresh implementado |

### 9.2 Diagnóstico de Codificación Axial

**Verificar estado:**
```powershell
# Contar códigos en PostgreSQL
python -c "from app.settings import load_settings; from app.clients import get_pg_connection, return_pg_connection; s=load_settings(); c=get_pg_connection(s); cur=c.cursor(); cur.execute('SELECT count(DISTINCT codigo) FROM analisis_codigos_abiertos WHERE project_id=%s', ('jd-007',)); print('Códigos PG:', cur.fetchone()[0]); return_pg_connection(c)"

# Contar códigos en Neo4j
python -c "from app.settings import load_settings; from app.clients import build_service_clients; s=load_settings(); c=build_service_clients(s); r=c.neo4j.session().run('MATCH (c:Codigo {project_id: \"jd-007\"}) RETURN count(c)'); print('Códigos Neo4j:', r.single()[0])"
```

**Discrepancia típica:** Si PostgreSQL tiene más códigos que Neo4j, ejecutar sincronización.

Documentación de soporte: ver `docs/05-troubleshooting/`.

---

## 10) Referencias útiles

- Guía de ejecución local: [docs/01-configuracion/run_local.md](01-configuracion/run_local.md)
- Configuración infraestructura: [docs/01-configuracion/configuracion_infraestructura.md](01-configuracion/configuracion_infraestructura.md)
- Metodología: [docs/02-metodologia/manual_etapas.md](02-metodologia/manual_etapas.md)
- Troubleshooting: [docs/05-troubleshooting/](05-troubleshooting/)
- Plan cobertura 100%: [docs/03-sprints/proximos_sprint/sprint31_cobertura_100_fragmentos.md](03-sprints/proximos_sprint/sprint31_cobertura_100_fragmentos.md)

---

## 11) Flujo Visual de Trabajo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FLUJO DE ANÁLISIS CUALITATIVO                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ETAPA 3: CODIFICACIÓN ABIERTA                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                      │
│  │ Fragmentos  │───▶│ Asignar     │───▶│ Validar     │                      │
│  │ pendientes  │    │ códigos     │    │ candidatos  │                      │
│  └─────────────┘    └─────────────┘    └─────────────┘                      │
│        │                  │                  │                              │
│        ▼                  ▼                  ▼                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                      │
│  │ Runner LLM  │    │ Sugerencias │    │ Bandeja     │                      │
│  │ automático  │    │ semánticas  │    │ validación  │                      │
│  └─────────────┘    └─────────────┘    └─────────────┘                      │
│                                                                             │
│  ────────────────────────────────────────────────────────────────────────   │
│                                                                             │
│  ETAPA 4: CODIFICACIÓN AXIAL                                                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                      │
│  │ Códigos     │───▶│ Crear       │───▶│ Calcular    │                      │
│  │ validados   │    │ relaciones  │    │ GDS         │                      │
│  └─────────────┘    └─────────────┘    └─────────────┘                      │
│        │                  │                  │                              │
│        ▼                  ▼                  ▼                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                      │
│  │ Sincronizar │    │ Categorías  │    │ Comunidades │                      │
│  │ Neo4j       │    │ emergentes  │    │ + PageRank  │                      │
│  └─────────────┘    └─────────────┘    └─────────────┘                      │
│                                                                             │
│  ────────────────────────────────────────────────────────────────────────   │
│                                                                             │
│  ETAPA 5: NÚCLEO SELECTIVO                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                      │
│  │ Centralidad │───▶│ Seleccionar │───▶│ Generar     │                      │
│  │ (PageRank)  │    │ categoría   │    │ reporte     │                      │
│  │             │    │ núcleo      │    │ integrado   │                      │
│  └─────────────┘    └─────────────┘    └─────────────┘                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Manual alineado con el código vigente (Enero 2026).*