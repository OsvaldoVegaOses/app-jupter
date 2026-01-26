# Flujo de codificación (Grounded Theory) — Desarrollo pendiente

## Nota relacionada: modelo ontológico futuro (IDs canónicos y `superseded`)

Para la reflexión completa sobre el salto a identidad estable (`code_id` / `canonical_code_id`) y la opción de introducir el estado `superseded` (reemplazo evolutivo, distinto de `merged`), ver:

- [docs/04-arquitectura/desarrollo_pendiente/modelo_ontologico_code_id_y_superseded.md](docs/04-arquitectura/desarrollo_pendiente/modelo_ontologico_code_id_y_superseded.md)
# Flujo de Codificación Grounded Theory - Estado Actual y Desarrollo Pendiente

> **Fecha:** 19 Enero 2026  
> **Proyecto:** APP_Jupter - Sistema de Análisis Cualitativo

---

## 1. Resumen Ejecutivo

Este documento describe el flujo completo de las tres etapas de codificación de Grounded Theory implementadas en el frontend, incluyendo componentes disponibles, criterios de cierre, y desarrollo pendiente.

---

## 2. Arquitectura de Vistas de Investigación

### 2.1 Estructura General

```
App.tsx
└── view === "investigacion"
    └── investigationView (estado)
        ├── "abierta"    → Codificación Abierta (Etapa 3)
        ├── "axial"      → Codificación Axial (Etapa 4)
        └── "selectiva"  → Codificación Selectiva (Etapa 5)
```

### 2.2 Navegación

- **Desde WorkflowPanel:** `onNavigateToInvestigation(tab)` cambia `investigationView`
- **Desde barra de navegación:** Botones "Codificación abierta", "Codificación axial", "Codificación selectiva"
- **Persistencia:** Estado guardado en `localStorage` con key `qualy-dashboard-investigation-view`

---

## 3. Etapa 3: Codificación Abierta

### 3.1 Componentes Implementados ✅

| Componente | Archivo | Función |
|------------|---------|---------|
| `DiscoveryPanel` | `DiscoveryPanel.tsx` | Búsqueda semántica exploratoria con triplete (positivo/negativo/target) |
| `CodingPanel` | `CodingPanel.tsx` | Asignación de códigos a fragmentos por entrevista |
| `CodesList` | `CodesList.tsx` | Lista de códigos con frecuencia y búsqueda |
| `CodeValidationPanel` | `CodeValidationPanel.tsx` | Validación de candidatos (pendientes/validados/rechazados/hipótesis) |

### 3.2 Criterios de Cierre

```python
# home_panorama.py - compute_axial_gate()

# Política "auto" (default):
if coverage_percent >= 70.0:
    return "unlocked"  # Por cobertura

if plateau_detected and coverage_percent >= 30.0:
    return "unlocked"  # Por saturación

# Política "manual":
if axial_manual_unlocked:
    return "unlocked"
```

| Criterio | Umbral | Configurable |
|----------|--------|--------------|
| Cobertura mínima | ≥70% | `axial_min_coverage_percent` |
| Saturación + cobertura mínima | Plateau + ≥30% | `axial_gate_policy: "saturation"` |
| Manual | Flag activado | `axial_manual_unlocked: true` |

### 3.3 Métricas Observadas

```typescript
observed.codificacion = {
  porcentaje_cobertura: number,
  fragmentos_codificados: number,
  fragmentos_sin_codigo: number,
  codigos_unicos: number,
  citas: number
}
```

### 3.4 Desarrollo Pendiente ⏳

| Funcionalidad | Prioridad | Descripción |
|---------------|-----------|-------------|
| **Merge de códigos sinónimos** | Alta | UI para fusionar códigos duplicados |
| **Bulk coding** | Media | Asignar mismo código a múltiples fragmentos |
| **Comparación inter-coder** | Media | Métricas de acuerdo entre codificadores |
| **Export REFI-QDA mejorado** | Baja | Incluir memos y relaciones |

---

## 4. Etapa 4: Codificación Axial

### 4.1 Componentes Implementados ✅

| Componente | Archivo | Función |
|------------|---------|---------|
| `LinkPredictionPanel` | `LinkPredictionPanel.tsx` | Predicción de enlaces faltantes (common_neighbors, etc.) |
| `HiddenRelationshipsPanel` | `HiddenRelationshipsPanel.tsx` | Descubrimiento de relaciones ocultas |
| `BloomOrExplorer` | `BloomOrExplorer.tsx` | Visualización de grafo Neo4j (Bloom o Explorer) |

### 4.2 Criterios de Cierre

| Criterio | Condición | Endpoint |
|----------|-----------|----------|
| Relaciones axiales | `observed.axial.relaciones > 0` | Auto-detectado |
| Categorías definidas | `observed.axial.categorias >= 1` | Auto-detectado |
| Marcado manual | Usuario completa etapa | `/api/projects/{id}/stages/axial/complete` |

### 4.3 Métricas Observadas

```typescript
observed.axial = {
  relaciones: number,
  categorias: number
}
```

### 4.4 Flujo de Hipótesis (Nuevo - Enero 2026)

```
┌─────────────────────────────────────────────────────────────────┐
│ Link Prediction / Discovery → Proponer como código             │
│                                                                 │
│         ↓                                                       │
│                                                                 │
│ codigos_candidatos (estado: 'pendiente')                        │
│ └── fragmento_id = NULL → Estado cambia a 'hipotesis'           │
│                                                                 │
│         ↓                                                       │
│                                                                 │
│ CodeValidationPanel (filtro: Hipótesis)                         │
│ └── Buscar evidencia empírica (fragmentos que soporten)         │
│ └── Si se encuentra → Validar con evidencia                     │
│ └── Si no → Rechazar o mantener como hipótesis                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.5 Desarrollo Pendiente ⏳

| Funcionalidad | Prioridad | Descripción |
|---------------|-----------|-------------|
| **Paradigma de Strauss** | Alta | Modelo visual: condiciones causales, contexto, acciones, consecuencias |
| **Validación de hipótesis mejorada** | Alta | Workflow guiado para buscar evidencia |
| **Persistencia GDS** | Media | Guardar resultados de Louvain/PageRank en Neo4j |
| **Análisis comparativo** | Media | Comparar estructuras entre entrevistas |
| **Timeline de relaciones** | Baja | Visualizar evolución temporal |

---

## 5. Etapa 5: Codificación Selectiva

### 5.1 Componentes Implementados ✅

| Componente | Archivo | Función |
|------------|---------|---------|
| `AnalysisPanel` | `AnalysisPanel.tsx` | Análisis LLM por entrevista |
| `GraphRAGPanel` | `GraphRAGPanel.tsx` | Consultas con contexto de grafo |
| `InsightsPanel` | `InsightsPanel.tsx` | Insights emergentes |
| `AgentPanel` | `AgentPanel.tsx` | Agente autónomo de investigación |

### 5.2 Criterios de Cierre

| Criterio | Condición | Endpoint |
|----------|-----------|----------|
| Candidatos a núcleo | ≥1 identificado | `/api/reports/nucleus-candidates` |
| Informe Etapa 4 | Generado | `/api/reports/stage4-final` |
| Narrativa integrada | Generada | Via GraphRAGPanel |
| Marcado manual | Usuario completa | `/api/projects/{id}/stages/nucleo/complete` |

### 5.3 Desarrollo Pendiente ⏳

| Funcionalidad | Prioridad | Descripción |
|---------------|-----------|-------------|
| **Selección formal de núcleo** | Alta | UI para marcar categoría como núcleo con justificación |
| **Diagrama de integración** | Alta | Visualización central con categoría núcleo |
| **Muestreo teórico guiado** | Alta | Sugerencias de qué datos adicionales recolectar |
| **Generación de teoría** | Media | Síntesis automática de proposiciones teóricas |
| **Exportación académica** | Media | Formato para publicación (APA, tesis) |

---

## 6. Endpoints API Relacionados

### 6.1 Codificación Abierta

```
POST /api/coding/assign          # Asignar código a fragmento
POST /api/coding/suggest         # Sugerencias de códigos
GET  /api/coding/stats           # Estadísticas de codificación
GET  /api/coding/saturation      # Curva de saturación
POST /api/search/discover        # Búsqueda Discovery
```

### 6.2 Codificación Axial

```
GET  /api/axial/predict          # Predicción de enlaces
GET  /api/axial/community-links  # Enlaces por comunidad
GET  /api/axial/hidden-relationships  # Relaciones ocultas
POST /api/axial/confirm-relationship  # Confirmar relación
POST /api/axial/gds              # Ejecutar GDS (Louvain, PageRank)
```

### 6.3 Codificación Selectiva

```
GET  /api/reports/nucleus-candidates  # Candidatos a núcleo
GET  /api/reports/stage4-summary      # Resumen Etapa 4
POST /api/reports/stage4-final        # Informe final Etapa 4
POST /api/graphrag/query              # Consulta GraphRAG
```

### 6.4 Gestión de Etapas

```
POST /api/projects/{id}/stages/{stage}/complete  # Marcar etapa como completada
GET  /api/status                                  # Estado del proyecto
```

---

## 7. Configuración del Proyecto

```python
# project_state.py - get_project_config()

default_config = {
    # Gate Axial (Etapa 4)
    "axial_gate_policy": "auto",           # auto | coverage | saturation | manual
    "axial_min_coverage_percent": 70.0,    # Umbral de cobertura
    "axial_min_saturation_window": 3,      # Ventana para detectar plateau
    "axial_min_saturation_threshold": 2,   # Max códigos nuevos para plateau
    "axial_manual_unlocked": False,        # Override manual
    
    # Discovery
    "discovery_threshold": 0.30,
    
    # Análisis LLM
    "analysis_temperature": 0.3,
    "analysis_max_tokens": 2000,
}
```

---

## 8. Matriz de Estado de Desarrollo

| Etapa | Componentes | Criterios | Métricas | API | Estado |
|-------|-------------|-----------|----------|-----|--------|
| **Abierta** | ✅ 100% | ✅ 100% | ✅ 100% | ✅ 100% | **Producción** |
| **Axial** | ✅ 100% | ⚠️ 80% | ✅ 100% | ✅ 90% | **Beta** |
| **Selectiva** | ⚠️ 70% | ⚠️ 60% | ⚠️ 50% | ⚠️ 70% | **Alpha** |

---

## 9. Roadmap Sugerido

### Sprint Inmediato (1-2 semanas)
1. ✅ Implementar estado 'hipótesis' para códigos sin evidencia
2. ⏳ Completar workflow de validación de hipótesis
3. ⏳ UI para selección formal de categoría núcleo

### Sprint Siguiente (3-4 semanas)
1. Paradigma visual de Strauss para Axial
2. Persistencia de resultados GDS
3. Generación automática de diagrama de integración

### Backlog
1. Comparación inter-coder
2. Exportación académica
3. Muestreo teórico guiado

---

## 10. Archivos Clave

### Frontend
- `frontend/src/App.tsx` - Routing de vistas
- `frontend/src/components/WorkflowPanel.tsx` - Panel de flujo de trabajo
- `frontend/src/components/CodingPanel.tsx` - Codificación abierta
- `frontend/src/components/LinkPredictionPanel.tsx` - Axial
- `frontend/src/components/GraphRAGPanel.tsx` - Selectiva

### Backend
- `app/home_panorama.py` - Lógica de gates y acciones primarias
- `app/project_state.py` - Estado y configuración del proyecto
- `app/coding.py` - Lógica de codificación
- `app/axial.py` - Lógica axial y GDS
- `app/nucleus.py` - Selección de núcleo

### Configuración
- `main.py` - STAGE_DEFINITIONS
- `.env` - Variables de entorno

---

*Documento generado automáticamente - 19 Enero 2026*
