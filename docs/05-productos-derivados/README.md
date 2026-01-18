# Productos Derivados de APP_Jupter

**Fecha de creación:** 2025-12-27  
**Autor:** Equipo de Desarrollo

---

## Propósito de esta Carpeta

Esta carpeta contiene documentación de **productos independientes** que se derivan del desarrollo base de APP_Jupter pero constituyen **líneas de producto separadas**.

Cada subdirectorio representa una variación o extensión que:
- Comparte la arquitectura base (Qdrant + Neo4j + PostgreSQL + LLM)
- Tiene objetivos de negocio distintos
- Requiere desarrollo adicional específico
- Puede tener roadmap y prioridades independientes

---

## Productos Derivados

### 1. Chat Empresarial Anti-Alucinaciones
**Estado:** Propuesta  
**Carpeta:** `chat-enterprise/`  
**Descripción:** Chat conversacional con memoria, gates de evidencia y verificación automática para uso empresarial.

### 2. App Bibliográfica (Marco Teórico desde Literatura Científica)
**Estado:** En diseño (definición de brechas/criterios)  
**Carpeta:** `06-bibliografia/`  
**Descripción:** Producto separado para construir marcos teóricos desde literatura (papers/libros), con referencias formales (DOI/BibTeX/RIS) y trazabilidad por obra.

### 3. Evidence Packs / Reporting Suite (Entregables defendibles)
**Estado:** Propuesta  
**Carpeta:** `01-evidence-packs/`  
**Descripción:** Empaquetado de hallazgos en entregables auditables (informe integrado, anexos, manifiestos, “evidence packs”) orientado a consultoría/impacto.

### 4. Interoperabilidad CAQDAS (Exports)
**Estado:** Parcial (existe REFI-QDA/MAXQDA; faltan NVivo/ATLAS.ti)  
**Carpeta:** `02-interoperabilidad-caqdas/`  
**Descripción:** Línea de producto centrada en exportaciones/puentes a herramientas CAQDAS y formatos estándar (NVivo, ATLAS.ti, MAXQDA, REFI-QDA).

### 5. Enterprise Governance (SSO + Audit + Compliance)
**Estado:** Propuesta  
**Carpeta:** `03-enterprise-governance/`  
**Descripción:** Paquete enterprise para gobernanza: SSO/OAuth, audit logging, retención/backup, cumplimiento (GDPR/SOC2) y hardening operacional.

---

## Relación con APP_Jupter Base

```
APP_Jupter (Base)
├── Ingesta de documentos
├── Codificación cualitativa
├── GraphRAG (consultas puntuales)
├── Discovery
└── Reportes

    ↓ Deriva en ↓

Productos Independientes
├── Chat Enterprise (conversacional + anti-alucinaciones)
├── [Futuro: API SaaS]
└── [Futuro: Versión On-Premise]
```

---

## Criterios para Nuevos Productos

Un desarrollo se considera **producto derivado** cuando:
1. Requiere **nuevo frontend** o interfaz significativamente diferente
2. Tiene **flujo de usuario** distinto al análisis cualitativo tradicional
3. Apunta a un **segmento de mercado** diferente
4. Necesita **más de 1 sprint** de desarrollo dedicado

---

## Convención de Documentación

Cada producto derivado debe tener:
- `README.md` - Descripción y objetivos
- `arquitectura.md` - Cambios técnicos vs base
- `roadmap.md` - Plan de implementación
- `valor_negocio.md` - Propuesta de valor diferenciada
