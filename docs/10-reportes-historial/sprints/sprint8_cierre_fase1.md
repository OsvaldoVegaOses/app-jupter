# Sprint 8: Cierre de Fase 1 (Etapas 1-4)

> **Fecha:** Diciembre 2024  
> **Duración:** 1 semana (5 días hábiles)  
> **Objetivo:** Cerrar todas las brechas pendientes para completar la Fase 1

---

## Resumen de Brechas a Cerrar

| # | Brecha | Prioridad | Días |
|---|--------|-----------|------|
| 1 | Remapeo de códigos fantasma (~30%) | Alta | 1 |
| 2 | Limpieza de datos `Automatica_Test` | Alta | 0.5 |
| 3 | Validación con load testing | Media | 1.5 |
| 4 | Verificación E2E completa | Media | 1 |
| 5 | Documentación de cierre | Baja | 1 |

---

## Día 1: Remapeo de Códigos Fantasma

### Objetivo
Reducir códigos con IDs sintéticos de ~30% a <10%

### Tareas

| Tarea | Responsable | Estado |
|-------|-------------|--------|
| Ejecutar `remap_ghost_codes.py` en proyecto default | Backend | [ ] |
| Verificar tasa de vinculación post-remapeo | Backend | [ ] |
| Documentar resultados en `docs/metricas_vinculacion.md` | Backend | [ ] |

### Comandos

```bash
# Listar códigos fantasma
python -c "
from app.clients import build_service_clients
from app.settings import load_settings
settings = load_settings()
clients = build_service_clients(settings)
with clients.postgres.cursor() as cur:
    cur.execute(\"SELECT COUNT(*) FROM analisis_codigos_abiertos WHERE fragmento_id LIKE '%#auto#%'\")
    print('Códigos fantasma:', cur.fetchone()[0])
clients.close()
"

# Ejecutar remapeo
python scripts/remap_ghost_codes.py --project default --threshold 0.92 --dry-run
python scripts/remap_ghost_codes.py --project default --threshold 0.92
```

### Criterio de éxito
- [ ] Códigos fantasma < 10% del total

---

## Día 2 (AM): Limpieza de Datos de Prueba

### Objetivo
Eliminar `Automatica_Test` y otros datos de prueba

### Tareas

| Tarea | Responsable | Estado |
|-------|-------------|--------|
| Backup de base de datos | DBA | [ ] |
| Ejecutar limpieza PostgreSQL | DBA | [ ] |
| Ejecutar limpieza Neo4j | DBA | [ ] |
| Verificar conteos post-limpieza | DBA | [ ] |

### Comandos

```sql
-- PostgreSQL: Listar antes
SELECT codigo, COUNT(*) FROM analisis_codigos_abiertos 
WHERE codigo LIKE '%Test%' OR codigo LIKE '%Automatica%'
GROUP BY codigo;

-- PostgreSQL: Eliminar
DELETE FROM analisis_codigos_abiertos 
WHERE codigo LIKE '%Automatica_Test%';

DELETE FROM analisis_axial 
WHERE codigo LIKE '%Automatica_Test%';
```

```cypher
// Neo4j: Listar antes
MATCH (c:Codigo) WHERE c.nombre CONTAINS 'Test' RETURN c.nombre, count(*);

// Neo4j: Eliminar
MATCH (c:Codigo) WHERE c.nombre CONTAINS 'Automatica_Test' DETACH DELETE c;
```

### Criterio de éxito
- [ ] Cero registros con `Automatica_Test`

---

## Día 2 (PM) + Día 3: Load Testing

### Objetivo
Validar rendimiento con volumen realista (≥50 documentos)

### Tareas

| Tarea | Responsable | Estado |
|-------|-------------|--------|
| Generar 50 documentos de prueba | QA | [ ] |
| Ejecutar ingesta con métricas | QA | [ ] |
| Registrar tiempos y errores | QA | [ ] |
| Documentar resultados en `docs/benchmarks.md` | QA | [ ] |

### Comandos

```bash
# Generar datos sintéticos
python scripts/generate_test_data.py --count 50 --output data/load_test/

# Ejecutar load test
python scripts/load_test_ingest.py \
  --directory data/load_test/ \
  --concurrent 3 \
  --project load-test-fase1

# Verificar resultados
python scripts/verify_ingestion.py --project load-test-fase1 --timeout 300
```

### Métricas a capturar

| Métrica | Umbral | Resultado |
|---------|--------|-----------|
| Tiempo promedio por documento | < 30s | [ ] |
| Tasa de errores Qdrant | < 5% | [ ] |
| Fragmentos creados | ≥ 500 | [ ] |
| Códigos generados | ≥ 100 | [ ] |

### Criterio de éxito
- [ ] 50+ documentos ingestados sin errores críticos
- [ ] Tiempos dentro de umbrales

---

## Día 4: Verificación E2E Completa

### Objetivo
Ejecutar ciclo completo Etapas 1-4 y validar integración

### Tareas

| Tarea | Responsable | Estado |
|-------|-------------|--------|
| Ejecutar `run_e2e.ps1` con proyecto limpio | QA | [ ] |
| Verificar persistencia en Neo4j | QA | [ ] |
| Ejecutar GDS (PageRank + Louvain) | QA | [ ] |
| Validar visualización en frontend | QA | [ ] |

### Comandos

```powershell
# E2E completo
powershell -ExecutionPolicy Bypass -File scripts/run_e2e.ps1 -ProjectID "fase1-final"

# Verificar Neo4j
python main.py neo4j query "MATCH (c:Categoria)-[r:REL]->(k:Codigo) RETURN count(*)"

# Ejecutar GDS
python main.py axial gds --algorithm pagerank --persist
python main.py axial gds --algorithm louvain --persist

# Verificar GDS
python main.py neo4j query "MATCH (n:Codigo) WHERE n.score_centralidad IS NOT NULL RETURN count(n)"
```

### Checklist de validación

| Componente | Verificación | Estado |
|------------|--------------|--------|
| Ingesta | Fragmentos en 3 DBs | [ ] |
| Códigos abiertos | Vinculados a fragmentos | [ ] |
| Códigos axiales | Relaciones en Neo4j | [ ] |
| GDS PageRank | `score_centralidad` existe | [ ] |
| GDS Louvain | `community_id` existe | [ ] |
| Frontend | Visualización funciona | [ ] |

### Criterio de éxito
- [ ] E2E completo sin errores
- [ ] GDS operativo

---

## Día 5: Documentación de Cierre

### Objetivo
Documentar resultados y marcar Fase 1 como completada

### Tareas

| Tarea | Responsable | Estado |
|-------|-------------|--------|
| Actualizar `docs/sprint_tracking.md` | Docs | [ ] |
| Crear `docs/cierre_fase1.md` | Docs | [ ] |
| Actualizar `docs/valor_negocio.md` | Docs | [ ] |
| Snapshot de métricas finales | Docs | [ ] |

### Contenido de `cierre_fase1.md`

```markdown
# Cierre de Fase 1 (Etapas 1-4)

## Fecha de cierre: [FECHA]

## Métricas finales
- Documentos procesados: X
- Fragmentos creados: X
- Códigos abiertos: X
- Códigos axiales: X
- Tasa de vinculación: X%

## Brechas cerradas
- [x] Remapeo de códigos fantasma
- [x] Limpieza de datos de prueba
- [x] Load testing validado
- [x] E2E verificado

## Próxima fase
- Sprint 9: GraphRAG completo
- Sprint 10: Discovery API
```

---

## Resumen del Sprint

| Día | Actividad | Entregable |
|-----|-----------|------------|
| 1 | Remapeo códigos | Tasa vinculación ≥90% |
| 2 AM | Limpieza datos | Cero `Automatica_Test` |
| 2 PM - 3 | Load testing | Benchmarks documentados |
| 4 | Verificación E2E | Ciclo completo validado |
| 5 | Documentación | `cierre_fase1.md` |

---

## Criterios de Cierre del Sprint

| Criterio | Umbral | Responsable |
|----------|--------|-------------|
| Códigos con fragmento real | ≥ 90% | Backend |
| Datos de prueba | 0% | DBA |
| Load test exitoso | ≥ 50 docs | QA |
| E2E sin errores | 100% | QA |
| Documentación | Completa | Docs |

---

## Riesgos y Mitigación

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Remapeo falla por baja similitud | Media | Reducir threshold a 0.85 |
| Timeout en load test | Baja | Reducir concurrencia |
| GDS no disponible | Baja | Usar fallback NetworkX |

---

*Sprint planificado: Diciembre 2024*
