# Sprint 19: Pruebas de Carga e Infraestructura de Benchmark

**Fecha inicio:** 2025-12-27  
**Duración estimada:** 4-6h (cuando se ejecute)  
**Estado:** 📋 PLANIFICADO (infraestructura lista)  
**Prioridad:** 🟡 MEDIA

---

## Objetivo

Validar capacidad real del sistema y documentar límites operativos.

---

## Brechas a Cerrar

| ID | Brecha | Descripción |
|----|--------|-------------|
| B9 | Pruebas de carga | Ejecutar con 10, 50, 100 entrevistas |
| B10 | Dataset sintético | Crear datos de prueba realistas |
| B11 | Documentar límites | Registrar bottlenecks y configuración óptima |

---

## Infraestructura Creada

| Archivo | Propósito | Estado |
|---------|-----------|--------|
| `scripts/generate_test_data.py` | Dataset sintético | ✅ Listo |
| `scripts/load_test_ingest.py` | Benchmark de ingesta | ✅ Listo |
| `docs/benchmarks.md` | Documentación resultados | ⏳ Pendiente ejecución |

---

## Tareas

| ID | Tarea | Estimación | Estado |
|----|-------|------------|--------|
| T1 | Crear script generador de entrevistas | 1h | ✅ |
| T2 | Crear script benchmark ingesta | 1h | ✅ |
| T3 | Ejecutar prueba 10 entrevistas | 30min | ⏳ |
| T4 | Ejecutar prueba 50 entrevistas | 1h | ⏳ |
| T5 | Ejecutar prueba 100 entrevistas | 2h | ⏳ |
| T6 | Documentar resultados | 1h | ⏳ |

---

## Uso de Scripts

### Generar Dataset

```bash
python scripts/generate_test_data.py --count 50 --output data/test_interviews/
```

### Ejecutar Benchmark

```bash
python scripts/load_test_ingest.py --project test_load --dir data/test_interviews/ --report
```

---

## Métricas a Recopilar

- Tiempo total de ingesta (N archivos)
- Tiempo promedio por archivo
- Fragmentos generados
- Uso de memoria pico
- Errores/reintentos Qdrant
- Latencia promedio LLM

---

## Criterios de Éxito

- [ ] Ingestar 10 entrevistas sin errores
- [ ] Ingestar 50 entrevistas con < 5% errores
- [ ] Documentar límite real (X entrevistas/hora)
- [ ] Identificar bottleneck principal
