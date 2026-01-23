# Manual de Usuario: ETAPA 0 - PREPARACIÓN

> **Versión:** 1.0  
> **Fecha:** 18 de Enero de 2026  
> **Aplicación:** Sistema de Análisis Cualitativo Doctoral

---

## Índice

1. [Descripción General](#1-descripción-general)
2. [Acceso a la Etapa 0](#2-acceso-a-la-etapa-0)
3. [Componentes de la Etapa](#3-componentes-de-la-etapa)
   - [3.1 Protocolo de Investigación](#31-protocolo-de-investigación)
   - [3.2 Actores (Participantes)](#32-actores-participantes)
   - [3.3 Consentimientos Informados](#33-consentimientos-informados)
   - [3.4 Criterios de Muestreo](#34-criterios-de-muestreo)
   - [3.5 Plan de Análisis](#35-plan-de-análisis)
4. [Panel de Estado](#4-panel-de-estado)
5. [Solución de Problemas](#5-solución-de-problemas)
6. [Preguntas Frecuentes](#6-preguntas-frecuentes)

---

## 1. Descripción General

La **Etapa 0: Preparación** es el primer paso obligatorio antes de iniciar cualquier análisis cualitativo. Esta etapa asegura que:

- ✅ El protocolo de investigación esté documentado
- ✅ Los participantes (actores) estén registrados de forma anónima
- ✅ Los consentimientos informados estén firmados
- ✅ Los criterios de muestreo estén definidos
- ✅ El plan de análisis esté establecido

**⚠️ IMPORTANTE:** No podrá avanzar a la Etapa 1 (Ingesta) hasta completar todos los componentes de la Etapa 0.

---

## 2. Acceso a la Etapa 0

### Pasos para acceder:

1. Inicie sesión en la aplicación
2. Seleccione o cree un proyecto
3. En el menú lateral, haga clic en **"Etapa 0: Preparación"**

### Indicador de Estado

En la parte superior verá un indicador de estado:

```
Estado: 🟡 Pendiente · Protocolo ✅ · Actores ✅ · Consentimientos ❌ · Muestreo ✅ · Plan ✅
```

| Símbolo | Significado |
|---------|-------------|
| ✅ | Componente completado |
| ❌ | Componente pendiente |
| 🟢 Listo | Todos los componentes completados |
| 🟡 Pendiente | Faltan componentes por completar |

---

## 3. Componentes de la Etapa

### 3.1 Protocolo de Investigación

El protocolo documenta el marco metodológico de su investigación.

#### Campos requeridos:

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| **Título** | Nombre del estudio | "Experiencias de docentes en educación rural" |
| **Objetivos** | Objetivos de investigación | "Explorar las percepciones de..." |
| **Enfoque metodológico** | Tipo de investigación | Fenomenológico, Teoría Fundamentada, etc. |
| **Justificación** | Por qué es relevante | "Esta investigación busca..." |

#### Pasos:

1. Haga clic en **"Protocolo"** en el menú de Etapa 0
2. Complete todos los campos requeridos
3. Haga clic en **"Guardar Protocolo"**
4. El indicador cambiará a ✅

---

### 3.2 Actores (Participantes)

Los actores son los participantes de su investigación. Se registran de forma **anónima** para proteger su identidad.

#### Campos disponibles:

| Campo | Requerido | Descripción |
|-------|-----------|-------------|
| **Alias** | ✅ Sí | Identificador anónimo (ej: "Participante A", "Docente 1") |
| **Datos demográficos** | No | Información anónima relevante (edad, género, etc.) |
| **Etiquetas** | No | Tags para categorizar (ej: "rural", "urbano") |
| **Notas** | No | Observaciones adicionales |

#### Pasos para agregar un actor:

1. Haga clic en **"Actores"** en el menú de Etapa 0
2. Haga clic en **"+ Agregar Actor"**
3. Complete el campo **Alias** (obligatorio)
4. Opcionalmente complete los datos demográficos
5. Haga clic en **"Guardar"**

#### Ejemplo de registro:

```
Alias: Docente-Rural-01
Datos demográficos: { "edad_rango": "30-40", "experiencia_años": "5-10" }
Etiquetas: ["rural", "primaria", "multigrado"]
```

---

### 3.3 Consentimientos Informados

**⚠️ CRÍTICO:** Cada actor DEBE tener al menos un consentimiento informado activo para que la Etapa 0 se complete.

El consentimiento documenta que el participante ha aceptado participar en la investigación.

#### Campos del consentimiento:

| Campo | Requerido | Descripción |
|-------|-----------|-------------|
| **Fecha de firma** | ✅ Sí | Cuándo firmó el participante |
| **Alcance (Scope)** | No | Qué cubre el consentimiento |
| **URL de evidencia** | No | Link al documento escaneado |
| **Notas** | No | Observaciones adicionales |

#### Pasos para registrar un consentimiento:

1. Haga clic en **"Actores"** en el menú de Etapa 0
2. Localice el actor en la lista
3. Haga clic en el botón **"Consentimiento"** o **"+"** junto al actor
4. Complete la **fecha de firma**
5. Opcionalmente agregue URL de evidencia
6. Haga clic en **"Guardar Consentimiento"**

#### Estados del consentimiento:

| Estado | Significado | Acción |
|--------|-------------|--------|
| **Sin consentimiento** | Actor no tiene consentimiento | Agregar consentimiento |
| **Firmado** | Consentimiento activo | Ninguna acción requerida |
| **Revocado** | Participante retiró consentimiento | Considerar eliminar datos |

#### ¿Por qué fallan los consentimientos?

El indicador de consentimientos mostrará ❌ si:

1. **No hay actores registrados** - Debe agregar al menos un actor
2. **Actores sin consentimiento** - Cada actor debe tener consentimiento firmado
3. **Consentimiento revocado** - El participante retiró su consentimiento

---

### 3.4 Criterios de Muestreo

Define cómo seleccionó a los participantes de su estudio.

#### Campos:

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| **Tipo de muestreo** | Estrategia utilizada | Intencional, Bola de nieve, Teórico |
| **Criterios de inclusión** | Quién puede participar | "Docentes con 5+ años de experiencia" |
| **Criterios de exclusión** | Quién no puede participar | "Docentes en práctica" |
| **Tamaño esperado** | Cantidad de participantes | 10-15 participantes |
| **Justificación** | Por qué estos criterios | "Se busca saturación teórica..." |

#### Pasos:

1. Haga clic en **"Muestreo"** en el menú de Etapa 0
2. Complete los criterios de selección
3. Haga clic en **"Guardar"**

---

### 3.5 Plan de Análisis

Describe cómo analizará los datos recolectados.

#### Campos:

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| **Enfoque analítico** | Método de análisis | Análisis temático, Codificación abierta |
| **Fases del análisis** | Etapas planificadas | Codificación → Categorización → Teorización |
| **Software/Herramientas** | Tecnología a usar | Este sistema, Atlas.ti, NVivo |
| **Estrategias de rigor** | Cómo asegura calidad | Triangulación, member checking |

#### Pasos:

1. Haga clic en **"Plan de Análisis"** en el menú de Etapa 0
2. Documente su estrategia analítica
3. Haga clic en **"Guardar"**

---

## 4. Panel de Estado

El panel de estado muestra el progreso de la Etapa 0:

```
┌─────────────────────────────────────────────────────────────┐
│  ETAPA 0: PREPARACIÓN                                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Estado General: 🟡 PENDIENTE                               │
│                                                             │
│  ┌─────────────┬────────┬─────────────────────────────────┐ │
│  │ Componente  │ Estado │ Detalle                         │ │
│  ├─────────────┼────────┼─────────────────────────────────┤ │
│  │ Protocolo   │   ✅   │ 1 protocolo registrado          │ │
│  │ Actores     │   ✅   │ 3 actores registrados           │ │
│  │ Consentim.  │   ❌   │ 1 actor sin consentimiento      │ │
│  │ Muestreo    │   ✅   │ Criterios definidos             │ │
│  │ Plan        │   ✅   │ Plan de análisis completo       │ │
│  └─────────────┴────────┴─────────────────────────────────┘ │
│                                                             │
│  [Continuar a Etapa 1] (deshabilitado hasta completar)     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Métricas adicionales:

- **Actores totales:** Cantidad de participantes registrados
- **Actores sin consentimiento:** Cuántos faltan por firmar
- **Última actualización:** Fecha del último cambio

---

## 5. Solución de Problemas

### Problema: Consentimientos ❌ aunque tengo actores

**Causa:** Los actores no tienen consentimiento firmado.

**Solución:**
1. Vaya a **Actores**
2. Para cada actor, haga clic en **"Agregar Consentimiento"**
3. Ingrese la fecha de firma
4. Guarde

### Problema: No puedo avanzar a Etapa 1

**Causa:** No todos los componentes están completos.

**Solución:**
1. Revise el indicador de estado
2. Complete los componentes marcados con ❌
3. El botón "Continuar" se habilitará automáticamente

### Problema: Actor aparece sin consentimiento después de registrarlo

**Causa:** El consentimiento pudo no guardarse correctamente.

**Solución:**
1. Refresque la página (F5)
2. Verifique en la lista de actores
3. Si persiste, intente registrar el consentimiento nuevamente

### Problema: Error al guardar protocolo

**Causa:** Campos requeridos vacíos o conexión perdida.

**Solución:**
1. Verifique que todos los campos obligatorios estén completos
2. Verifique su conexión a internet
3. Intente nuevamente

---

## 6. Preguntas Frecuentes

### ¿Puedo modificar el protocolo después de guardarlo?

**Sí.** Puede editar el protocolo en cualquier momento, incluso después de avanzar a etapas posteriores. Los cambios quedan versionados.

### ¿Qué pasa si un participante retira su consentimiento?

1. Vaya a **Actores → [Nombre del actor] → Consentimientos**
2. Haga clic en **"Revocar"** en el consentimiento activo
3. El sistema marcará los datos de ese actor
4. Considere eliminar o anonimizar sus datos según su protocolo ético

### ¿Puedo agregar actores después de la Etapa 0?

**Sí.** Puede volver a la Etapa 0 en cualquier momento para agregar nuevos actores. Esto es común en muestreo teórico donde los participantes se agregan iterativamente.

### ¿Los alias de los actores deben ser únicos?

**Recomendado.** Aunque el sistema permite duplicados, es mejor usar alias únicos para evitar confusión (ej: "Docente-01", "Docente-02").

### ¿Qué información demográfica debo registrar?

Solo la relevante para su análisis, de forma anónima:
- ❌ **Evitar:** Nombre real, dirección, teléfono
- ✅ **Permitido:** Rango de edad, género, años de experiencia, ubicación general

### ¿Puedo exportar los datos de la Etapa 0?

**Sí.** Vaya a **Proyecto → Exportar** para descargar todos los datos en formato JSON o ZIP.

---

## Flujo Recomendado

```
┌──────────────────────────────────────────────────────────────────┐
│                    FLUJO DE ETAPA 0                              │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  1. PROTOCOLO   │
                    │  Documentar el  │
                    │  marco teórico  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   2. ACTORES    │
                    │  Registrar      │
                    │  participantes  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ 3. CONSENTIM.   │
                    │  Firma de cada  │◄──── ⚠️ Paso más olvidado
                    │  participante   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  4. MUESTREO    │
                    │  Criterios de   │
                    │  selección      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    5. PLAN      │
                    │  Estrategia de  │
                    │  análisis       │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  ✅ ETAPA 0     │
                    │   COMPLETA      │
                    │                 │
                    │ [Ir a Etapa 1]  │
                    └─────────────────┘
```

---

## Soporte

Si tiene problemas adicionales:

1. Revise los logs de la aplicación
2. Contacte al administrador del sistema
3. Consulte la documentación técnica en `/docs/`

---

*Manual creado: 18 de Enero de 2026*
