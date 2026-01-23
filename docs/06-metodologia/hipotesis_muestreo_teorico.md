# Implementación de Hipótesis para Muestreo Teórico

> **Documento de Diseño Técnico**  
> **Fecha:** Enero 2026  
> **Sprint:** 32 - Validación Metodológica

---

## 1. Contexto del Problema

### 1.1 Situación Actual

Los candidatos generados por `link_prediction` tienen características especiales:

| Atributo | Valor | Problema Metodológico |
|----------|-------|----------------------|
| `fuente_origen` | `link_prediction` | ✅ Correcto |
| `fragmento_id` | `NULL` o `''` | ⚠️ **Sin evidencia empírica** |
| `cita` | "Relación sugerida: X → Y" | ⚠️ Generada, no observada |
| `estado` | `validado` | ❌ **Violación metodológica** |

### 1.2 Principio Violado

Según Grounded Theory (Glaser & Strauss, 1967; Charmaz, 2014):

> "Grounded theory is defined as the **discovery of theory from data**... purposefully named to describe its intent to **ground theory in empirical research**."

> "**Theoretical sampling** means sampling to develop or refine emerging theoretical categories... keeps them **grounded in data**."

Un código sin `fragmento_id` **no puede ser "validado"** porque no hay evidencia empírica que lo respalde.

---

## 2. Solución: Estado `hipotesis`

### 2.1 Nuevo Estado en el Flujo

```
                        ┌──────────────────────────────────────┐
                        │     FLUJO DE CÓDIGOS CANDIDATOS      │
                        └──────────────────────────────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
    ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
    │   fuente_origen │      │   fuente_origen │      │   fuente_origen │
    │       = LLM     │      │    = manual     │      │ = link_prediction│
    │   CON fragmento │      │   CON fragmento │      │   SIN fragmento  │
    └────────┬────────┘      └────────┬────────┘      └────────┬────────┘
             │                        │                        │
             ▼                        ▼                        ▼
    ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
    │    pendiente    │      │    pendiente    │      │  ⭐ hipotesis   │
    │  (tiene cita)   │      │  (tiene cita)   │      │ (sin evidencia) │
    └────────┬────────┘      └────────┬────────┘      └────────┬────────┘
             │                        │                        │
             │     Validación         │                        │
             │     del Investigador   │                        │
             ▼                        ▼                        ▼
    ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
    │    validado     │      │    validado     │      │ Muestreo Teórico│
    │                 │      │                 │      │                 │
    └────────┬────────┘      └────────┬────────┘      │ → Buscar        │
             │                        │               │   evidencia     │
             ▼                        ▼               │ → Vincular      │
    ┌─────────────────────────────────────────┐      │   fragmento     │
    │           LISTA DEFINITIVA              │      └────────┬────────┘
    │         (promote_to_definitive)         │               │
    └─────────────────────────────────────────┘               │
                              ▲                               │
                              │          Si encuentra         │
                              │          evidencia            │
                              └───────────────────────────────┘
```

### 2.2 Definición Semántica

| Estado | Significado | Tiene `fragmento_id` | Acción del Investigador |
|--------|-------------|---------------------|------------------------|
| `pendiente` | Código propuesto con evidencia, esperando revisión | ✅ SÍ | Validar o rechazar |
| `hipotesis` | **Proposición teórica sin evidencia empírica** | ❌ NO | Realizar muestreo teórico |
| `validado` | Código confirmado con evidencia | ✅ SÍ | Promover a definitivo |
| `rechazado` | Código descartado | N/A | Ninguna |
| `fusionado` | Código consolidado en otro | N/A | Ninguna |

### 2.3 Justificación Metodológica

El estado `hipotesis` implementa el concepto de **razonamiento abductivo** en Grounded Theory:

> "Grounded theory is an inductive—or perhaps more accurately—an **abductive method** aimed at generating theory from empirical data" (Babchuk & Boswell, 2023)

Las hipótesis son **proposiciones tentativas** que:
1. Emergen del análisis estructural del grafo (centralidad, comunidades)
2. Sugieren relaciones posibles entre conceptos
3. **Requieren validación empírica** antes de ser aceptadas

---

## 3. Implementación Técnica

### 3.1 Migración de Base de Datos

```sql
-- Migration 012: Add 'hipotesis' state and related fields
-- Fecha: 2026-01-18

-- 1. Permitir nuevo estado en CHECK constraint (si existe)
-- ALTER TABLE codigos_candidatos 
-- DROP CONSTRAINT IF EXISTS cc_estado_check;

-- 2. Añadir campo para tracking de muestreo teórico
ALTER TABLE codigos_candidatos 
ADD COLUMN IF NOT EXISTS requiere_muestreo BOOLEAN DEFAULT FALSE;

ALTER TABLE codigos_candidatos 
ADD COLUMN IF NOT EXISTS muestreo_notas TEXT;

ALTER TABLE codigos_candidatos 
ADD COLUMN IF NOT EXISTS codigo_origen_hipotesis TEXT;

-- 3. Marcar candidatos existentes de link_prediction como hipótesis
UPDATE codigos_candidatos 
SET estado = 'hipotesis',
    requiere_muestreo = TRUE,
    memo = COALESCE(memo, '') || ' [RECLASIFICADO: Hipótesis pendiente de muestreo teórico]'
WHERE fuente_origen = 'link_prediction'
  AND (fragmento_id IS NULL OR fragmento_id = '')
  AND estado IN ('validado', 'pendiente');

-- 4. Índice para consultas de hipótesis
CREATE INDEX IF NOT EXISTS ix_cc_hipotesis 
ON codigos_candidatos(project_id, estado) 
WHERE estado = 'hipotesis';
```

### 3.2 Cambios en Backend (`app/postgres_block.py`)

```python
# Añadir nuevo estado a la documentación
CandidateCodeRow = Tuple[
    str,  # project_id
    str,  # codigo
    Optional[str],  # cita
    Optional[str],  # fragmento_id
    Optional[str],  # archivo
    str,  # fuente_origen: 'llm', 'manual', 'discovery', 'semantic_suggestion', 'link_prediction'
    Optional[str],  # fuente_detalle
    Optional[float],  # score_confianza
    str,  # estado: 'pendiente', 'hipotesis', 'validado', 'rechazado', 'fusionado'
    Optional[str],  # memo
]

# Nueva función para listar hipótesis
def list_hypothesis_codes(
    pg: PGConnection,
    project: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Lista códigos en estado 'hipotesis' que requieren muestreo teórico.
    
    En Grounded Theory, estas son proposiciones emergentes que necesitan
    validación empírica antes de ser aceptadas como códigos definitivos.
    """
    ensure_candidate_codes_table(pg)
    
    sql = """
    SELECT id, codigo, cita, fuente_detalle, score_confianza, 
           muestreo_notas, codigo_origen_hipotesis, created_at
    FROM codigos_candidatos
    WHERE project_id = %s 
      AND estado = 'hipotesis'
      AND requiere_muestreo = TRUE
    ORDER BY score_confianza DESC NULLS LAST, created_at DESC
    LIMIT %s
    """
    with pg.cursor() as cur:
        cur.execute(sql, (project, limit))
        rows = cur.fetchall()
    
    return [
        {
            "id": r[0],
            "codigo": r[1],
            "cita": r[2],
            "fuente_detalle": r[3],
            "score_confianza": r[4],
            "muestreo_notas": r[5],
            "codigo_origen": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
        }
        for r in rows
    ]


def validate_hypothesis_with_evidence(
    pg: PGConnection,
    hypothesis_id: int,
    project: str,
    fragmento_id: str,
    cita: str,
    validado_por: str = "investigador",
) -> Dict[str, Any]:
    """
    Valida una hipótesis vinculándola a evidencia empírica.
    
    Este es el paso final del muestreo teórico: la hipótesis
    se convierte en código validado al encontrar un fragmento
    que la respalda.
    
    Args:
        pg: Conexión PostgreSQL
        hypothesis_id: ID del candidato en estado 'hipotesis'
        project: ID del proyecto
        fragmento_id: ID del fragmento que respalda la hipótesis
        cita: Cita textual del fragmento
        validado_por: Usuario que realiza la validación
    
    Returns:
        Dict con resultado de la operación
    """
    if not fragmento_id or len(fragmento_id) < 10:
        raise ValueError("Se requiere un fragmento_id válido para validar la hipótesis")
    
    sql = """
    UPDATE codigos_candidatos
    SET estado = 'validado',
        fragmento_id = %s,
        cita = %s,
        requiere_muestreo = FALSE,
        validado_por = %s,
        validado_en = NOW(),
        memo = COALESCE(memo, '') || ' [VALIDADO: Evidencia encontrada via muestreo teórico]',
        updated_at = NOW()
    WHERE id = %s 
      AND project_id = %s 
      AND estado = 'hipotesis'
    RETURNING id, codigo, fragmento_id
    """
    with pg.cursor() as cur:
        cur.execute(sql, (fragmento_id, cita, validado_por, hypothesis_id, project))
        result = cur.fetchone()
    pg.commit()
    
    if not result:
        raise ValueError(f"Hipótesis {hypothesis_id} no encontrada o no está en estado 'hipotesis'")
    
    return {
        "success": True,
        "id": result[0],
        "codigo": result[1],
        "fragmento_id": result[2],
        "message": "Hipótesis validada con evidencia empírica"
    }


def reject_hypothesis(
    pg: PGConnection,
    hypothesis_id: int,
    project: str,
    razon: str,
) -> Dict[str, Any]:
    """
    Rechaza una hipótesis después de muestreo teórico fallido.
    
    Se debe proporcionar una razón metodológica del rechazo.
    """
    sql = """
    UPDATE codigos_candidatos
    SET estado = 'rechazado',
        requiere_muestreo = FALSE,
        memo = COALESCE(memo, '') || ' [RECHAZADO - Muestreo teórico: ' || %s || ']',
        updated_at = NOW()
    WHERE id = %s 
      AND project_id = %s 
      AND estado = 'hipotesis'
    RETURNING id, codigo
    """
    with pg.cursor() as cur:
        cur.execute(sql, (razon, hypothesis_id, project))
        result = cur.fetchone()
    pg.commit()
    
    if not result:
        raise ValueError(f"Hipótesis {hypothesis_id} no encontrada")
    
    return {
        "success": True,
        "id": result[0],
        "codigo": result[1],
        "message": f"Hipótesis rechazada: {razon}"
    }
```

### 3.3 Cambios en Frontend

#### 3.3.1 Nuevo componente: `HypothesisValidationPanel.tsx`

```tsx
/**
 * Panel de Validación de Hipótesis (Muestreo Teórico)
 * 
 * Implementa el flujo de Grounded Theory donde:
 * 1. El investigador ve hipótesis sugeridas por link_prediction
 * 2. Busca fragmentos que respalden la hipótesis
 * 3. Vincula la evidencia para validar, o rechaza por falta de datos
 */

interface HypothesisValidationPanelProps {
    project: string;
}

export function HypothesisValidationPanel({ project }: HypothesisValidationPanelProps) {
    // Estados para lista de hipótesis, búsqueda de fragmentos, etc.
    
    return (
        <div className="hypothesis-panel">
            <header>
                <h3>🔬 Muestreo Teórico - Validación de Hipótesis</h3>
                <p>
                    Estas son proposiciones emergentes del análisis estructural.
                    Busca evidencia en los fragmentos para validarlas o recházalas.
                </p>
            </header>
            
            {/* Lista de hipótesis con acciones */}
            {/* Buscador de fragmentos relacionados */}
            {/* Modal de vinculación fragmento → hipótesis */}
        </div>
    );
}
```

#### 3.3.2 Actualizar `CodeValidationPanel.tsx`

Añadir nuevo estado `hipotesis` al diccionario de estados:

```tsx
const ESTADO_LABELS: Record<string, { label: string; color: string }> = {
    pendiente: { label: "⏳ Pendiente", color: "#f59e0b" },
    hipotesis: { label: "🔬 Hipótesis", color: "#8b5cf6" },  // NUEVO
    validado: { label: "✅ Validado", color: "#10b981" },
    rechazado: { label: "❌ Rechazado", color: "#ef4444" },
    fusionado: { label: "🔗 Fusionado", color: "#6366f1" },
};
```

### 3.4 Nuevo Endpoint API

```python
# backend/app.py

@app.post("/api/codes/candidates/{hypothesis_id}/validate-with-evidence")
async def validate_hypothesis_with_evidence_endpoint(
    hypothesis_id: int,
    request: Request,
    project: str = Query(...),
):
    """
    Valida una hipótesis vinculándola a un fragmento con evidencia empírica.
    
    Body:
        fragmento_id: str - ID del fragmento que respalda la hipótesis
        cita: str - Cita textual del fragmento
    """
    data = await request.json()
    fragmento_id = data.get("fragmento_id")
    cita = data.get("cita")
    
    if not fragmento_id:
        raise HTTPException(400, "Se requiere fragmento_id")
    
    result = validate_hypothesis_with_evidence(
        pg=request.state.clients.postgres,
        hypothesis_id=hypothesis_id,
        project=project,
        fragmento_id=fragmento_id,
        cita=cita,
    )
    return result
```

---

## 4. Flujo de Trabajo del Investigador

### 4.1 Panel de Hipótesis

```
┌────────────────────────────────────────────────────────────────────────────┐
│  🔬 MUESTREO TEÓRICO - HIPÓTESIS PENDIENTES                    [3 items]  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ 📊 rol_dirigencial                                    Score: 1.0    │  │
│  │                                                                      │  │
│  │ "Relación sugerida: participacion_ciudadana → rol_dirigencial"      │  │
│  │                                                                      │  │
│  │ Algoritmo: common_neighbors                                          │  │
│  │                                                                      │  │
│  │ 💡 Sugerencia de búsqueda:                                          │  │
│  │    "Buscar fragmentos donde participantes hablen sobre liderazgo    │  │
│  │     en contexto de participación ciudadana"                          │  │
│  │                                                                      │  │
│  │  [🔍 Buscar Evidencia]  [📋 Ver Fragmentos Relacionados]  [❌ Rechazar] │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ... más hipótesis ...                                                     │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Búsqueda de Evidencia (Muestreo Teórico)

Al hacer clic en "Buscar Evidencia":

1. El sistema consulta Qdrant con el código como query semántica
2. Muestra los fragmentos más relacionados
3. El investigador selecciona el fragmento que respalda la hipótesis
4. El sistema vincula el fragmento y cambia estado a `validado`

---

## 5. Beneficios de Esta Implementación

| Aspecto | Antes | Después |
|---------|-------|---------|
| **Rigor metodológico** | Códigos sin evidencia marcados como "validados" | Separación clara entre hipótesis y evidencia |
| **Trazabilidad** | No se sabía qué códigos necesitaban evidencia | Campo `requiere_muestreo` identifica pendientes |
| **Flujo de trabajo** | Validación automática sin revisión | Muestreo teórico guiado para hipótesis |
| **Auditabilidad** | No se registraba el proceso de validación | Memo documenta cada paso |

---

## 6. Referencias Metodológicas

1. Glaser, B. G., & Strauss, A. L. (1967). *The Discovery of Grounded Theory*
2. Charmaz, K. (2014). *Constructing Grounded Theory* (2nd ed.)
3. Strauss, A., & Corbin, J. (1998). *Basics of Qualitative Research*
4. Babchuk, W., & Boswell, E. (2023). "Grounded Theory" in *International Encyclopedia of Education*

---

## 7. Checklist de Implementación

- [ ] Crear migración 012 para nuevos campos
- [ ] Actualizar `postgres_block.py` con funciones de hipótesis
- [ ] Añadir endpoints en `backend/app.py`
- [ ] Crear `HypothesisValidationPanel.tsx`
- [ ] Actualizar `CodeValidationPanel.tsx` con nuevo estado
- [ ] Reclasificar candidatos existentes de link_prediction
- [ ] Documentar en manual de usuario
- [ ] Añadir tests E2E

---

*Documento creado: Enero 2026*
