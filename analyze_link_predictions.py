"""
Convertir candidatos de Link Prediction en relaciones axiales.

Los candidatos de link_prediction representan SUGERENCIAS DE RELACIONES,
no asignaciones código-fragmento. Por lo tanto:
- NO se promocionan a analisis_codigos_abiertos
- SE pueden convertir en relaciones axiales en Neo4j
"""
from app.settings import load_settings
from app.clients import build_service_clients
import re

settings = load_settings()
clients = build_service_clients(settings)

PROJECT_ID = "jd-007"

print("=" * 70)
print("ANÁLISIS DE CANDIDATOS DE LINK PREDICTION")
print("=" * 70)

cur = clients.postgres.cursor()

# Obtener candidatos de link_prediction
cur.execute("""
    SELECT id, codigo, cita, score_confianza, fuente_detalle, estado
    FROM codigos_candidatos 
    WHERE project_id = %s AND fuente_origen = 'link_prediction'
    ORDER BY score_confianza DESC
""", (PROJECT_ID,))

candidatos = cur.fetchall()
print(f"\nTotal candidatos: {len(candidatos)}")

# Parsear las relaciones sugeridas
relaciones = []
for cid, codigo, cita, score, detalle, estado in candidatos:
    # Extraer source → target de la cita
    # Formato: "Relación sugerida: source → target"
    matches = re.findall(r'Relación sugerida: (.+?) → (.+?)(?:\||$)', cita)
    for source, target in matches:
        relaciones.append({
            'candidate_id': cid,
            'source': source.strip(),
            'target': target.strip(),
            'score': score,
            'estado': estado,
            'detalle': detalle[:80] if detalle else '',
        })

print(f"Relaciones parseadas: {len(relaciones)}")

# Mostrar relaciones únicas
print("\n📊 RELACIONES SUGERIDAS (únicas):")
seen = set()
unique_rels = []
for r in relaciones:
    key = (r['source'], r['target'])
    if key not in seen:
        seen.add(key)
        unique_rels.append(r)
        print(f"  {r['source']} → {r['target']}")
        print(f"    Score: {r['score']}, Estado: {r['estado']}")

print(f"\n✅ Relaciones únicas: {len(unique_rels)}")

# Verificar cuáles ya existen en Neo4j
print("\n" + "=" * 70)
print("VERIFICACIÓN EN NEO4J")
print("=" * 70)

existentes = 0
faltantes = []

with clients.neo4j.session() as session:
    for rel in unique_rels:
        result = session.run("""
            MATCH (s {nombre: $source, project_id: $pid})
            MATCH (t {nombre: $target, project_id: $pid})
            OPTIONAL MATCH (s)-[r:REL]->(t)
            RETURN s.nombre as source, t.nombre as target, 
                   r IS NOT NULL as exists
        """, source=rel['source'], target=rel['target'], pid=PROJECT_ID)
        
        rec = result.single()
        if rec and rec['exists']:
            existentes += 1
        else:
            faltantes.append(rel)

print(f"\n  Ya existen en Neo4j: {existentes}")
print(f"  Faltantes (candidatas a crear): {len(faltantes)}")

if faltantes:
    print("\n📋 Relaciones que se pueden crear:")
    for rel in faltantes[:10]:
        print(f"    {rel['source']} → {rel['target']}")

# Opciones de uso
print("\n" + "=" * 70)
print("💡 OPCIONES DE USO")
print("=" * 70)
print("""
1. CREAR RELACIONES AXIALES EN NEO4J
   - Usar confirm_hidden_relationship() para cada par
   - Marcadas como origen='descubierta'
   
2. EXPORTAR PARA REVISIÓN MANUAL
   - Generar CSV con las sugerencias
   - El investigador valida cuáles son relevantes
   
3. ALIMENTAR MEMOS ANALÍTICOS
   - Documentar las relaciones descubiertas
   - Justificar con los fragmentos de co-ocurrencia
   
4. MARCAR COMO RECHAZADO
   - Si las sugerencias no son útiles
   - Actualizar estado='rechazado' en codigos_candidatos
""")

clients.close()
