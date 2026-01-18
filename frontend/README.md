# Módulo Frontend - Dashboard React

Dashboard web para análisis cualitativo construido con React 18 + Vite + TypeScript.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                   FRONTEND (React + Vite)                    │
│                   http://localhost:5173                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  App.tsx - Orquestador principal                        ││
│  │  - Gestión de proyectos                                 ││
│  │  - Navegación por etapas (9 stages)                     ││
│  │  - Estado global de la aplicación                       ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │  components/                                            ││
│  │  - IngestionPanel: Subida de archivos DOCX              ││
│  │  - AnalysisPanel: Análisis LLM asistido                 ││
│  │  - CodingPanel: Codificación abierta/axial              ││
│  │  - Neo4jExplorer: Consultas Cypher                      ││
│  │  - StageCard: Tarjeta de etapa del workflow             ││
│  │  - CodesList: Lista de códigos                          ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │  services/                                              ││
│  │  - api.ts: Cliente HTTP genérico                        ││
│  │  - neo4jClient.ts: Cliente especializado Neo4j          ││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │  hooks/                                                 ││
│  │  - useProjects: Gestión de proyectos                    ││
│  │  - useStatus: Estado del proyecto actual                ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                          │ HTTP/REST
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI)                          │
│                   http://localhost:8000                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Estructura de Archivos

```
frontend/
├── src/
│   ├── App.tsx              # Componente principal (328 líneas)
│   ├── App.css              # Estilos globales
│   ├── types.ts             # Interfaces TypeScript
│   ├── main.tsx             # Punto de entrada
│   ├── components/          # Componentes React
│   │   ├── IngestionPanel.tsx     # Subida DOCX
│   │   ├── AnalysisPanel.tsx      # Análisis LLM
│   │   ├── CodingPanel.tsx        # Codificación (39KB)
│   │   ├── Neo4jExplorer.tsx      # Consultas Cypher
│   │   ├── StageCard.tsx          # Etapas workflow
│   │   ├── CodesList.tsx          # Lista códigos
│   │   ├── ManifestSummary.tsx    # Resumen manifiesto
│   │   └── Toast.tsx              # Notificaciones
│   ├── services/            # Clientes API
│   │   ├── api.ts                 # Fetch genérico
│   │   └── neo4jClient.ts         # Cliente Neo4j
│   ├── hooks/               # React Hooks
│   │   ├── useProjects.ts         # Gestión proyectos
│   │   └── useStatus.ts           # Estado actual
│   ├── client/              # Cliente API generado (OpenAPI)
│   └── utils/               # Utilidades
├── package.json             # Dependencias npm
├── vite.config.ts           # Configuración Vite
├── tsconfig.json            # Configuración TypeScript
└── index.html               # HTML principal
```

---

## Componentes Principales

| Componente | Descripción | Tamaño |
|------------|-------------|--------|
| `App.tsx` | Orquestador con 9 etapas de workflow | 328 líneas |
| `CodingPanel.tsx` | Codificación completa | 39KB |
| `Neo4jExplorer.tsx` | Consultas Cypher + vis. tabla | 23KB |
| `AnalysisPanel.tsx` | Análisis LLM asistido | 16KB |
| `IngestionPanel.tsx` | Subida de archivos | 9KB |

---

## Etapas del Workflow (9)

```typescript
const stageTitles = [
  ["preparacion", "Preparación y reflexividad"],
  ["ingesta", "Ingesta y normalización"],
  ["codificacion", "Codificación abierta"],
  ["axial", "Codificación axial"],
  ["nucleo", "Selección del núcleo"],
  ["transversal", "Análisis transversal"],
  ["validacion", "Validación y saturación"],
  ["informe", "Informe integrado"],
  ["analisis", "Análisis asistido por LLM"]
];
```

---

## Variables de Entorno

Editar `frontend/.env` (o crear `frontend/.env.local` para overrides locales):

```env
# DEV recomendado: dejar vacío para usar same-origin.
# El dev-server de Vite proxea /api, /healthz, /neo4j, /token, etc. al backend.
VITE_API_BASE=

# Target del proxy de Vite (server-side). Útil si cambias el puerto del backend.
VITE_BACKEND_URL=http://127.0.0.1:8000

# API Key para autenticación
VITE_NEO4J_API_KEY=tu-api-key
```

---

## Ejecución

```bash
# Instalar dependencias
npm install

# Desarrollo
npm run dev

# Build producción
npm run build

# Preview producción
npm run preview

# Tests
npm run test
```

---

## Dependencias Principales

| Paquete | Versión | Uso |
|---------|---------|-----|
| `react` | 18.3.1 | Framework UI |
| `react-force-graph-2d` | 1.29.0 | Visualización de grafos |
| `vite` | 5.4.10 | Bundler |
| `typescript` | 5.6.3 | Tipado estático |
| `vitest` | 2.1.3 | Testing |

---

## Interfaces Principales (types.ts)

```typescript
// Proyecto
interface ProjectEntry { id, name, description, created_at }

// Estado
interface StatusSnapshot { project, stages, manifest }

// Codificación
interface CodingAssignPayload { fragmento_id, codigo, cita }
interface CodingSuggestion { fragmento_id, score, archivo }

// Neo4j
interface Neo4jGraph { nodes, relationships }
interface Neo4jTable { columns, rows }
```

---

*Documento generado: Diciembre 2024*
