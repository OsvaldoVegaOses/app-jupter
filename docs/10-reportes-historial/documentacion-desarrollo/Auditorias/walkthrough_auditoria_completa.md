# Auditoría Técnica: Epistemic Mode & Relaciones Ocultas

He completado la revisión exhaustiva de la implementación. Los componentes operan según los requerimientos metodológicos y de seguridad (Sprint Review).

## Resumen de Hallazgos

### 1. Epistemic Mode (Protección de Integridad)
- **Endpoint**: `PUT /api/projects/{project_id}/epistemic-mode` detectado y funcional.
- **Guardias (Locks)**: En `app/postgres_block.py:8183`, la función `set_project_epistemic_mode` implementa bloqueos estrictos:
  - Se bloquea si `analisis_codigos_abiertos` tiene datos.
  - Se bloquea si `codigos_candidatos` tiene datos.
  - Se bloquea si existen relaciones en `analisis_axial` o `link_predictions` con estado `validado`.
- **Resultado**: El sistema impide cambios de paradigma metodológico una vez que la investigación ha avanzado significativamente.

### 2. Separación Discovery vs Ledger (Prevención de Alucinaciones)
- **Confirmación**: `confirm_hidden_relationship` en `app/link_prediction.py:890` NO escribe directamente en Neo4j.
- **Persistencia**: Las relaciones descubiertas se encolan en `analisis_axial` con `estado='pendiente'`.
- **Audit Trail**: Se genera automáticamente un registro en `axial_ai_analyses` vinculando la sugerencia con el análisis de la IA que la propuso.

### 3. Síntesis IA y Grounding de Evidencia
- **Endpoint**: `/api/axial/analyze-hidden-relationships` integra `build_link_prediction_evidence_pack`.
- **Guardrail Epistemológico**: Localizado en `backend/app.py:844-846`. La IA tiene prohibido emitir `OBSERVATION` si no hay `evidence_fragment_ids` presentes; en su lugar, se degrada a `INTERPRETATION`.
- **Presupuesto de Evidencia**: El pack de evidencia equilibra casos positivos y negativos (tensión) para evitar sesgos de confirmación.

### 4. Alineación Frontend
- **TypeScript**: Los tipos en `api.ts` reflejan correctamente `analysis_id`, `persisted` y los contadores de evidencia.
- **UI**: El `HiddenRelationshipsPanel.tsx` muestra métricas de auditoría (cobertura, overlap) y permite la validación batch hacia el ledger.
- **Hooks**: `useProjects.ts` utiliza el endpoint dedicado para asegurar que los locks del servidor sean respetados.

## Estado de Pruebas
- Se han verificado los guards `if __name__ == "__main__":` en:
  - `test_create_project_api.py`
  - `scripts/test_transcription.py`
  - `test_project_flow_fix.py`
- Esto evita fallos de importación colaterales en `pytest`.

> [!NOTE]
> La implementación actual cumple con el estándar de "Human-in-the-loop", asegurando que la IA proponga hipótesis (Discovery) pero solo el humano valide el registro oficial (Ledger/Neo4j).
