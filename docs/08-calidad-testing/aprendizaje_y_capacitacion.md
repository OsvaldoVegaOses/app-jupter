# Aprendizaje y capacitación
**Fecha:** 2026-01-12  
**Estado:** Propuesta (para discusión)

Esta página consolida el bloque operativo de aprendizaje/capacitación asociado al proceso (posterior a 📖 Etapa 2 – Familiarización).

---

## Etapas (estado y verificación)

El panel **Proceso** en la app muestra información **variable por ejecución** (pendiente/completa, último `run_id`, timestamps, último comando y logs). Para documentación, evitamos copiar el “dump visual” y dejamos solo lo estable: cómo verificar cada etapa.

### Verificaciones por etapa (comandos)

| Etapa | Nombre | Verificación (CLI) |
|------:|--------|---------------------|
| 0 | Preparación y reflexividad | `python scripts/healthcheck.py` |
| 1 | Ingesta y normalización | `python main.py ingest ...` |
| 3 | Codificación abierta | `python main.py coding stats` |
| 4 | Codificación axial | `python main.py axial gds --algorithm pagerank` |
| 5 | Selección del núcleo | `python main.py nucleus report ...` |
| 6 | Análisis transversal | `python main.py transversal dashboard ...` |
| 8 | Validación y saturación | `python main.py validation curve` |
| 9 | Informe integrado | `python main.py report build` |
