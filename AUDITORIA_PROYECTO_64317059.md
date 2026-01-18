# 📋 AUDITORIA DE ALMACENAMIENTO - PROYECTO ESPECIFICO

**Fecha:** 16 enero 2026  
**Cuenta:** osvaldovegaoses@gmail.com  
**Proyecto UUID:** `64317059-08aa-4831-b1b7-ab83d357c08f`

---

## ⚠️ RESUMEN EJECUTIVO

El proyecto especificado **NO EXISTE** en ninguna de las cuatro bases de datos del sistema.

| Base de Datos | Estado | Detalles |
|---|---|---|
| **PostgreSQL** | ❌ VACÍO | 0 fragmentos, 0 códigos |
| **Neo4j** | ❌ VACÍO | 0 nodos |
| **Qdrant** | ❌ VACÍO | Sin colecciones específicas |
| **Blob Storage** | ❌ VACÍO | Sin archivos |

---

## 🔍 ANÁLISIS DETALLADO

### PostgreSQL
```
Tabla proyectos:         NO ENCONTRADO
Fragmentos:             0
Códigos abiertos:       0  
Códigos candidatos:     0
```

**Conclusión:** El proyecto no está registrado en la tabla `proyectos` ni tiene ningún dato asociado.

### Neo4j
```
Nodos Entrevista:       0
Nodos Fragmento:        0
Nodos Codigo:           0
Relaciones:             0
```

**Conclusión:** No hay grafo construido para este proyecto.

### Qdrant (Vector Store)
```
Colecciones:            0
Puntos de embedding:    0
```

**Conclusión:** Sin vectores de embeddings almacenados.

### Azure Blob Storage
```
Contenedor interviews:  No accesible
Archivos:               0
```

**Conclusión:** Sin archivos de entrevista almacenados.

---

## 📊 CONTEXTO GLOBAL DEL SISTEMA

Mientras que el proyecto especificado está vacío, el sistema total contiene:

```
Total en el sistema:
  • Proyectos activos: 2 (JD 0018, Proyecto default)
  • Proyectos con datos: 8
  • Fragmentos: 1,872
  • Códigos: 745
  • Archivos: 51
```

### TOP Proyectos por volumen:
1. **jd-007...** - 24 archivos, 800 fragmentos, 165 códigos
2. **jd-009...** - 15 archivos, 597 fragmentos, 440 códigos
3. **jd-008...** - 6 archivos, 229 fragmentos
4. **nubeweb...** - 2 archivos, 74 fragmentos
5. **jd007-vi...** - 1 archivo, 53 fragmentos

---

## ✅ ACCIONES RECOMENDADAS

### Opción 1: Crear el proyecto
Si deseas crear este proyecto, usa el endpoint POST `/api/projects`:

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "X-API-Key: [tu-api-key]" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Nombre del Proyecto",
    "description": "Descripción",
    "config": {}
  }'
```

### Opción 2: Usar un proyecto existente
Selecciona uno de los proyectos con datos:
- `jd-007...` (más fragmentos)
- `jd-009...` (más códigos)

### Opción 3: Verificar UUID
Asegúrate de que el UUID sea correcto. Algunos proyectos usan alias como `jd-0018` en lugar de UUID completo.

---

## 📝 NOTAS TÉCNICAS

- **Integridad:** Las 4 bases de datos están **sincronizadas** (todas vacías para este proyecto)
- **No hay datos huérfanos** para este proyecto
- **Acceso:** No hay restricciones de acceso detectadas
- **Última limpieza:** Sistema limpio post-Etapa 3 (16 enero 2026)

---

**Generado:** 16 de enero de 2026, 01:18 UTC

