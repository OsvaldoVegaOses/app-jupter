# Benchmarks y Resultados de Pruebas de Carga

**Fecha:** 2024-12-13  
**Estado:** 🔄 Infraestructura lista, ejecución pendiente

---

## Infraestructura de Pruebas

### Scripts Creados

| Script | Propósito | Uso |
|--------|-----------|-----|
| `scripts/generate_test_data.py` | Genera entrevistas sintéticas | `python scripts/generate_test_data.py --count 50 --output data/test_interviews` |
| `scripts/load_test_ingest.py` | Prueba de carga de ingesta | `python scripts/load_test_ingest.py --input data/test_interviews --project loadtest --limit 10` |

### Configuración de Prueba

```bash
# Generar datos de prueba
python scripts/generate_test_data.py --count 100 --output data/test_interviews

# Ejecutar con diferentes volúmenes
python scripts/load_test_ingest.py --input data/test_interviews --project test10 --limit 10
python scripts/load_test_ingest.py --input data/test_interviews --project test50 --limit 50
python scripts/load_test_ingest.py --input data/test_interviews --project test100 --limit 100
```

---

## Resultados de Pruebas

### Prueba 1: 10 Entrevistas Sintéticas

| Métrica | Valor |
|---------|-------|
| **Archivos procesados** | 0/10 |
| **Éxito** | 0% |
| **Error** | 502 - Backend UTF-8 codec error |

**Bloqueador identificado:** El backend presenta un error de inicialización de clientes relacionado con codificación UTF-8 en el archivo .env.

### Prueba 2: Pendiente (50 entrevistas)

_Bloqueado por error de backend_

### Prueba 3: Pendiente (100 entrevistas)

_Bloqueado por error de backend_

---

## Configuraciones Implementadas

### Qdrant (Prevención de Timeouts)

| Parámetro | Valor | Variable de Entorno |
|-----------|-------|---------------------|
| Batch size | 20 | `QDRANT_BATCH_SIZE` |
| Timeout | 30s | `QDRANT_TIMEOUT` |
| Retry attempts | 3 | Hardcoded |
| Wait strategy | Exponential backoff (1-30s) | Hardcoded |

### Ingesta

| Parámetro | Valor |
|-----------|-------|
| Default batch size | 20 fragmentos |
| Min chars per fragment | 200 |
| Max chars per fragment | 1200 |

---

## Próximos Pasos

1. **Resolver error de backend** (502 UTF-8 codec):
   - Revisar archivo `.env` por caracteres no UTF-8
   - Verificar que todas las API keys estén correctamente formateadas

2. **Ejecutar pruebas cuando esté resuelto:**
   - P5: 10 entrevistas (baseline)
   - P6: 50 entrevistas (load)
   - P7: 100 entrevistas (stress)

3. **Métricas a capturar:**
   - Tiempo total de ingesta
   - Tiempo promedio por archivo
   - Fragmentos procesados
   - Errores de timeout de Qdrant
   - Uso de memoria

---

## Métricas Esperadas (Estimación)

Basado en la configuración actual:

| Volumen | Tiempo Estimado | Fragmentos |
|---------|-----------------|------------|
| 10 entrevistas | ~2-3 min | ~300-500 |
| 50 entrevistas | ~10-15 min | ~1500-2500 |
| 100 entrevistas | ~20-30 min | ~3000-5000 |

---

*Documento actualizado: Diciembre 2024*
