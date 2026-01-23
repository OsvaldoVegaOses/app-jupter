# Epic: Epistemic Mode v1 — Propuesta Definitiva

> **Fecha:** 23 Enero 2026  
> **Estado:** APROBADO para implementación  
> **Dependencias:** Fase 1.5 Core completada ✅  
> **Estimación:** 10-12 horas (3 sesiones)

---

## 1. Contraste de propuestas

### 1.1 Propuesta original vs Aporte

| Aspecto | Propuesta Original | Aporte Usuario | Decisión Final |
|---------|-------------------|----------------|----------------|
| **Priorización** | A+B ahora, C después | A+B+C ahora (evitar más proyectos mezclados) | ✅ **A+B+C ahora** |
| **Stage naming** | Inconsistente (`discovery` vs `discovery_synthesis.txt`) | Detectado: crear mapping explícito | ✅ **Mapping stage→filename** |
| **Fallback logging** | Silencioso | Warning + `prompt_version="fallback"` | ✅ **Log warning auditado** |
| **Lock de modo** | Solo en criterios | Forzar en backend, no solo UI | ✅ **Backend enforcement** |
| **UI (Ticket D)** | Opcional | "Si hay usuarios, mejor pronto" | 🔄 **D después de C** |

### 1.2 Gaps identificados y cerrados

| Gap | Solución |
|-----|----------|
| Stage names no coinciden con archivos | Definir `STAGE_TO_FILE` dict en loader |
| Fallback silencioso | `_logger.warning("prompt.fallback", ...)` |
| Lock de modo solo cosmético | Check en `set_project_epistemic_mode()` que rechaza si `has_axial_relations=True` |
| Sin test de diferenciación real | Agregar test que verifica "gerundio" en output constructivista |

---

## 2. Diseño definitivo

### 2.1 Schema (PostgreSQL)

```sql
-- migrations/017_epistemic_mode.sql
ALTER TABLE pg_proyectos 
ADD COLUMN IF NOT EXISTS epistemic_mode TEXT 
DEFAULT 'constructivist' 
CHECK (epistemic_mode IN ('constructivist', 'post_positivist'));

COMMENT ON COLUMN pg_proyectos.epistemic_mode IS 
'Modo epistemológico: constructivist (Charmaz) | post_positivist (Glaser/Strauss)';

-- Índice para queries frecuentes
CREATE INDEX IF NOT EXISTS idx_proyectos_epistemic_mode 
ON pg_proyectos(epistemic_mode);
```

### 2.2 Enum y configuración (`app/settings.py`)

```python
from enum import Enum

class EpistemicMode(str, Enum):
    CONSTRUCTIVIST = "constructivist"
    POST_POSITIVIST = "post_positivist"
    
    @classmethod
    def from_string(cls, value: str) -> "EpistemicMode":
        """Parse string to enum, defaulting to CONSTRUCTIVIST."""
        try:
            return cls(value)
        except ValueError:
            return cls.CONSTRUCTIVIST
```

### 2.3 Estructura de prompts (definitiva)

```
app/
└── prompts/
    ├── __init__.py
    ├── loader.py
    ├── constructivist/
    │   ├── system_base.txt
    │   ├── open_coding.txt
    │   ├── axial_coding.txt
    │   ├── discovery.txt          # Renombrado de discovery_synthesis
    │   ├── selective.txt
    │   └── memo.txt               # Unificado (reflexivo)
    └── post_positivist/
        ├── system_base.txt
        ├── open_coding.txt
        ├── axial_coding.txt
        ├── discovery.txt
        ├── selective.txt
        └── memo.txt               # Unificado (conceptual)
```

### 2.4 Loader con mapping y fallback auditado (`app/prompts/loader.py`)

```python
"""Prompt loader with epistemic mode differentiation and audit trail."""
from pathlib import Path
from functools import lru_cache
from typing import Tuple
import structlog

from app.settings import EpistemicMode

_logger = structlog.get_logger()
PROMPTS_DIR = Path(__file__).parent

# Mapping explícito stage → filename (cierra gap de naming)
STAGE_TO_FILE = {
    "open_coding": "open_coding.txt",
    "axial_coding": "axial_coding.txt",
    "discovery": "discovery.txt",
    "selective": "selective.txt",
    "memo": "memo.txt",
}


@lru_cache(maxsize=32)
def load_prompt(mode: EpistemicMode, stage: str) -> Tuple[str, str]:
    """Load a prompt template for the given epistemic mode.
    
    Args:
        mode: EpistemicMode.CONSTRUCTIVIST or EpistemicMode.POST_POSITIVIST
        stage: "open_coding" | "axial_coding" | "discovery" | "selective" | "memo"
    
    Returns:
        Tuple[prompt_text, prompt_version]
        
    Raises:
        FileNotFoundError: if no prompt exists (even fallback)
    """
    filename = STAGE_TO_FILE.get(stage, f"{stage}.txt")
    mode_dir = PROMPTS_DIR / mode.value
    prompt_file = mode_dir / filename
    
    # Intento primario
    if prompt_file.exists():
        text = prompt_file.read_text(encoding="utf-8")
        version = f"{mode.value}_{stage}_v1"
        return text, version
    
    # Fallback a constructivista con warning auditado
    fallback_file = PROMPTS_DIR / "constructivist" / filename
    if fallback_file.exists():
        _logger.warning(
            "prompt.fallback",
            requested_mode=mode.value,
            stage=stage,
            fallback_to="constructivist",
            reason="prompt_file_missing",
        )
        text = fallback_file.read_text(encoding="utf-8")
        version = f"fallback_constructivist_{stage}_v1"
        return text, version
    
    raise FileNotFoundError(f"No prompt found for stage '{stage}' in any mode")


def get_system_prompt(mode: EpistemicMode, stage: str) -> Tuple[str, str]:
    """Build complete system prompt combining base + stage-specific.
    
    Args:
        mode: EpistemicMode
        stage: "open_coding" | "axial_coding" | "discovery" | "selective"
    
    Returns:
        Tuple[complete_prompt, prompt_version]
    """
    base_text, base_version = load_prompt(mode, "system_base")
    stage_text, stage_version = load_prompt(mode, stage)
    
    combined = f"{base_text}\n\n---\n\n{stage_text}"
    version = f"{base_version}+{stage_version}"
    
    return combined, version
```

### 2.5 Funciones PostgreSQL (`app/postgres_block.py`)

```python
from app.settings import EpistemicMode

def get_project_epistemic_mode(pg: PGConnection, project_id: str) -> EpistemicMode:
    """Get the epistemic mode configured for a project."""
    query = "SELECT epistemic_mode FROM pg_proyectos WHERE id = %s"
    with pg.cursor() as cur:
        cur.execute(query, (project_id,))
        row = cur.fetchone()
        if row and row[0]:
            return EpistemicMode.from_string(row[0])
    return EpistemicMode.CONSTRUCTIVIST


def set_project_epistemic_mode(
    pg: PGConnection, 
    project_id: str, 
    mode: EpistemicMode
) -> Tuple[bool, str]:
    """Set epistemic mode for a project.
    
    Returns:
        Tuple[success, message]
        
    Fails if project already has axial relations (lock enforcement).
    """
    # Check for existing axial relations (lock de modo)
    check_axial = """
        SELECT COUNT(*) FROM axial_relationships 
        WHERE project_id = %s
    """
    with pg.cursor() as cur:
        cur.execute(check_axial, (project_id,))
        axial_count = cur.fetchone()[0]
        
        if axial_count > 0:
            return False, f"Cannot change epistemic_mode: project has {axial_count} axial relations"
        
        # Safe to update
        update = """
            UPDATE pg_proyectos 
            SET epistemic_mode = %s, updated_at = NOW()
            WHERE id = %s
        """
        cur.execute(update, (mode.value, project_id))
        pg.commit()
        
        return True, f"epistemic_mode set to {mode.value}"
```

### 2.6 Integración en `app/analysis.py`

```python
from app.prompts.loader import get_system_prompt
from app.postgres_block import get_project_epistemic_mode

async def analyze_interview_text(
    pg: PGConnection,
    project_id: str,
    text: str,
    ...
) -> Dict[str, Any]:
    # Cargar modo epistemológico del proyecto
    mode = get_project_epistemic_mode(pg, project_id)
    
    # Obtener prompt diferenciado con version para audit
    system_prompt, prompt_version = get_system_prompt(mode, "open_coding")
    
    # ... llamada a LLM con system_prompt ...
    
    # Agregar metadata de auditoría
    result["_meta"] = {
        "epistemic_mode": mode.value,
        "prompt_version": prompt_version,
        "analysis_schema_version": ANALYSIS_MEMO_SCHEMA_VERSION,
    }
    
    return result
```

---

## 3. Definition of Done (consolidado)

| # | Criterio | Verificación |
|---|----------|--------------|
| 1 | `epistemic_mode` existe en `pg_proyectos` | `SELECT epistemic_mode FROM pg_proyectos LIMIT 1` no falla |
| 2 | API expone modo | `GET /api/projects/{id}` incluye `epistemic_mode` |
| 3 | API permite cambiar modo | `PATCH /api/projects/{id}` acepta `epistemic_mode` |
| 4 | Lock backend | `PATCH` con axial relations existentes → 409 |
| 5 | Prompts diferenciados | Archivos existen en `app/prompts/{mode}/` |
| 6 | Fallback auditado | Log `prompt.fallback` cuando aplica |
| 7 | Audit trail | Response incluye `epistemic_mode` + `prompt_version` |
| 8 | Test de diferenciación | Prompt constructivista contiene "gerundio"; post_positivist contiene "sustantivo" |

---

## 4. Tickets de implementación

---

### TICKET-EM01: Schema + Config + API

**Prioridad:** P0  
**Estimación:** 3 horas  
**Archivos:** `migrations/017_epistemic_mode.sql`, `app/settings.py`, `app/postgres_block.py`, `backend/routers/projects.py`

#### Descripción
Agregar columna `epistemic_mode` a `pg_proyectos` y exponer en API.

#### Checklist de implementación

- [ ] **Migración SQL**
  - [ ] Crear `migrations/017_epistemic_mode.sql`
  - [ ] ALTER TABLE con CHECK constraint
  - [ ] Índice para queries
  - [ ] Aplicar en desarrollo

- [ ] **Enum en settings.py**
  - [ ] Definir `EpistemicMode(str, Enum)`
  - [ ] Método `from_string()` con fallback seguro

- [ ] **Funciones PostgreSQL**
  - [ ] `get_project_epistemic_mode(pg, project_id) -> EpistemicMode`
  - [ ] `set_project_epistemic_mode(pg, project_id, mode) -> Tuple[bool, str]`
  - [ ] Lock enforcement: rechazar si `axial_relationships > 0`

- [ ] **Endpoints API**
  - [ ] `GET /api/projects/{id}` incluye `epistemic_mode`
  - [ ] `PATCH /api/projects/{id}` acepta `epistemic_mode`
  - [ ] Retornar 409 si intenta cambiar con axial existente

- [ ] **Tests**
  - [ ] Test: get_project_epistemic_mode retorna default
  - [ ] Test: set_project_epistemic_mode con proyecto vacío → OK
  - [ ] Test: set_project_epistemic_mode con axial → rechaza
  - [ ] Test: API PATCH → 200/409 según estado

#### Criterio de éxito
```sql
SELECT id, epistemic_mode FROM pg_proyectos;
-- Retorna filas con epistemic_mode = 'constructivist' (default)
```

---

### TICKET-EM02: Prompts Templates + Loader

**Prioridad:** P0  
**Estimación:** 3 horas  
**Archivos:** `app/prompts/` (nuevo directorio)

#### Descripción
Crear estructura de prompts diferenciados y loader con cache + fallback auditado.

#### Checklist de implementación

- [ ] **Estructura de directorios**
  - [ ] `app/prompts/__init__.py`
  - [ ] `app/prompts/loader.py`
  - [ ] `app/prompts/constructivist/`
  - [ ] `app/prompts/post_positivist/`

- [ ] **Loader**
  - [ ] Dict `STAGE_TO_FILE` para mapping explícito
  - [ ] `load_prompt(mode, stage) -> Tuple[text, version]`
  - [ ] `get_system_prompt(mode, stage) -> Tuple[combined, version]`
  - [ ] LRU cache (32 entries)
  - [ ] Warning log en fallback

- [ ] **Templates constructivistas**
  - [ ] `system_base.txt`: principios Charmaz
  - [ ] `open_coding.txt`: gerundios + in-vivo
  - [ ] `axial_coding.txt`: relaciones fluidas
  - [ ] `discovery.txt`: exploración situada
  - [ ] `selective.txt`: teoría emergente
  - [ ] `memo.txt`: reflexivo

- [ ] **Templates post-positivistas**
  - [ ] `system_base.txt`: principios Glaser/Strauss
  - [ ] `open_coding.txt`: abstracción + sustantivos
  - [ ] `axial_coding.txt`: paradigma rígido
  - [ ] `discovery.txt`: patrones
  - [ ] `selective.txt`: teoría formal
  - [ ] `memo.txt`: conceptual

- [ ] **Tests**
  - [ ] Test: load_prompt carga archivo correcto
  - [ ] Test: fallback funciona y loguea
  - [ ] Test: LRU cache reduce I/O
  - [ ] Test: prompt constructivista contiene "gerundio"
  - [ ] Test: prompt post_positivist contiene "sustantivo"

#### Criterio de éxito
```python
text, version = load_prompt(EpistemicMode.CONSTRUCTIVIST, "open_coding")
assert "gerundio" in text.lower()
assert version == "constructivist_open_coding_v1"
```

---

### TICKET-EM03: Integración analysis.py + Audit Trail

**Prioridad:** P0  
**Estimación:** 2 horas  
**Archivos:** `app/analysis.py`, `app/discovery.py` (si aplica)

#### Descripción
Integrar loader de prompts en flujos de análisis y agregar metadata de auditoría.

#### Checklist de implementación

- [ ] **Modificar `analyze_interview_text()`**
  - [ ] Importar `get_system_prompt`, `get_project_epistemic_mode`
  - [ ] Obtener modo del proyecto
  - [ ] Usar prompt diferenciado
  - [ ] Agregar `_meta` con `epistemic_mode` + `prompt_version`

- [ ] **Modificar Discovery (si aplica)**
  - [ ] `synthesize_discovery_results()` usa prompt por modo
  - [ ] Metadata de auditoría

- [ ] **Logging**
  - [ ] `analysis.started` incluye `epistemic_mode`
  - [ ] `analysis.completed` incluye `prompt_version`

- [ ] **Backward compatibility**
  - [ ] Si proyecto no tiene modo → usar CONSTRUCTIVIST
  - [ ] Response shape no cambia (solo agrega `_meta`)

- [ ] **Tests**
  - [ ] Test: análisis con proyecto constructivista usa prompt correcto
  - [ ] Test: response incluye `_meta.epistemic_mode`
  - [ ] Test: response incluye `_meta.prompt_version`

#### Criterio de éxito
```python
result = await analyze_interview_text(pg, project_id, text)
assert result["_meta"]["epistemic_mode"] == "constructivist"
assert "open_coding" in result["_meta"]["prompt_version"]
```

---

### TICKET-EM04: UI Selector + Badge (Opcional, post-EM03)

**Prioridad:** P1  
**Estimación:** 2 horas  
**Archivos:** `frontend/src/components/ProjectSettings.tsx`, `frontend/src/components/common/EpistemicBadge.tsx`

#### Descripción
Agregar selector de modo en configuración de proyecto y badge indicador en paneles.

#### Checklist de implementación

- [ ] **Componente selector**
  - [ ] Radio group con 2 opciones
  - [ ] Descripción breve de cada modo
  - [ ] Disabled si proyecto tiene axial (feedback visual)

- [ ] **Badge indicador**
  - [ ] `EpistemicModeBadge.tsx`
  - [ ] Purple para constructivista, Blue para post-positivist
  - [ ] Tooltip con descripción

- [ ] **Integrar en paneles**
  - [ ] `AnalysisPanel.tsx`
  - [ ] `CodingPanel.tsx`
  - [ ] `DiscoveryPanel.tsx`

- [ ] **API calls**
  - [ ] `patchProject({ epistemic_mode })` en `api.ts`
  - [ ] Handle 409 con mensaje claro

- [ ] **Tests E2E**
  - [ ] Test: selector visible en nuevo proyecto
  - [ ] Test: selector disabled después de axial
  - [ ] Test: badge refleja modo correcto

#### Criterio de éxito
Usuario puede seleccionar modo al crear proyecto y ve badge en todos los paneles.

---

### TICKET-EM05: Documentación

**Prioridad:** P2  
**Estimación:** 1 hora  
**Archivos:** `docs/02-metodologia/`, `README.md`

#### Descripción
Documentar diferencias entre modos y guía de selección.

#### Checklist de implementación

- [ ] **Guía de selección**
  - [ ] Cuándo usar constructivista
  - [ ] Cuándo usar post-positivista
  - [ ] Implicaciones en códigos y memos

- [ ] **Actualizar matriz epistemológica**
  - [ ] Agregar columna "Modo sistema"
  - [ ] Mapear decisiones a modo

- [ ] **README**
  - [ ] Sección "Modos epistemológicos"
  - [ ] Link a guía detallada

---

## 5. Orden de ejecución

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEPENDENCY GRAPH                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TICKET-EM01 ──────┐                                            │
│  (Schema + API)    │                                            │
│                    ├──► TICKET-EM03 ──► TICKET-EM04 (opcional)  │
│  TICKET-EM02 ──────┘    (Integration)   (UI)                    │
│  (Prompts)                    │                                 │
│                               ▼                                 │
│                         TICKET-EM05                             │
│                         (Docs)                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Paralelo:** EM01 y EM02 pueden hacerse en paralelo.  
**Secuencial:** EM03 requiere EM01 + EM02. EM04/EM05 requieren EM03.

---

## 6. Tracking

| Ticket | Estado | Inicio | Fin | Notas |
|--------|--------|--------|-----|-------|
| TICKET-EM01 | ⬜ NOT STARTED | — | — | Schema + API |
| TICKET-EM02 | ⬜ NOT STARTED | — | — | Prompts + Loader |
| TICKET-EM03 | ⬜ NOT STARTED | — | — | Integración analysis.py |
| TICKET-EM04 | ⬜ NOT STARTED | — | — | UI (opcional) |
| TICKET-EM05 | ⬜ NOT STARTED | — | — | Documentación |

---

*Documento consolidado: 23 Enero 2026*
