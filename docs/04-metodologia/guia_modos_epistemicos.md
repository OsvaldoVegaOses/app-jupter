# Guía de Modos Epistemológicos

> **Versión:** 1.0  
> **Fecha:** Enero 2026  
> **Epic:** Epistemic Mode v1

---

## 1. Introducción

El sistema soporta dos modos epistemológicos que reflejan las principales corrientes de la Teoría Fundamentada (Grounded Theory). Cada modo configura automáticamente los prompts del LLM para generar análisis coherentes con el paradigma metodológico elegido.

**El modo se selecciona al crear el proyecto y no puede cambiarse una vez iniciada la codificación axial**, garantizando consistencia metodológica a lo largo del análisis.

---

## 2. Comparativa de Modos

| Aspecto | Constructivista (Charmaz) | Post-positivista (Glaser/Strauss) |
|---------|---------------------------|-----------------------------------|
| **Ícono UI** | 🟣 Purple badge | 🔵 Blue badge |
| **Ontología** | Realidad co-construida | Realidad objetiva descubrible |
| **Rol investigador** | Co-constructor activo | Observador neutral |
| **Códigos iniciales** | Gerundios (procesos) | Sustantivos (conceptos) |
| **Códigos in-vivo** | Priorizados | Usados con moderación |
| **Abstracción** | Gradual, situada | Temprana, sistemática |
| **Memos** | Reflexivos, posicionalidad | Conceptuales, teóricos |
| **Categorías axiales** | Relaciones fluidas | Modelo paradigmático rígido |
| **Teoría resultante** | Sustantiva, contextual | Formal, generalizable |

---

## 3. Modo Constructivista (Charmaz)

### 3.1 Cuándo elegir este modo

- Investigación cualitativa interpretativa
- Énfasis en procesos sociales y experiencias vividas
- El investigador reconoce su influencia en los datos
- Interés en perspectivas de los participantes
- Contexto social específico (no generalización)

### 3.2 Características del análisis

**Codificación abierta:**
- Códigos en gerundio: "Negociando identidad", "Resistiendo cambio"
- Prioriza códigos in-vivo (palabras exactas del participante)
- Captura acciones y procesos, no solo temas

**Codificación axial:**
- Relaciones flexibles entre categorías
- Permite múltiples conexiones simultáneas
- No requiere modelo paradigmático estricto

**Memos:**
- Reflexivos: incluyen posicionalidad del investigador
- Documentan decisiones metodológicas
- Exploran sesgos y preconcepciones

### 3.3 Ejemplo de código constructivista

```
Fragmento: "Cuando llegué a la empresa, nadie me explicó nada. Tuve que 
           aprender todo solo, preguntando aquí y allá."

Código: Navegando-la-incertidumbre-inicial
Tipo: Gerundio (proceso)
In-vivo: "preguntando aquí y allá"
Memo reflexivo: "El participante enfatiza agencia personal ante vacío 
                institucional. Mi experiencia similar puede sesgar mi 
                interpretación hacia crítica organizacional."
```

---

## 4. Modo Post-positivista (Glaser/Strauss)

### 4.1 Cuándo elegir este modo

- Investigación orientada a teoría formal
- Búsqueda de patrones generalizables
- Énfasis en rigor y sistematicidad
- Objetivo: descubrir teoría latente en datos
- Contextos comparables o estudios multi-sitio

### 4.2 Características del análisis

**Codificación abierta:**
- Códigos sustantivos: "Aislamiento institucional", "Autogestión"
- Abstracción temprana desde los datos
- Foco en conceptos, no acciones

**Codificación axial:**
- Modelo paradigmático: Condiciones → Fenómeno → Acciones → Consecuencias
- Relaciones causales explícitas
- Estructura jerárquica de categorías

**Memos:**
- Conceptuales: desarrollan propiedades y dimensiones
- Teóricos: conectan categorías emergentes
- Orientados a saturación teórica

### 4.3 Ejemplo de código post-positivista

```
Fragmento: "Cuando llegué a la empresa, nadie me explicó nada. Tuve que 
           aprender todo solo, preguntando aquí y allá."

Código: Déficit-de-onboarding
Tipo: Sustantivo (concepto)
Propiedades: intensidad (alta), duración (inicial), alcance (individual)
Dimensiones: formal-informal, institucional-personal
Memo teórico: "Categoría emergente 'Vacío institucional' agrupa códigos 
              de déficit de inducción. Propiedad: respuesta adaptativa 
              individual como mecanismo compensatorio."
```

---

## 5. Impacto en el Sistema

### 5.1 Prompts diferenciados

El sistema carga automáticamente prompts específicos según el modo:

| Stage | Constructivista | Post-positivista |
|-------|-----------------|------------------|
| `open_coding` | Gerundios, in-vivo | Sustantivos, abstracción |
| `axial_coding` | Relaciones fluidas | Modelo paradigmático |
| `discovery` | Exploración situada | Patrones emergentes |
| `selective` | Teoría sustantiva | Teoría formal |
| `memo` | Reflexivo | Conceptual |

### 5.2 Audit trail

Cada análisis incluye metadata de auditoría:

```json
{
  "_meta": {
    "epistemic_mode": "constructivist",
    "prompt_version": "constructivist_open_coding_v1+constructivist_system_base_v1",
    "analysis_schema_version": "2.0"
  }
}
```

### 5.3 Lock de modo

Una vez que el proyecto tiene relaciones axiales (`axial_relationships > 0`), el modo queda bloqueado. Esto previene inconsistencias metodológicas en el análisis.

---

## 6. Guía de Selección Rápida

```
¿Tu investigación busca...

┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  Comprender experiencias      →  🟣 CONSTRUCTIVISTA             │
│  situadas y procesos                                            │
│                                                                 │
│  Desarrollar teoría           →  🔵 POST-POSITIVISTA            │
│  generalizable                                                  │
│                                                                 │
│  ¿No estás seguro?            →  🟣 CONSTRUCTIVISTA             │
│  (es el default, más flexible)                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Referencias Metodológicas

### Constructivismo (Charmaz)
- Charmaz, K. (2014). *Constructing Grounded Theory* (2nd ed.). SAGE.
- Charmaz, K. (2006). *Constructing Grounded Theory: A Practical Guide*. SAGE.

### Post-positivismo (Glaser/Strauss)
- Glaser, B. G., & Strauss, A. L. (1967). *The Discovery of Grounded Theory*. Aldine.
- Strauss, A., & Corbin, J. (1998). *Basics of Qualitative Research* (2nd ed.). SAGE.
- Corbin, J., & Strauss, A. (2015). *Basics of Qualitative Research* (4th ed.). SAGE.

### Comparativas
- Bryant, A., & Charmaz, K. (Eds.). (2007). *The SAGE Handbook of Grounded Theory*. SAGE.
- Birks, M., & Mills, J. (2015). *Grounded Theory: A Practical Guide* (2nd ed.). SAGE.

---

## 8. FAQ

### ¿Puedo cambiar el modo después de crear el proyecto?
Sí, pero solo antes de crear la primera relación axial. Después, el modo queda bloqueado para mantener consistencia metodológica.

### ¿Qué pasa si elijo el modo incorrecto?
Si aún no tienes relaciones axiales, puedes cambiarlo desde la configuración del proyecto. Si ya tienes análisis axial, deberás crear un nuevo proyecto.

### ¿Los códigos existentes cambian si cambio el modo?
No. Los códigos ya creados permanecen intactos. Solo los nuevos análisis usarán los prompts del nuevo modo.

### ¿Puedo mezclar enfoques?
El sistema no lo recomienda por coherencia metodológica. Si tu investigación requiere triangulación de paradigmas, considera crear proyectos separados.

---

*Documento creado: Enero 2026 | Epic: Epistemic Mode v1*
