# Ficha metodológica: `export_codes_refi_qda()` (Exportación REFI‑QDA)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/export/refi-qda`

## 1) Resumen

`export_codes_refi_qda()` exporta el catálogo de códigos (con conteos) en un XML compatible con el ecosistema REFI‑QDA (p.ej. Atlas.ti).

## 2) Propósito y contexto

Permite interoperabilidad y resguardo:

- Auditoría externa.
- Migración a herramientas CAQDAS.
- Archivo metodológico del proceso.

## 3) Firma e inputs

- `project`: proyecto.

## 4) Salida

String XML.

## 5) Flujo interno

1. Asegura tabla open coding.
2. Recupera resumen de códigos: `list_codes_summary(limit=1000)`.
3. Construye XML mínimo con CodeBook.

## 6) Persistencia

- Lectura PG.

## 7) Riesgos y limitaciones

- Es un XML “mínimo”: no exporta todas las citas/segmentos, sino el catálogo con descripción de conteos.

## 8) Operación

- Uso recomendado vía endpoint para descargar.

## 9) Referencias internas

- `app/coding.py` (`export_codes_refi_qda`)
- `backend/app.py` (`GET /api/export/refi-qda`)
