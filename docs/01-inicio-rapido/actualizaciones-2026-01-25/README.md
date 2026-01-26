## Cambios aplicados (25-01-2026)

- **Migraciones PostgreSQL**: ejecutado `scripts/apply_migrations_production.py`, incluyendo los scripts `020_axial_ai_analyses.sql` y `021_axial_ai_evidence.sql` (además de las previas en la lista del script). Resultado: todas aplicaron OK contra la base productiva.
- **Configuración multi-tenant**: en `.env` se actualizó `API_KEY_ORG_ID` a `6fc75e26-c0f4-4559-a2ef-10e508467661` (org del proyecto `jd-007`). Implica que las llamadas con `X-API-Key` ahora se validan contra esa organización. Ajustar este valor si se opera con otra org.
- **Fix evidencia axial**: corregido `app/axial_evidence.py` (orden en consultas `DISTINCT` → `ORDER BY fragmento_id`) para eliminar el error `ORDER BY expressions must appear in select list` al generar `evidence_json` en `/api/axial/analyze-predictions`.
- **Pruebas realizadas**:
  - Backend levantado temporalmente en `127.0.0.1:8010` con `APP_ENV_FILE=.env` y `API_KEY_ORG_ID` anterior; se confirmó salud (`/healthz`).
  - Se ejecutó `POST /api/axial/analyze-predictions` con `project=jd-007`, algoritmo `common_neighbors` y 2 sugerencias; se persistió `analysis_id=1`.
  - `GET /api/axial/ai-analyses` y `GET /api/axial/ai-analyses/1` verificaron que `evidence_json` contiene `fragmento_id` en los fragmentos positivos/negativos.

### Notas operativas
- Los puertos por defecto de los scripts (`backend 8000`, `frontend 5173`) **no se modificaron**. El uso del puerto 8010 fue solo para pruebas manuales.
- Si necesitas otra organización con API Key, cambia `API_KEY_ORG_ID` antes de levantar el backend (o exporta la variable en el entorno).
- Para repetir el flujo de prueba: levantar backend con `.env` actualizado, llamar al endpoint `/api/axial/analyze-predictions` con `X-API-Key=dev-key` y `project=jd-007`, luego consultar `/api/axial/ai-analyses` y el detalle por ID.
