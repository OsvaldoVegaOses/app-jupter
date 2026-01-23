# Ficha metodológica: `get_all_codes_for_project()` (Códigos únicos)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`

## 1) Resumen

`get_all_codes_for_project()` retorna una lista de códigos únicos en un proyecto. Se usa como insumo para medir “novedad” de códigos en análisis/runner y para evitar duplicación nominal.

## 2) Propósito y contexto

En Teoría Fundamentada, el crecimiento del catálogo es una señal:

- Puede indicar exploración efectiva (etapas tempranas).
- O puede indicar duplicación/ruido (si no hay gobernanza).

Tener un set de códigos permite:

- Comparar contra propuestas nuevas.
- Evaluar saturación/plateau de novedades.

## 3) Firma e inputs

- `pg_conn`: conexión PG.
- `project_id`: proyecto.

## 4) Salida

Lista de strings (`codigo`).

## 5) Flujo interno

1. Asegura tabla open coding.
2. Ejecuta `SELECT DISTINCT codigo FROM open_codes WHERE project_id=%s`.
3. Filtra nulos/vacíos.

## 6) Persistencia

- Lectura PG.

## 7) Riesgos

- Depende de la consistencia entre tablas/vistas (`open_codes`). Si hay migraciones, validar que el nombre exista.

## 8) Operación

- Útil para runners y sugerencias de código.

## 9) Referencias internas

- `app/coding.py` (`get_all_codes_for_project`)
- `app/postgres_block.py` (`ensure_open_coding_table`)
