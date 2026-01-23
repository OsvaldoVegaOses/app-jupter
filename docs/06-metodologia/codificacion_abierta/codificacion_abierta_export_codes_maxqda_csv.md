# Ficha metodológica: `export_codes_maxqda_csv()` (Exportación MAXQDA CSV)

> **Fecha**: 2026-01-20
>
> **Código fuente**: `app/coding.py`
>
> **Endpoint relacionado**: `GET /api/export/maxqda`

## 1) Resumen

`export_codes_maxqda_csv()` exporta un resumen tabular de códigos para MAXQDA (CSV con conteos y timestamps de primera/última cita).

## 2) Propósito y contexto

Facilita:

- Interoperabilidad con MAXQDA.
- Reportería rápida.
- Comparaciones por equipo.

## 3) Firma e inputs

- `project`: proyecto.

## 4) Salida

String CSV con encabezados:

`Code,Quotations,Fragments,FirstQuote,LastQuote`

## 5) Flujo interno

1. Asegura tabla open coding.
2. Recupera resumen `list_codes_summary(limit=1000)`.
3. Construye líneas CSV escapando el nombre del código.

## 6) Persistencia

- Lectura PG.

## 7) Riesgos

- CSV es sensible a comillas y comas: se envuelve `Code` entre comillas.

## 8) Operación

- Descargar vía endpoint y abrir en MAXQDA/Excel.

## 9) Referencias internas

- `app/coding.py` (`export_codes_maxqda_csv`)
- `backend/app.py` (`GET /api/export/maxqda`)
