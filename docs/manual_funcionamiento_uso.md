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
### 3.3 Codificación abierta
1. Revisar fragmentos sugeridos.
2. Crear/editar códigos.
3. Ver métricas de cobertura y consistencia.

### 3.4 Codificación axial
1. Relacionar códigos y categorías.
2. Validar relaciones tipadas (causa, condición, consecuencia, parte-de).
3. Persistir relaciones en grafo.

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

Documentación de soporte: ver `docs/05-troubleshooting/`.

---

## 10) Referencias útiles

- Guía de ejecución local: [docs/01-configuracion/run_local.md](01-configuracion/run_local.md)
- Configuración infraestructura: [docs/01-configuracion/configuracion_infraestructura.md](01-configuracion/configuracion_infraestructura.md)
- Metodología: [docs/02-metodologia/manual_etapas.md](02-metodologia/manual_etapas.md)
- Troubleshooting: [docs/05-troubleshooting/](05-troubleshooting/)

---

*Manual alineado con el código vigente (Enero 2026).*