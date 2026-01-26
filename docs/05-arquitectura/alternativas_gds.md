# Situación Actual y Estrategia para Etapas GDS

env/Scripts/Activate.ps1
(.venv) PS C:\Users\osval\Downloads\APP_Jupter> CALL gds.version() YIELD version

En línea: 1 Carácter: 18
+ CALL gds.version() YIELD version
+                  ~
Se esperaba una expresión después de '('.
    + CategoryInfo          : ParserError: (:) [], ParentContainsErrorRecordEx 
   ception
    + FullyQualifiedErrorId : ExpectedExpression
 
(.venv) PS C:\Users\osval\Downloads\APP_Jupter> RETURN version;
version : El término 'version' no se reconoce como nombre de un cmdlet, 
función, archivo de script o programa ejecutable. Compruebe si escribió 
correctamente el nombre o, si incluyó una ruta de acceso, compruebe que dicha 
ruta es correcta e inténtelo de nuevo.
En línea: 1 Carácter: 8
+ RETURN version;
+        ~~~~~~~
    + CategoryInfo          : ObjectNotFound: (version:String) [], CommandNotF  
   oundException
    + FullyQualifiedErrorId : CommandNotFoundException

## 2. Alternativas

### Alternativa A · Habilitar GDS en AuraDB (oficial)
- **Qué implica**: activar el plugin "Graph Analytics" en la consola AuraDB (o usar Aura Graph Analytics). Requiere plan Professional (≥4 GB RAM).
- **Cambios en código**: ninguno adicional; los comandos `axial gds` y `nucleus report` funcionarán como están.
- **Prós**:
  - Pipelines GDS oficiales (Louvain/PageRank/Betweenness) disponibles en Neo4j.
  - Menos mantenimiento: reutilizas procedimientos soportados por Neo4j.
  - Consistencia con documentación y soporte (Graph Data Connect, Aura).
- **Contras**:
  - Dependencia de infraestructura Neo4j (costos, permisos, administración de plugin).
  - Requiere activar el add-on (no disponible en planes básicos/free).

### Alternativa B · Instalar Neo4j local con GDS o Aura Graph Analytics diferente
- **Qué implica**: desplegar Neo4j Desktop/Standalone con el plugin GDS, o abrir una sesión "Graph Analytics" separada en Aura Graph Analytics y conectar el cliente.
- **Cambios en código**: ajustar `settings.neo4j` para apuntar a la instancia que sí tenga GDS.
- **Prós**:
  - Control total: puedes experimentar con versiones de GDS, usar pipelines ML avanzados sin costes Aura.
  - Laboratorio offline para validar algoritmos sin tocar la instancia productiva.
- **Contras**:
  - Gestión adicional: nuevas credenciales, configuración de seguridad, sincronización con datos ya ingeridos.
  - Requiere exportar/importar datos si cambias de instancia.

### Alternativa C · Mantener la arquitectura actual sin GDS
- **Qué implica**: saltar las etapas que dependen de GDS (Etapa 4 – auditoría automática; Etapa 5 – nucleus report) o sustituirlas por análisis manual.
- **Prós**:
  - Zero overhead adicional; todo sigue operativo en PG/Qdrant/Neo4j básico.
  - Puedes seguir documentando/visualizando grafos desde Neo4j Browser o exports manuales.
- **Contras**:
  - Se pierde automatización: centralidad, detección de comunidades y núcleo selectivo quedarían sin soporte programático.
  - Menor reproducibilidad: habría que anotar resultados manualmente.

### Alternativa D · Adoptar Graph Data Connect (GDC)
- **Qué implica**: migrar ingestión al pipeline oficial `graph-data-connect run ingest-unstructured`, con configuraciones declarativas.
- **Prós**:
  - Soporte oficial: pipelines reproducibles, manejo de embeddings integrado cuando se combina con Aura Graph Analytics.
  - Facilita adopción de nuevas fuentes sin mantener código.
- **Contras**:
  - Requiere reaprender el flujo; menos flexibilidad para personalizaciones (coalesce propio, metadatos a medida).
  - No reemplaza las integraciones actuales con Qdrant/PostgreSQL (habría que complementarlo).

## 3. Recomendación
- **Operación continua**: seguir usando la arquitectura actual (PG/Qdrant/Neo4j) para Etapas 3, 6, 7, 8, 9.
- **Para desbloquear GDS en Etapas 4 y 5**:
  1. Verifica en Aura que el plugin **Graph Analytics** esté habilitado.
  2. Si no es posible habilitarlo, despliega una instancia Neo4j con GDS (local/Aura Graph Analytics) y actualiza las credenciales.
  3. Como última opción, documenta las etapas con análisis manual/consultas Cypher sin algoritmos GDS.
- **Mediano plazo**: evalúa GDC si se desea un pipeline soportado oficialmente y reducir mantenimiento del código artesanal.

## 4. Acciones inmediatas
1. Registrar en `docs/reflexividad.md` la decisión sobre el uso de GDS.
2. Si se habilita el plugin, reintentar:
   ```powershell
   python main.py --env .env axial gds --algorithm louvain
   python main.py --env .env nucleus report --categoria "..." --prompt "..."
   ```
3. Si no se habilita, documentar en el informe cómo se estiman comunalidades/centralidades (p.ej., exportaciones manuales).

