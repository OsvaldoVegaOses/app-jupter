# Chat Enterprise Anti-Alucinaciones

**Estado:** 📋 Propuesta  
**Tipo:** Producto Derivado  
**Base:** APP_Jupter GraphRAG

---

## Descripción

Chat conversacional empresarial con:
- Memoria de sesión entre turnos
- Gates de evidencia obligatorios
- Verificación automática de respuestas
- Métricas de alucinación

---

## Documentos

| Documento | Descripción |
|-----------|-------------|
| [chat_empresarial_anti_alucinaciones.md](./chat_empresarial_anti_alucinaciones.md) | Propuesta arquitectónica completa |

---

## Diferencias vs APP_Jupter Base

| Aspecto | APP_Jupter Base | Chat Enterprise |
|---------|-----------------|-----------------|
| Frontend | Panel GraphRAG (consulta única) | Chat con historial |
| Flujo | Usuario ejecuta manualmente | Automatizado |
| Memoria | Sin persistencia | Sesión persistente |
| Validación | Sin gates | Gates + verificador |

---

## Estado de Implementación

- [ ] Propuesta arquitectónica
- [ ] Gates de evidencia (puede hacerse sobre GraphRAG actual)
- [ ] Frontend de chat
- [ ] Backend conversacional
- [ ] Métricas de alucinación

---

## Roadmap Estimado

| Sprint | Entregable | Esfuerzo |
|--------|------------|----------|
| 1 | Gates + formato de respuesta | 10h |
| 2 | Verificador + métricas | 14h |
| 3 | Frontend de chat | 20h |
| 4 | Backend conversacional | 16h |

**Total estimado:** ~60h de desarrollo

---

## Decisión Pendiente

¿Implementar gates sobre GraphRAG existente como paso intermedio?  
**Recomendación:** Sí, aporta valor inmediato sin dependencia del frontend de chat.
