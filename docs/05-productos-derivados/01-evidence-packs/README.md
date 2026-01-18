# Evidence Packs / Reporting Suite

**Producto derivado:** sí (línea separada del análisis cualitativo interactivo).  
**Base:** capacidades existentes de trazabilidad, reporting y manifiestos descritas en `docs/04-arquitectura/valor_negocio.md`.

---

## Qué es
Un producto orientado a generar **entregables defendibles** para consultoría/impacto ("evidence packs"): documentos y anexos donde cada hallazgo queda respaldado por evidencia trazable (fragmentos/códigos/relaciones) y metadatos de auditoría.

## Entregables típicos (salidas)
- Informe ejecutivo (Markdown/PDF vía pipeline externo)
- Informe integrado + anexos (tablas cruzadas, listados)
- Manifiesto de reporte (hashes, parámetros, fecha, proyecto)
- Paquetes de evidencia por tema/categoría (quotes + origen + contexto)

## Qué reutiliza del baseline
- Generación de reportes y manifiestos (conceptualmente alineado a `informes/`, `reports/`, `notes/`)
- Trazabilidad fragmento↔código↔cita y outline teórico desde grafo

## Qué lo hace producto separado
- Empaquetado “cliente-ready” (plantillas, secciones, formatos, redacción)
- Flujo de aprobación/revisión (interno/cliente)
- Políticas de anonimización y compliance por sector
