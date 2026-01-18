# Sprint 17: Sugerencia de Acción con IA para Codificación

**Fecha inicio:** 2025-12-27  
**Fecha fin:** 2025-12-27  
**Duración real:** ~1.5h desarrollo  
**Estado:** ✅ COMPLETADO  
**Dependencias:** Sprint 15 (Gates GraphRAG), Sprint 16 (Hardening)

---

## Objetivo

Implementar un flujo de "Sugerencia de Acción" donde el sistema:
1. Muestra fragmentos similares con scores
2. Sugiere código(s) basado en patrones semánticos
3. Genera memo IA explicando el agrupamiento
4. Permite selección múltiple de fragmentos
5. Envía todo a la **Bandeja de Códigos Candidatos** para validación

---

## Mockup de la Feature

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 💡 SUGERENCIA DE ACCIÓN                                                     │
│                                                                              │
│ Basado en los 5 fragmentos similares encontrados, te sugiero:               │
│                                                                              │
│ 📝 Código propuesto: [proyecto_radicar        ] ←── editable               │
│                                                                              │
│ 📋 Fragmentos seleccionados:                                                │
│ ☑ [1] 0.87 | "...224 familias que necesitamos..." | entrevista_01.docx     │
│ ☑ [2] 0.82 | "...quedarse aquí mismo..."         | entrevista_03.docx     │
│ ☑ [3] 0.78 | "...el riesgo de desalojo..."       | entrevista_05.docx     │
│ ☑ [4] 0.71 | "...organización comunitaria..."    | entrevista_02.docx     │
│ ☐ [5] 0.65 | "...defensa del territorio..."      | entrevista_04.docx     │
│                                                                              │
│ 📝 Memo IA (editable):                                                       │
│ ┌──────────────────────────────────────────────────────────────────────────┐│
│ │ Este código agrupa tanto la planificación técnica (224 familias)         ││
│ │ como la defensa territorial (quedarse 'aquí mismo'). El riesgo de        ││
│ │ desalojo actúa como catalizador para la organización en torno a          ││
│ │ la radicación.                                                           ││
│ └──────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│ [✓ Enviar a Bandeja (4)] [🔄 Regenerar memo] [✕ Cancelar]                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Tabla Resumen de Epics

| Epic | Descripción | Esfuerzo | Estado |
|------|-------------|----------|--------|
| E1 | Endpoint batch para candidatos | 1h | ✅ |
| E2 | Sugerencia de código IA | 2h | ✅ |
| E3 | Frontend: Selección múltiple | 2h | ✅ |
| E4 | Frontend: ActionSuggestionCard | 2h | ✅ |
| E5 | Integración y testing | 1h | ✅ |

**Total estimado:** 8h → **Completado:** ~1.5h

---

## E1: Endpoint Batch para Candidatos (1h)

### Archivo: `backend/app.py`

**Request:**
```python
class BatchCandidateRequest(BaseModel):
    project: str
    codigo: str
    memo: Optional[str] = None
    fragments: List[FragmentSelection]  # fragmento_id, archivo, cita, score

class FragmentSelection(BaseModel):
    fragmento_id: str
    archivo: str
    cita: str
    score: float
```

**Endpoint:**
```python
@app.post("/api/codes/candidates/batch")
async def api_submit_candidates_batch(payload: BatchCandidateRequest):
    candidates = [
        {
            "project_id": payload.project,
            "codigo": payload.codigo,
            "cita": frag.cita,
            "fragmento_id": frag.fragmento_id,
            "archivo": frag.archivo,
            "fuente_origen": "semantic_suggestion",
            "fuente_detalle": "Sugerencia de Acción IA",
            "memo": payload.memo,
            "score_confianza": frag.score,
        }
        for frag in payload.fragments
    ]
    count = insert_candidate_codes(clients.postgres, candidates)
    return {"submitted": count, "codigo": payload.codigo}
```

**Criterios de aceptación:**
- [ ] Acepta lista de fragmentos
- [ ] Inserta todos en `codigo_candidatos`
- [ ] Retorna conteo de insertados

---

## E2: Sugerencia de Código IA (2h)

### Archivo: `app/coding.py`

**Nueva función:**
```python
def suggest_code_from_fragments(
    clients: ServiceClients,
    settings: AppSettings,
    fragments: List[Dict[str, Any]],
    existing_codes: List[str],
    llm_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sugiere nombre de código y memo basado en fragmentos.
    
    Returns:
        - suggested_code: Nombre propuesto
        - memo: Justificación del agrupamiento
        - confidence: alta/media/baja
    """
```

**Prompt IA:**
```
Analiza los siguientes fragmentos de entrevistas y propón:
1. UN nombre de código que agrupe el tema central (2-4 palabras, snake_case)
2. Un memo de 2-3 oraciones explicando la convergencia temática

Fragmentos:
[1] "...224 familias que necesitamos..."
[2] "...quedarse aquí mismo..."
...

Códigos existentes en el proyecto (evitar duplicados):
- resiliencia_comunitaria
- participacion_vecinal
...

Responde en JSON:
{"suggested_code": "...", "memo": "...", "confidence": "alta|media|baja"}
```

**Criterios de aceptación:**
- [ ] Genera nombre de código coherente
- [ ] Memo explica convergencia
- [ ] Evita códigos duplicados

---

## E3: Frontend - Selección Múltiple (2h)

### Archivo: `frontend/src/components/CodingPanel.tsx`

**Cambios:**
1. Agregar estado `selectedSuggestions: Set<string>`
2. Agregar checkboxes a cada sugerencia
3. Mostrar contador de seleccionados
4. Botón "Seleccionar todos" / "Deseleccionar todos"

```tsx
const [selectedSuggestions, setSelectedSuggestions] = useState<Set<string>>(new Set());

const toggleSelection = (fragmentId: string) => {
  setSelectedSuggestions(prev => {
    const next = new Set(prev);
    if (next.has(fragmentId)) next.delete(fragmentId);
    else next.add(fragmentId);
    return next;
  });
};
```

**Criterios de aceptación:**
- [ ] Checkboxes funcionales
- [ ] Estado persiste entre renders
- [ ] Selección/deselección múltiple

---

## E4: Frontend - ActionSuggestionCard (2h)

### Nuevo componente: `frontend/src/components/ActionSuggestionCard.tsx`

```tsx
interface ActionSuggestionCardProps {
  suggestedCode: string;
  memo: string;
  selectedFragments: CodingSuggestion[];
  onCodeChange: (code: string) => void;
  onMemoChange: (memo: string) => void;
  onSubmit: () => void;
  onRegenerate: () => void;
  onCancel: () => void;
  isSubmitting: boolean;
}

export function ActionSuggestionCard({...}: ActionSuggestionCardProps) {
  return (
    <div className="action-suggestion-card">
      <header>
        <span>💡</span>
        <h3>Sugerencia de Acción</h3>
      </header>
      
      <div className="code-input">
        <label>Código propuesto:</label>
        <input 
          value={suggestedCode} 
          onChange={e => onCodeChange(e.target.value)}
        />
      </div>
      
      <div className="memo-editor">
        <label>Memo IA:</label>
        <textarea 
          value={memo}
          onChange={e => onMemoChange(e.target.value)}
          rows={4}
        />
      </div>
      
      <footer>
        <button onClick={onSubmit} disabled={isSubmitting}>
          ✓ Enviar a Bandeja ({selectedFragments.length})
        </button>
        <button onClick={onRegenerate}>🔄 Regenerar</button>
        <button onClick={onCancel}>✕ Cancelar</button>
      </footer>
    </div>
  );
}
```

**Criterios de aceptación:**
- [ ] Card con diseño consistente
- [ ] Código y memo editables
- [ ] Botones funcionales
- [ ] Loading state

---

## E5: Integración y Testing (1h)

### Flujo completo:

1. Usuario selecciona fragmento semilla
2. Click "Buscar similares" → llama `/api/coding/suggest` con `llm_model`
3. Backend retorna `suggestions` + `llm_summary` + `suggested_code`
4. Frontend muestra `ActionSuggestionCard`
5. Usuario selecciona fragmentos (checkboxes)
6. Usuario edita código/memo si desea
7. Click "Enviar a Bandeja" → llama `/api/codes/candidates/batch`
8. Confirmación + actualizar stats

**Tests:**
- [ ] E2E: Flujo completo desde semilla hasta bandeja
- [ ] Unit: `suggest_code_from_fragments()`
- [ ] Unit: `ActionSuggestionCard` render

---

## Archivos a Modificar/Crear

| Archivo | Tipo | Cambio |
|---------|------|--------|
| `backend/app.py` | MOD | Endpoint `/api/codes/candidates/batch` |
| `app/coding.py` | MOD | `suggest_code_from_fragments()` |
| `frontend/src/components/CodingPanel.tsx` | MOD | Selección múltiple + integración |
| `frontend/src/components/ActionSuggestionCard.tsx` | NEW | Componente de sugerencia |
| `frontend/src/index.css` | MOD | Estilos para card |

---

## Verificación Final

- [ ] Seleccionar fragmento semilla → muestra similares con scores
- [ ] Click "Generar sugerencia" → muestra ActionSuggestionCard
- [ ] Seleccionar 3+ fragmentos → checkboxes funcionan
- [ ] Editar código y memo → cambios reflejados
- [ ] "Enviar a Bandeja" → items aparecen en bandeja de candidatos
- [ ] Bandeja muestra origen "semantic_suggestion"

---

## Próximos Sprints

- **Sprint 18:** Verificador LLM (segunda capa anti-alucinaciones)
- **Sprint 19:** Dashboard de métricas GraphRAG
- **Sprint 20:** Chat Enterprise (frontend conversacional)
