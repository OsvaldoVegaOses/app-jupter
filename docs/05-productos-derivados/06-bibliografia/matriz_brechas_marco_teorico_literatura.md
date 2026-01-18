# Matriz de brechas: Marco teórico desde literatura científica

**Fecha:** 2025-12-27  
**Propósito:** esta matriz es un insumo de arquitectura para **desarrollar una app nueva** orientada a revisión/gestión de **literatura científica** y construcción de **marcos teóricos con referencias bibliográficas formales**.  
**Contexto:** se usa el código actual (módulo `app/`) **solo como baseline de comparación**, porque hoy está orientado a **análisis cualitativo de entrevistas** (Grounded Theory + GraphRAG).  
**Alcance:** identificar si el baseline actual cubre (o no) requisitos típicos de una app bibliográfica y documentar **brechas, impacto y prioridades**.  
**Restricción:** este documento NO implica cambios en código; solo define criterios y gaps para una solución separada.

---

## 1) Resumen ejecutivo

El core actual está optimizado para **análisis cualitativo de entrevistas / corpus propio** (Grounded Theory + GraphRAG), donde la “cita” es un **extracto del texto** vinculado a un fragmento.

Para “marco teórico desde literatura científica”, faltan capacidades clave: **ingesta de papers (PDF/HTML), extracción/normalización de referencias (DOI/BibTeX/RIS), modelo de datos de obras, y exportación de citas**.

---

## 2) Definiciones operativas (para evitar ambigüedad)

- **Cita (corpus de entrevistas):** extracto textual del documento analizado (quote). En la app actual se modela como `cita` y se vincula a `fragmento_id`.
- **Referencia bibliográfica (literatura científica):** obra citada (paper/libro) con metadatos (autores, año, título, venue/editorial) y, cuando aplique, DOI/ISBN/URL.
- **Marco teórico desde literatura:** síntesis conceptual sustentada por **referencias bibliográficas formales** + evidencia localizada (sección/página/fragmento) en la literatura.

Nota de lectura: en este documento, el término **"referencias"** apunta a **referencias bibliográficas** (obras). Las **"citas"** en el baseline actual son **citas-texto** (quotes) del corpus de entrevistas.

---

## 3) Matriz de brechas (capacidad → estado actual → falta → impacto)

> Leyenda prioridad: P0 (bloqueante), P1 (muy alta), P2 (media), P3 (baja)

| Capacidad requerida (literatura) | Estado en `app/` hoy | Evidencia / módulo relacionado | Brecha concreta | Impacto si no se cubre | Prioridad |
|---|---|---|---|---|---|
| Ingesta de PDFs de papers | No explícita | `documents.py` procesa DOCX; `ingestion.py` asume DOCX | Falta extracción de texto de PDF + segmentación por secciones/páginas | No puedes analizar papers reales sin convertirlos fuera del sistema | P0 |
| Ingesta de HTML (journals/web) | No explícita | No hay fetch/parse de HTML en `app/` | Falta scraping/control de licencias + extracción main-content | Dependencia manual (copiar/pegar) y baja reproducibilidad | P1 |
| Extracción de bibliografía (References) | No | No hay parser de “References” | Falta identificar bloque de referencias + parse de entradas | No hay base de obras; imposible citar formalmente | P0 |
| Resolución de DOI (Crossref/OpenAlex) | No | No se encuentran `doi`, `crossref`, `openalex` | Falta resolver metadatos confiables (título/autores/año) | Duplicados; referencias inconsistentes | P0 |
| Modelo de datos de “Obras” (works) | No | Postgres tiene fragmentos/códigos; no tabla `works` | Falta entidad obra + ediciones + identificadores | No puedes gestionar bibliografía como primer ciudadano | P0 |
| Vínculo: obra ↔ fragmentos de evidencia | Parcial (solo fragmento↔código) | `analisis_codigos_abiertos` vincula quote a fragmento | Falta `work_id`, ubicación (sección/página) y soporte de citas in-text | Evidencia no auditable a nivel bibliográfico | P0 |
| Detección de in-text citations (Autor-año / [n]) | No | No hay regex/parsers dedicados | Falta extraer menciones y mapearlas a referencias | Marco teórico no puede atribuir correctamente | P1 |
| Exportación BibTeX / RIS / CSL-JSON | No | No hay output bibliográfico | Falta exportadores estándar | No puedes integrar con Zotero/Mendeley/Word/LaTeX | P1 |
| Formateo de citas (APA/IEEE) | No | No hay motor CSL | Falta “citeproc”/CSL y plantillas | Salida final no cumple formato académico | P2 |
| Gestión de “corpus bibliográfico” por proyecto | Parcial (project_id existe) | `project_id` permea PG/Qdrant/Neo4j | Falta pipeline dedicado “biblioteca del proyecto” | Mezcla de evidencia; difícil versionar selección de papers | P1 |
| Deduplicación de obras | No | Solo dedupe de fragmentos por hash | Falta dedupe por DOI/ISBN + fuzzy título | Basura en bibliografía; resultados no confiables | P1 |
| Métricas bibliométricas (co-citación, coupling) | No | Neo4j se usa para categorías/códigos | Falta grafo paper→paper y algoritmos bibliométricos | No puedes justificar centralidad de literatura | P2 |
| Reproducibilidad (manifest + checksums) | Parcial | `reporting.py` genera manifest; ingest guarda sha256 de fragmento | Falta manifest de obras + fuentes + licencias + resoluciones DOI | Auditoría incompleta para revisión sistemática | P1 |
| Control de calidad (sesgos, cobertura temática) | Parcial | Hay saturación/validación para entrevistas | Falta QA específico para literatura (cobertura por año/venue/tema) | Sesgo de selección no detectado | P2 |

---

## 4) Criterios mínimos de aceptación (para decir “apto para marco teórico desde literatura”)

1. **Works registry:** existe una entidad de obra (paper/libro) con metadatos mínimos: `title`, `authors`, `year`, `venue`, `doi|isbn|url`.
2. **Ingest reproducible:** se puede ingestar PDF/HTML con trazabilidad (hash del archivo, fecha, origen) y se generan fragmentos con ubicación (`page`, `section`, `offset`).
3. **References parsed:** se extraen referencias del documento y se normalizan (idealmente via DOI cuando exista).
4. **Claims traceable:** cualquier afirmación del marco teórico se apoya en evidencia: `(work_id, fragment_id, quote, location)`.
5. **Export estándar:** se puede exportar bibliografía en BibTeX o CSL-JSON (mínimo uno) para integración externa.

---

## 5) Hoja de ruta mínima (por fases, sin “gold plating”)

### Fase 0 (P0) — Habilitar literatura como corpus
- Ingesta PDF → texto → fragmentos + embeddings
- Entidad obra (`work`) + relación obra↔fragmentos
- Extracción básica de referencias (aunque sea heurística) + normalización mínima

### Fase 1 (P1) — Normalización y citación formal
- Resolución DOI (cuando haya)
- Deduplicación por DOI y fuzzy título
- Export BibTeX/CSL-JSON

### Fase 2 (P2) — Robustez académica
- Detección de in-text citations y mapeo a referencias
- Métricas bibliométricas básicas (paper→paper) opcional
- QA de cobertura (años, temas, fuentes)

---

## 6) Recomendación práctica (sin tocar código aún)

Si necesitas resultados inmediatos, el camino de menor fricción (a corto plazo) es:
- Convertir papers a **texto estructurado** fuera del sistema y luego ingestar como “documentos” (pero esto degrada trazabilidad y bibliografía).

Si necesitas **marco teórico con referencias formales**, lo recomendable es planificar Fase 0 + Fase 1: sin `works` + DOI/normalización, el sistema seguirá siendo “análisis de corpus” y no “gestor de literatura”.
