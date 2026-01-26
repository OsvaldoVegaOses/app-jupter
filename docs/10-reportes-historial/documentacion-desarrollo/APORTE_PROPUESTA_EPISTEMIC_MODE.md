Aporte a **propuesta en `PROPUESTA_EPISTEMIC_MODE.md`**, el plan queda así (y te marco dos ajustes finos que conviene hacer para que no se vuelva deuda).

---

## 1) Qué cambia realmente con `epistemic_mode`

La propuesta está bien enfocada: hoy el sistema mezcla paradigmas en un solo prompt y eso genera inconsistencia en códigos/memos/axialidad . Separarlo por proyecto **sí impacta salida analítica**, no es cosmético .

Lo propuesto:

* **Schema**: `pg_proyectos.epistemic_mode` con valores `constructivist | post_positivist` y default `constructivist` 
* **Prompts**: templates separados por modo en `app/prompts/{mode}/...` 
* **Loader** con LRU cache + fallback seguro al modo constructivista 
* **Integración** en `analysis.py`: seleccionar prompt por modo y registrar `epistemic_mode` + `prompt_version` 
* **UI**: selector + badge indicador 
* **Criterios de aceptación** claros (incluye “lock” del modo post-axial) 

---

## 2) Recomendación de priorización (ajustada a tu nuevo estado: Fase 1.5 Core DONE)

En el doc, se recomienda **Ticket A + B ahora** y “integrar en analysis.py cuando se refactorice para Fase 2” .

Con la Fase 1.5 Core ya cerrada, yo haría esto:

### Implementar **A + B + C ahora** (y D opcional)

* **A (schema + config + API)**: necesario para que exista el modo y quede auditable 
* **B (prompts + loader)**: necesario para que exista diferenciación real 
* **C (integración en `analysis.py`)**: esto evita generar más proyectos “mezclados” bajo un prompt híbrido (tu motivación #1). 
* **D (UI)**: puede ir después si quieren acelerar backend, pero si hay usuarios internos probando, mejor poner el selector pronto 

---

## 3) Dos ajustes finos que haría antes de codear (evitan bugs/deuda)

### Ajuste A: coherencia de nombres “stage” vs archivos

En la estructura propuesta, existe `discovery_synthesis.txt` , pero `get_system_prompt()` documenta stages tipo `"discovery"` / `"selective"` .
**Solución simple:** definir un mapping único (p.ej. `stage -> filename`) o renombrar archivos para que coincidan 1:1.

### Ajuste B: fallback constructivista debe quedar auditado

El fallback está bien como “default seguro” , pero yo **loguearía warning** (y/o metería `prompt_version` explícito “fallback”) para que no quede silencioso.

---

## 4) “Definition of Done” para cerrar `epistemic_mode` sin ambigüedades

Me quedaría con los criterios del doc y los reforzaría así:

1. **DB**: `epistemic_mode` existe y se persiste por proyecto (default constructivist). 
2. **API**: `GET project` devuelve `epistemic_mode`; `PATCH` permite setearlo.
3. **Runtime**: `analysis` adjunta `epistemic_mode` y `prompt_version` en response (audit trail). 
4. **Lock de consistencia**: “modo no puede cambiarse después de iniciar codificación axial” (en backend, no solo UI). 
5. **Prompts**: constructivist produce sesgo a gerundios/in-vivo; post_positivist a sustantivos abstractos (al menos a nivel de *instrucción* del prompt y tests de template). 

---

## 5) Siguiente paso concreto (lo que yo pondría hoy en el tablero)

**Epic: “Epistemic Mode v1”** (8–12h estimado por el doc )

1. **Ticket A**: migration `017_epistemic_mode.sql` + enum + `get_project_epistemic_mode()`  
2. **Ticket B**: `app/prompts/*` + loader LRU + tests de carga y mapping stage→archivo 
3. **Ticket C**: integrar en `analysis.py` y registrar `prompt_version` 
4. **Ticket D (si hay usuarios ya)**: selector + badge 
5. **Ticket E**: doc breve + checklist de cuándo usar cada modo (para evitar confusión de usuarios) 

