# Manual de Uso: Etapas 3 a 9

Este instructivo guía la ejecución de las etapas posteriores a la ingesta completa de entrevistas. Todos los comandos deben ejecutarse en **PowerShell** dentro del directorio del proyecto, con el entorno virtual activo (`.venv`) y el archivo `.env` configurado.

> Ejemplo de activación de la venv en Windows:
> ```powershell
> .\.venv\Scripts\Activate.ps1
> ```

Antes de comenzar, asegúrate de que la ingesta se haya completado sin errores y que existan registros en Qdrant, PostgreSQL y Neo4j.

---

## Paso previo · Enriquecer metadatos (opcional pero recomendado)

Para que los cortes transversales funcionen (p. ej. por género), puedes aplicar un plan de metadatos:

```json
[
  {
    "archivo": "Claudia_Cesfam.docx",
    "metadata": { "genero": "F", "rol": "dirigente vecinal" },
    "actor_principal": "dirigente vecinal"
  }
]
```

Guárdalo en `metadata/metadata_plan.json` y ejecútalo:

```powershell
python scripts/apply_metadata_plan.py --env .env --plan metadata/metadata_plan.json
```

Esto actualiza PostgreSQL, Qdrant y Neo4j con los metadatos (incluyendo `genero`) para todos los fragmentos del archivo indicado.

Si prefieres hacerlo desde la CLI:

```powershell
# Actualización puntual
python main.py metadata set --archivo Trancripción_Elba.docx \
    --actor-principal "dirigente vecinal" \
    --metadata genero=F --metadata lugar="Lota" --metadata fecha_entrevista=2025-07-18

# O importar desde plan JSON/CSV
python main.py metadata apply --plan metadata/metadata_plan.json
python main.py metadata apply --csv metadata/entrevistas.csv
```

## Etapa 3 · Codificación Abierta

### 3.1 Automatizada (opcional)

Si dispones de un plan de codificación predefinido, puedes alimentarlo desde archivos JSON:

- `metadata/open_codes.json`
  ```json
  [
    {
      "fragmento_id": "<uuid del fragmento>",
      "codigo": "Participación",
      "cita": "Cita literal justificatoria",
      "fuente": "P01"
    }
  ]
  ```

- `metadata/axial.json`
  ```json
  [
    {
      "categoria": "Participación Ciudadana",
      "codigo": "Participación",
      "tipo": "causa",
      "evidencia": ["<uuid1>", "<uuid2>"],
      "memo": "Notas analíticas"
    }
  ]
  ```

Aplica ambos en una sola ejecución:

```powershell
python scripts/apply_coding_plan.py --env .env \
    --open-codes metadata/open_codes.json \
    --axial metadata/axial.json
```

Esto registra los códigos abiertos y las relaciones axiales automáticamente.

### 3.2 Manual

1. **Estado inicial de los códigos**
   ```powershell
   python main.py --env .env coding stats
   ```
   - Crea la tabla `analisis_codigos_abiertos` si no existe.
   - Devuelve totales de fragmentos codificados y sin codificar.

2. **Asignar un código abierto**
   ```powershell
   python main.py --env .env coding assign \
       --fragment-id <fragmento_uuid> \
       --codigo "Nombre del código" \
       --cita "Cita corta justificativa" \
       [--fuente "Alias participante"]
   ```
   Repite para cada fragmento relevante. Los IDs pueden obtenerse con `python main.py search "consulta"`.

3. **Revisión de evidencia por código**
   ```powershell
   python main.py --env .env coding citations --codigo "Nombre del código"
   ```
   Útil para validar citas antes de avanzar a etapas posteriores.

---

## Etapa 4 · Codificación Axial

1. **Relacionar categorías y códigos**
   ```powershell
   python main.py --env .env axial relate \
       --categoria "Categoria Axial" \
       --codigo "Codigo Abierto" \
       --tipo causa|condicion|consecuencia|partede \
       --evidencia <fragmento_id_1> <fragmento_id_2> [más IDs] \
       [--memo "Justificación analítica"]
   ```
   Requiere al menos dos fragmentos evidenciales.

2. **Auditar el grafo con Neo4j GDS**
   ```powershell
   python main.py --env .env axial gds --algorithm louvain
   ```
   - Alternativas: `pagerank`, `betweenness`.
   - Documenta hallazgos (comunidades, rankings) para el diario de reflexividad.

### Consulta libre en Neo4j (soporte)

Cuando necesites obtener vistas rápidas del grafo sin salir de la CLI, utiliza el subcomando `neo4j query`:

```powershell
python main.py --env .env neo4j query ^
    --cypher "MATCH (c:Categoria)-[r:REL]->(k:Codigo) RETURN c.nombre AS categoria, k.nombre AS codigo, size(r.evidencia) AS evidencia" ^
    --format table ^
    --json
```

- Puedes repetir `--param clave=valor` para enviar parámetros al Cypher (por ejemplo `--param limite=10`).
- `--format` acepta `raw`, `table`, `graph` o `all` (repetible). Sin `--json`, se imprimen los formatos seleccionados con indentación legible.

#### Exponer la consulta vía API (opcional)

Cuando requieras integración con dashboards u otras aplicaciones, levanta el backend FastAPI:

```powershell
$env:APP_ENV_FILE = ".env"   # opcional, reuse la misma configuración de la CLI
$env:NEO4J_API_KEY = "<tu-api-key>"
uvicorn backend.app:app --reload --port 8000
```

Luego consume el endpoint:

```bash
curl -X POST http://localhost:8000/neo4j/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <tu-api-key>" \
  -d '{"cypher":"MATCH (c:Categoria)-[r:REL]->(k:Codigo) RETURN c.nombre AS categoria","formats":["table"]}'
```

La respuesta contiene las vistas `raw`, `table` y/o `graph` según lo solicitado, reutilizando el helper `run_cypher`. Si trabajas desde el dashboard React, inicia el frontend con `VITE_NEO4J_API_KEY=<tu-api-key> npm run neo4j:dev` para enviar el header automáticamente. También puedes exportar los resultados:

```bash
curl -X POST http://localhost:8000/neo4j/export \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <tu-api-key>" \
  -d '{"cypher":"MATCH (c:Categoria) RETURN c.nombre","export_format":"csv"}' -o neo4j_export.csv
```

El Explorer añade botones de exportación (CSV/JSON) y muestra la latencia reportada por `X-Query-Duration`.

#### Prueba de carga y monitoreo

Para validar capacidad, ejecuta el script de carga:

```powershell
python scripts/load_test.py ^
   --endpoint http://localhost:8000/neo4j/query ^
    --api-key $env:NEO4J_API_KEY ^
    --duration 60 ^
    --concurrency 6
```

El resultado indica totales, errores y percentiles. Úsalo tras cambios relevantes (dataset grande, ajustes de índice). Complementa con el script de alertas del README para revisar fallos consecutivos.

---

## Etapa 5 · Codificación Selectiva (Núcleo)

Ejecuta un reporte integral sobre la categoría candidata a núcleo.
```powershell
python main.py --env .env nucleus report \
    --categoria "Categoria Núcleo" \
    --prompt "Descripción semántica del núcleo"

    ejemplo:
    python .\main.py nucleus report `
    --categoria "Memoria Territorial" `
    --prompt "analiza cómo la participación sostiene la resiliencia barrial"; python .\main.py nucleus report `
    --categoria "Gestión de Programas " `
    --prompt "analiza cómo la participación sostiene la resiliencia barrial"
```
El JSON resultante indica:
- Posición en PageRank/centralidad.
- Cobertura (entrevistas, roles, citas) en PostgreSQL.
- Probes semánticas en Qdrant y cumplimiento del DoD (checks).

---

## Etapa 6 · Análisis Transversal

1. **Cross-tabs en PostgreSQL**
   ```powershell
   python main.py --env .env transversal pg --dimension genero --refresh
   ```
   Otras dimensiones: `rol`, `periodo`.

2. **Probes segmentadas en Qdrant**
   ```powershell
   python main.py --env .env transversal qdrant \
       --prompt "tema a explorar" \
       --segment "Mujeres|genero=F" \
       --segment "Hombres|genero=M" \
       [--top-k 10]
   ```

3. **Subgrafos comparativos en Neo4j**
   ```powershell
   python main.py --env .env transversal neo4j \
       --attribute genero --values F M
   ```

4. **Payload combinado (dashboard)**
   ```powershell
   python main.py --env .env transversal dashboard \
       --prompt "tema a explorar" \
       --attribute genero --values F M \
       --segment "Mujeres|genero=F" \
       --segment "Hombres|genero=M" \
       [--dimension genero] [--limit 10]
   ```
   El JSON incluye los tres pilares (PG, Qdrant, Neo4j) y latencias por vista (<3 s DoD).

---

## Etapa 7 · Validación y Saturación

1. **Curva de saturación (nuevos códigos)**
   ```powershell
   python main.py --env .env validation curve --window 3 --threshold 0
   ```

2. **Detección de outliers semánticos**
   ```powershell
   python main.py --env .env validation outliers \
       --archivo "Trancripción_Patricio_Yañez.docx" \
       --limit 30 --threshold 0.8
   ```

3. **Triangulación de fuentes en Neo4j**
   ```powershell
   python main.py --env .env validation overlap --limit 20
   ```

4. **Paquetes para member checking**
   ```powershell
   python main.py --env .env validation member \
       --actor "dirigente vecinal" --limit 10
   ```

Documenta resultados (plateau, ausencia de outliers, paquetes generados) para cerrar el sprint.

---

## Etapa 8/9 · Informe Integrado

1. **Estructura Categoria→Código (Neo4j)**
   ```powershell
   python main.py --env .env report outline
   ```

2. **Generar informe, anexos y manifiesto**
   ```powershell
   python main.py --env .env report build \
       --categoria-nucleo "Categoria Núcleo" \
       --prompt-nucleo "Descripción semántica" \
       --output informes/informe_integrado.md \
       --annex-dir informes/anexos \
       --manifest informes/report_manifest.json
   ```

Salidas:
- `informes/informe_integrado.md` (estructura teórica, citas, evidencia).
- CSVs en `informes/anexos/` con cross-tabs y hashes.
- `informes/report_manifest.json` con timestamp, saturación, núcleo y checksums.

Incluye estas rutas en tu documentación final y archivarlas en control de versiones.

---

### Sugerencias de documentación
- Registra en `docs/reflexividad.md` las observaciones de cada etapa.
- Anexa los comandos ejecutados y capturas relevantes en el informe integrado.
- Conserva los hashes (manifest) para auditorías posteriores.

¡Listo! Repite cada etapa según tus hallazgos y actualiza el informe conforme avances.

---

## Mantenimiento y Limpieza

Si necesitas re-procesar un archivo debido a cambios en la lógica de ingesta (ej. detección de hablantes) o errores, es crucial limpiar los datos previos para evitar duplicados.

### Script de Limpieza (`scripts/delete_file_data.py`)

Este script elimina **todos** los datos asociados a un archivo específico en las tres bases de datos (PostgreSQL, Neo4j, Qdrant).

**Uso desde CLI:**
```powershell
# Borrar datos de un archivo en el proyecto por defecto
python scripts/delete_file_data.py "Nombre_Archivo.docx"

# Borrar datos en un proyecto específico
python scripts/delete_file_data.py "Nombre_Archivo.docx" --project nubeweb
```

### Limpieza desde el Frontend

En el panel de **Análisis**, junto al botón de "Ejecutar Análisis", encontrarás un botón rojo **"Eliminar Datos"**.
- Este botón ejecuta el script de limpieza para el archivo seleccionado.
- Úsalo con precaución: la acción es irreversible.
- Es ideal para iterar rápidamente: Ingesta -> Revisión -> Eliminar -> Re-ingesta (con ajustes).

---

## Otros Scripts de Utilidad

Además de los scripts principales, existen herramientas auxiliares en la carpeta `scripts/` que facilitan el mantenimiento y depuración:

| Script | Descripción | Uso Típico |
| :--- | :--- | :--- |
| `scripts/inspect_data.py` | Lista los proyectos y archivos presentes en Postgres, Neo4j y Qdrant. | Verificar qué datos están cargados realmente en cada BD. |
| `scripts/recreate_views.py` | Recrea las vistas materializadas de Postgres (ej. `mv_categoria_por_rol`). | Si las vistas transversales fallan o están desactualizadas. |
| `scripts/normalize_taxonomy.py` | Normaliza acentos y caracteres especiales en códigos y categorías. | Limpieza de datos si hay inconsistencias de texto. |
| `scripts/run_manual.ps1` | Ejecuta secuencialmente las etapas 3 a 9. | Automatizar el flujo completo de análisis tras la ingesta. |
| `scripts/fix_postgres_pk.py` | Corrige constraints de Primary Key en tablas de Postgres. | Reparación de esquema si ocurren errores de integridad. |
| `scripts/run_*_migration.py` | Scripts individuales para aplicar migraciones a cada BD. | Aplicar cambios de esquema (`migrations/`) manualmente. |

**Ejemplo de uso:**
```powershell
# Verificar estado de las bases de datos
python scripts/inspect_data.py

# Recrear vistas para análisis transversal
python scripts/recreate_views.py
```
