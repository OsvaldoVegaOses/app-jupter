# Análisis revisado: algoritmo `_link_codes_to_fragments` (asociación código → evidencias)

**Contexto**

APP_Jupter busca producir **insights accionables y auditables**, manteniendo **trazabilidad** desde el hallazgo hasta los fragmentos de evidencia (ver `docs/04-arquitectura/valor_negocio.md`). En ese marco, el algoritmo `_link_codes_to_fragments` cumple una función simple pero crítica: **adjuntar 1–3 fragmentos (IDs) por código sugerido** para que cada recomendación sea defendible en reporte y en bandeja.

Nota: esta auditabilidad mejora aún más cuando el **recorrido por entrevistas** también sigue un orden defendible (p. ej. por **orden de ingesta** o por **muestreo de máxima variación**). Ver `--interview-order` en `scripts/seed_loop_agent.py` (documentado en `docs/06-agente-autonomo/seed_loop_agent_mvp.md`).

**Link al algoritmo (fuente de verdad)**

- Implementación actual: [backend/routers/agent.py](../../backend/routers/agent.py#L178-L266)

---

## 1) Qué hace realmente (lectura estricta del código)

El algoritmo recibe:

- `codes: List[str]` (códigos sugeridos)
- `fragments: List[Dict]` (fragmentos candidatos; normalmente ya vienen **ordenados por score** desde discovery)
- `max_fragments_per_code` (por defecto `3`)

Y devuelve una lista de objetos con:

- `code`
- `fragments`: lista (0–3) con `fragmento_id`, `archivo`, `score`, y `preview`.

En términos operativos:

1) Construye un **pool** como prefijo `fragments[:pool_size]`.
2) Genera un orden de recorrido **determinístico** del pool por código (offset por `sha256(code)` + `idx`, y salto modular `stride` coprimo).
3) De esos candidatos, selecciona los **menos usados globalmente** en la corrida actual (contador `usage[fragmento_id]`).

Esto no intenta “probar” causalidad ni semántica entre código y fragmento. Su objetivo explícito es **asignar evidencia de forma reproducible y con cierta diversidad**, dentro de un pool razonable.

---

## 2) Qué garantías ofrece (y cuáles NO)

### Garantías (si el input es estable)

- **Determinismo**: para los mismos `codes` (mismo orden) y el mismo `fragments` (mismo orden), la selección es reproducible. Se evita depender de `hash()` (salado por sesión) usando `hashlib.sha256`.
- **Diversificación parcial**: el uso de `usage` tiende a “repartir” IDs entre códigos, **reduciendo** el fenómeno de “el mismo trío para todos”, especialmente cuando el pool es suficientemente grande.

### No-garantías (importante para comunicar correctamente)

- **No garantiza relevancia semántica** entre un código y un fragmento. La relevancia viene “prestada” del orden del pool (si discovery ordenó bien) y del hecho de trabajar dentro de un subconjunto top.
- **No garantiza ausencia de repetición** (ni de IDs, ni de tríos). Si el pool es pequeño vs. el número de códigos, o si hay muchos `fragmento_id` duplicados/ausentes, habrá reutilización.
- **Códigos idénticos no implican asignación idéntica**: aunque el `sha256(code)` sea igual, el algoritmo suma `idx`, por lo que el punto de inicio cambia y la selección puede variar.

---

## 3) Tradeoff real (por qué tiene sentido en producto)

Este diseño toma una postura pragmática:

- **Prioriza auditabilidad** (siempre devolver IDs) y **reproducibilidad** (mismo input ⇒ mismo output).
- **Introduce diversidad** como heurística de presentación (evitar concentración en pocos IDs).
- **Acepta un costo**: dentro del pool, la elección no optimiza por `score`, sino por “menor uso + orden determinístico”. Eso puede bajar la “calidad top-1” en favor de una evidencia más repartida.

En términos de valor de negocio, esto soporta el objetivo de **“insights auditables”**: el usuario siempre puede rastrear un código a fragmentos concretos, y la evidencia no parece “copiada/pegada” sistemáticamente.

---

## 4) Extracto del algoritmo (bloque clave)

Este extracto muestra el corazón de la diversificación determinística (offset/stride + balanceo por `usage`):

```python
# Offset determinístico por código (evita depender de hash() de Python que cambia por sesión)
h = hashlib.sha256(code.encode("utf-8")).hexdigest()
base = int(h[:8], 16)
start = (base + idx) % len(pool)

# Candidatos en orden determinístico; luego elegimos los menos usados globalmente.
candidates = []
for pos in range(len(pool)):
    frag = pool[(start + pos * stride) % len(pool)]
    frag_id = str(frag.get("fragmento_id") or "")
    if not frag_id:
        continue
    candidates.append((pos, frag_id, frag))

# Dedup por fragmento_id manteniendo el primer 'pos' (determinístico)
seen_ids = set()
unique = []
for pos, frag_id, frag in candidates:
    if frag_id in seen_ids:
        continue
    seen_ids.add(frag_id)
    unique.append((usage.get(frag_id, 0), pos, frag_id, frag))

unique.sort(key=lambda t: (t[0], t[1]))
chosen = unique[:max_fragments_per_code]
selected = [frag for _, _, _, frag in chosen]

for _, _, frag_id, _ in chosen:
    usage[frag_id] += 1
```

---

## 5) Sugerencia que sí aporta valor (convertir intuición en métrica)

Para que “diversidad” no sea un juicio cualitativo, conviene medirlo por corrida, por ejemplo:

- `unique_ids / total_ids` (cobertura)
- número de tríos únicos vs. total de códigos
- “top repeated triple count” (máxima repetición)

Esto permite decidir si la diversidad actual es suficiente para UX/auditoría, o si se requiere una restricción más dura (p. ej. “no repetir tríos” cuando el pool lo permita).
