# Propuesta: `epistemic_mode` por proyecto + prompts diferenciados

> **Fecha:** 23 Enero 2026  
> **Estado:** PROPUESTA (pendiente priorización)  
> **Dependencias:** Fase 1.5 Core completada ✅  
> **Estimación:** 8-12 horas (2-3 sesiones)

---

## 1. Motivación

El sistema actual opera con un único prompt (`QUAL_SYSTEM_PROMPT` en `app/analysis.py`) que mezcla elementos de ambos paradigmas metodológicos. Esto genera:

1. **Inconsistencia metodológica:** códigos a veces usan gerundios (Charmaz), a veces sustantivos abstractos (Glaser/Strauss)
2. **Memos homogéneos:** sin distinción entre reflexividad (constructivista) y conceptualización (post-positivista)
3. **Axialidad rígida:** el paradigma relacional actual (causa/condición/consecuencia/partede) es más afín al post-positivismo

La literatura base (`docs/fundamentos_teoria/`) documenta diferencias significativas que **sí impactan las salidas analíticas**.

---

## 2. Diferencias operacionalizables

| Dimensión | Post-positivista | Constructivista |
|-----------|------------------|-----------------|
| **Codificación inicial** | Abstracción temprana, sustantivos | **Gerundios + in-vivo** |
| **Formato código** | `presion_infraestructura` | `experimentando_presion` |
| **Memos** | Conceptuales, analíticos | **Reflexivos** (posicionamiento) |
| **Axialidad** | Paradigma rígido (condiciones/acciones/consecuencias) | Categorías fluidas, relacionales |
| **Evidencia** | Validez, confiabilidad | Credibilidad, resonancia |
| **Prompt tone** | "Identifica patrones objetivos" | "Explora cómo construyen significado" |

---

## 3. Diseño propuesto

### 3.1 Schema (PostgreSQL)

```sql
-- migrations/017_epistemic_mode.sql
ALTER TABLE pg_proyectos 
ADD COLUMN IF NOT EXISTS epistemic_mode TEXT 
DEFAULT 'constructivist' 
CHECK (epistemic_mode IN ('constructivist', 'post_positivist'));

COMMENT ON COLUMN pg_proyectos.epistemic_mode IS 
'Modo epistemológico del proyecto: constructivist (Charmaz) o post_positivist (Glaser/Strauss/Corbin)';
```

### 3.2 Configuración (`app/settings.py`)

```python
from enum import Enum

class EpistemicMode(str, Enum):
    CONSTRUCTIVIST = "constructivist"
    POST_POSITIVIST = "post_positivist"

@dataclass
class ProjectSettings:
    project_id: str
    epistemic_mode: EpistemicMode = EpistemicMode.CONSTRUCTIVIST
    # ... otros campos
```

### 3.3 Templates de prompts

**Estructura de archivos:**
```
app/
├── prompts/
│   ├── __init__.py
│   ├── loader.py
│   ├── constructivist/
│   │   ├── system_base.txt
│   │   ├── open_coding.txt
│   │   ├── axial_coding.txt
│   │   ├── memo_reflexivo.txt
│   │   └── discovery_synthesis.txt
│   └── post_positivist/
│       ├── system_base.txt
│       ├── open_coding.txt
│       ├── axial_coding.txt
│       ├── memo_conceptual.txt
│       └── discovery_synthesis.txt
```

**Ejemplo: `prompts/constructivist/open_coding.txt`**
```
Eres un asistente experto en Teoría Fundamentada Constructivista (enfoque Charmaz).

PRINCIPIOS:
- Los códigos deben capturar PROCESOS y ACCIONES usando GERUNDIOS
- Privilegia códigos IN-VIVO (palabras exactas del participante)
- El conocimiento es co-construido; reflexiona sobre tu mediación
- Cada interpretación debe vincularse a evidencia textual

FORMATO DE CÓDIGOS:
- Usar gerundios: "experimentando_presion", "negociando_identidad"
- Incluir códigos in-vivo cuando el participante usa expresiones significativas
- Máximo 3-4 palabras por código

MEMO REFLEXIVO:
- Incluir posicionamiento: ¿desde dónde estoy interpretando?
- Notar interacción: ¿cómo el contexto de la entrevista afecta el dato?
```

**Ejemplo: `prompts/post_positivist/open_coding.txt`**
```
Eres un asistente experto en Teoría Fundamentada (enfoque Glaser/Strauss).

PRINCIPIOS:
- Los códigos deben capturar PATRONES y REGULARIDADES
- Busca abstracción temprana hacia conceptos analíticos
- El objetivo es descubrir la estructura subyacente del fenómeno
- Validez se logra mediante consistencia y parsimonia

FORMATO DE CÓDIGOS:
- Usar sustantivos abstractos: "presion_infraestructura", "identidad_cultural"
- Preferir conceptos analíticos sobre descripciones literales
- Máximo 3-4 palabras por código

MEMO CONCEPTUAL:
- Definición operacional del código
- Propiedades y dimensiones
- Condiciones bajo las cuales ocurre
```

### 3.4 Loader de prompts (`app/prompts/loader.py`)

```python
"""Prompt loader with epistemic mode differentiation."""
from pathlib import Path
from functools import lru_cache
from typing import Optional
from app.settings import EpistemicMode

PROMPTS_DIR = Path(__file__).parent

@lru_cache(maxsize=32)
def load_prompt(mode: EpistemicMode, prompt_name: str) -> str:
    """Load a prompt template for the given epistemic mode.
    
    Args:
        mode: EpistemicMode.CONSTRUCTIVIST or EpistemicMode.POST_POSITIVIST
        prompt_name: e.g., "open_coding", "axial_coding", "discovery_synthesis"
    
    Returns:
        Prompt text
        
    Raises:
        FileNotFoundError: if prompt template doesn't exist
    """
    mode_dir = PROMPTS_DIR / mode.value
    prompt_file = mode_dir / f"{prompt_name}.txt"
    
    if not prompt_file.exists():
        # Fallback to constructivist if specific prompt missing
        fallback = PROMPTS_DIR / "constructivist" / f"{prompt_name}.txt"
        if fallback.exists():
            return fallback.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Prompt not found: {prompt_name} for mode {mode}")
    
    return prompt_file.read_text(encoding="utf-8")


def get_system_prompt(mode: EpistemicMode, stage: str) -> str:
    """Build complete system prompt for a given mode and analysis stage.
    
    Args:
        mode: EpistemicMode
        stage: "open_coding" | "axial_coding" | "discovery" | "selective"
    
    Returns:
        Complete system prompt combining base + stage-specific
    """
    base = load_prompt(mode, "system_base")
    stage_prompt = load_prompt(mode, stage)
    return f"{base}\n\n---\n\n{stage_prompt}"
```

### 3.5 Integración en `app/analysis.py`

```python
from app.prompts.loader import get_system_prompt, EpistemicMode
from app.postgres_block import get_project_epistemic_mode

async def analyze_interview_text(
    pg: PGConnection,
    project_id: str,
    text: str,
    ...
) -> Dict[str, Any]:
    # Cargar modo epistemológico del proyecto
    mode = get_project_epistemic_mode(pg, project_id)
    
    # Obtener prompt diferenciado
    system_prompt = get_system_prompt(mode, "open_coding")
    
    # Agregar metadata de modo al response
    result["epistemic_mode"] = mode.value
    result["prompt_version"] = f"{mode.value}_open_coding_v1"
    ...
```

### 3.6 Función auxiliar en `app/postgres_block.py`

```python
from app.settings import EpistemicMode

def get_project_epistemic_mode(pg: PGConnection, project_id: str) -> EpistemicMode:
    """Get the epistemic mode configured for a project.
    
    Returns:
        EpistemicMode (defaults to CONSTRUCTIVIST if not set)
    """
    query = """
        SELECT epistemic_mode 
        FROM pg_proyectos 
        WHERE id = %s
    """
    with pg.cursor() as cur:
        cur.execute(query, (project_id,))
        row = cur.fetchone()
        if row and row[0]:
            try:
                return EpistemicMode(row[0])
            except ValueError:
                pass
    return EpistemicMode.CONSTRUCTIVIST
```

---

## 4. UI: Selector de modo

### 4.1 En configuración de proyecto

**Archivo:** `frontend/src/components/ProjectSettings.tsx` (nuevo o existente)

```tsx
// Selector de modo epistemológico
<FormControl>
  <FormLabel>Modo Epistemológico</FormLabel>
  <RadioGroup 
    value={project.epistemic_mode} 
    onChange={(e) => updateProject({ epistemic_mode: e.target.value })}
  >
    <Radio value="constructivist">
      <strong>Constructivista (Charmaz)</strong>
      <Text fontSize="sm" color="gray.600">
        Gerundios, in-vivo, memos reflexivos. Recomendado para investigación interpretativa.
      </Text>
    </Radio>
    <Radio value="post_positivist">
      <strong>Post-positivista (Glaser/Strauss)</strong>
      <Text fontSize="sm" color="gray.600">
        Abstracción temprana, patrones, memos conceptuales. Recomendado para estudios estructurales.
      </Text>
    </Radio>
  </RadioGroup>
</FormControl>
```

### 4.2 Indicador visual en paneles

Agregar badge en `AnalysisPanel`, `CodingPanel`, `DiscoveryPanel`:

```tsx
<Badge colorScheme={mode === 'constructivist' ? 'purple' : 'blue'}>
  {mode === 'constructivist' ? '🔮 Constructivista' : '📊 Post-positivista'}
</Badge>
```

---

## 5. Cambios específicos por modo

### 5.1 Codificación abierta

| Aspecto | Constructivista | Post-positivista |
|---------|-----------------|------------------|
| Formato código | Gerundios: `experimentando_X` | Sustantivos: `presion_X` |
| In-vivo | Obligatorio cuando disponible | Opcional |
| Evidencia | `evidence_ids` + reflexión | `evidence_ids` |

### 5.2 Memos (`memo_sintesis`)

| Tipo | Constructivista | Post-positivista |
|------|-----------------|------------------|
| OBSERVATION | Igual (evidencia obligatoria) | Igual |
| INTERPRETATION | + reflexividad ("desde mi posición...") | Analítico puro |
| HYPOTHESIS | Tentativa, situada | Proposición verificable |
| NORMATIVE_INFERENCE | Implicaciones éticas explícitas | Implicaciones prácticas |

### 5.3 Axialidad

| Aspecto | Constructivista | Post-positivista |
|---------|-----------------|------------------|
| Tipos de relación | Flexibles, contextuales | Paradigma rígido (causa/condición/consecuencia) |
| Validación | Resonancia con participantes | Consistencia interna |

---

## 6. Plan de implementación

### Ticket A: Schema + config (2h)
- [ ] Migración `017_epistemic_mode.sql`
- [ ] Enum `EpistemicMode` en `settings.py`
- [ ] Función `get_project_epistemic_mode()` en `postgres_block.py`
- [ ] Endpoint `PATCH /api/projects/{id}` acepta `epistemic_mode`
- [ ] Tests unitarios

### Ticket B: Prompts templates (3h)
- [ ] Crear directorio `app/prompts/`
- [ ] Escribir templates constructivistas (base + 4 stages)
- [ ] Escribir templates post-positivistas (base + 4 stages)
- [ ] Implementar `loader.py` con cache
- [ ] Tests de carga de prompts

### Ticket C: Integración analysis.py (2h)
- [ ] Modificar `analyze_interview_text()` para usar loader
- [ ] Agregar `epistemic_mode` a response metadata
- [ ] Agregar `prompt_version` para auditoría
- [ ] Tests de integración

### Ticket D: UI selector + indicadores (2h)
- [ ] Selector en configuración de proyecto
- [ ] Badge indicador en paneles
- [ ] Tooltip explicativo de diferencias
- [ ] E2E test

### Ticket E: Documentación (1h)
- [ ] Actualizar `README.md` con modos
- [ ] Actualizar matriz de validación epistemológica
- [ ] Guía de usuario: cuándo usar cada modo

---

## 7. Criterios de aceptación

1. **Proyecto nuevo:** al crear proyecto, selector de modo visible (default: constructivist)
2. **Análisis diferenciado:** códigos generados reflejan el modo:
   - Constructivista → gerundios predominan
   - Post-positivista → sustantivos abstractos predominan
3. **Auditoría:** cada análisis registra `epistemic_mode` + `prompt_version`
4. **Consistencia:** modo no puede cambiarse después de iniciar codificación axial
5. **Fallback:** si prompt falta, usar constructivista (default seguro)

---

## 8. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Prompts mal calibrados | Media | Alto | Validar con expertos en GT antes de release |
| Usuarios confundidos por opciones | Baja | Medio | Default sensato + tooltips explicativos |
| Cambio de modo mid-proyecto | Media | Alto | Lock de modo después de primera axialidad |
| Inconsistencia entre modos | Media | Medio | Suite de tests comparativos |

---

## 9. Métricas de éxito

- **Adopción:** % de proyectos que eligen explícitamente un modo (vs default)
- **Consistencia:** ratio gerundios/sustantivos en códigos por modo
- **Satisfacción:** feedback cualitativo de investigadores sobre diferenciación

---

## 10. Decisión pendiente

**¿Implementar ahora o después de Fase 2?**

| Opción | Pros | Contras |
|--------|------|---------|
| **Ahora (post Fase 1.5)** | Diferenciación metodológica desde el inicio | Retrasa Fase 2 (selective coding) |
| **Después de Fase 2** | Fase 2 se beneficia de modos | Acumulación de deuda técnica en prompts |

**Recomendación:** Implementar **Ticket A + B** ahora (schema + prompts), integrar en analysis.py cuando se refactorice para Fase 2.

---

*Documento creado: 23 Enero 2026*
