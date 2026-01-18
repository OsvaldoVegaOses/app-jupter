#!/usr/bin/env python
"""
Script para diagnosticar y corregir constraints de Neo4j.

Este script identifica constraints antiguas (sin project_id) que pueden
causar errores de ConstraintValidationFailed durante la ingesta, y las
reemplaza por las constraints compuestas correctas.

Uso:
    # Diagnosticar (ver constraints actuales)
    python scripts/fix_neo4j_constraints.py
    
    # Diagnosticar y corregir (eliminar antiguas, crear nuevas)
    python scripts/fix_neo4j_constraints.py --fix
    
    # Mostrar ayuda
    python scripts/fix_neo4j_constraints.py --help

Constraints esperadas (compuestas con project_id):
    - ent_nombre_project: (Entrevista.nombre, Entrevista.project_id)
    - frag_id_project: (Fragmento.id, Fragmento.project_id)
    - codigo_nombre_project: (Codigo.nombre, Codigo.project_id)
    - categoria_nombre_project: (Categoria.nombre, Categoria.project_id)
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.settings import load_settings
from app.clients import build_service_clients


# Constraints compuestas correctas (con project_id)
EXPECTED_CONSTRAINTS = {
    "ent_nombre_project": {
        "label": "Entrevista",
        "properties": ["nombre", "project_id"],
        "cypher": """
            CREATE CONSTRAINT ent_nombre_project IF NOT EXISTS 
            FOR (e:Entrevista) REQUIRE (e.nombre, e.project_id) IS UNIQUE
        """
    },
    "frag_id_project": {
        "label": "Fragmento", 
        "properties": ["id", "project_id"],
        "cypher": """
            CREATE CONSTRAINT frag_id_project IF NOT EXISTS 
            FOR (f:Fragmento) REQUIRE (f.id, f.project_id) IS UNIQUE
        """
    },
    "codigo_nombre_project": {
        "label": "Codigo",
        "properties": ["nombre", "project_id"],
        "cypher": """
            CREATE CONSTRAINT codigo_nombre_project IF NOT EXISTS 
            FOR (c:Codigo) REQUIRE (c.nombre, c.project_id) IS UNIQUE
        """
    },
    "categoria_nombre_project": {
        "label": "Categoria",
        "properties": ["nombre", "project_id"],
        "cypher": """
            CREATE CONSTRAINT categoria_nombre_project IF NOT EXISTS 
            FOR (c:Categoria) REQUIRE (c.nombre, c.project_id) IS UNIQUE
        """
    },
}

# Nombres de constraints antiguas conocidas (sin project_id)
LEGACY_CONSTRAINT_PATTERNS = [
    "ent_nombre",           # Antigua: solo nombre
    "frag_id",              # Antigua: solo id  
    "codigo_nombre",        # Antigua: solo nombre
    "categoria_nombre",     # Antigua: solo nombre
    "entrevista_nombre",    # Variante antigua
    "fragmento_id",         # Variante antigua
]


def get_all_constraints(session) -> list[dict]:
    """Obtiene todas las constraints de la base de datos."""
    result = session.run("SHOW CONSTRAINTS")
    constraints = []
    for record in result:
        constraints.append({
            "name": record.get("name"),
            "type": record.get("type"),
            "entityType": record.get("entityType"),
            "labelsOrTypes": record.get("labelsOrTypes"),
            "properties": record.get("properties"),
            "ownedIndex": record.get("ownedIndex"),
        })
    return constraints


def classify_constraints(constraints: list[dict]) -> dict:
    """Clasifica las constraints en correctas, antiguas y desconocidas."""
    result = {
        "correct": [],      # Constraints compuestas con project_id
        "legacy": [],       # Constraints antiguas sin project_id
        "unknown": [],      # Otras constraints
    }
    
    expected_names = set(EXPECTED_CONSTRAINTS.keys())
    
    for c in constraints:
        name = c.get("name", "")
        props = c.get("properties", [])
        
        # Es una constraint esperada (compuesta con project_id)
        if name in expected_names:
            result["correct"].append(c)
        # Es una constraint antigua conocida
        elif any(name == legacy or name.startswith(legacy + "_") for legacy in LEGACY_CONSTRAINT_PATTERNS):
            # Verificar que NO tiene project_id
            if "project_id" not in props:
                result["legacy"].append(c)
            else:
                result["correct"].append(c)
        # Constraint en labels relevantes pero sin project_id
        elif any(label in ["Entrevista", "Fragmento", "Codigo", "Categoria"] 
                 for label in (c.get("labelsOrTypes") or [])):
            if "project_id" not in props:
                result["legacy"].append(c)
            else:
                result["unknown"].append(c)
        else:
            result["unknown"].append(c)
    
    return result


def print_constraints_table(constraints: list[dict], title: str):
    """Imprime una tabla formateada de constraints."""
    if not constraints:
        print(f"\n{title}: (ninguna)")
        return
    
    print(f"\n{title}:")
    print("-" * 80)
    print(f"{'Nombre':<30} {'Label':<15} {'Propiedades':<30}")
    print("-" * 80)
    
    for c in constraints:
        name = c.get("name", "?")[:29]
        labels = ", ".join(c.get("labelsOrTypes") or ["?"])[:14]
        props = ", ".join(c.get("properties") or ["?"])[:29]
        print(f"{name:<30} {labels:<15} {props:<30}")
    
    print("-" * 80)


def drop_constraint(session, name: str) -> bool:
    """Elimina una constraint por nombre."""
    try:
        session.run(f"DROP CONSTRAINT {name} IF EXISTS")
        return True
    except Exception as e:
        print(f"  ⚠️  Error eliminando {name}: {e}")
        return False


def create_constraint(session, name: str, cypher: str) -> bool:
    """Crea una constraint usando el Cypher proporcionado."""
    try:
        session.run(cypher)
        return True
    except Exception as e:
        print(f"  ⚠️  Error creando {name}: {e}")
        return False


def diagnose(clients, settings):
    """Muestra diagnóstico de constraints actuales."""
    print("\n" + "=" * 80)
    print("DIAGNÓSTICO DE CONSTRAINTS NEO4J")
    print("=" * 80)
    
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        all_constraints = get_all_constraints(session)
        classified = classify_constraints(all_constraints)
        
        print_constraints_table(classified["correct"], "✅ CONSTRAINTS CORRECTAS (compuestas con project_id)")
        print_constraints_table(classified["legacy"], "⚠️  CONSTRAINTS ANTIGUAS (sin project_id - CONFLICTIVAS)")
        print_constraints_table(classified["unknown"], "ℹ️  OTRAS CONSTRAINTS")
        
        # Resumen
        print("\n" + "=" * 80)
        print("RESUMEN")
        print("=" * 80)
        print(f"  Total constraints: {len(all_constraints)}")
        print(f"  ✅ Correctas: {len(classified['correct'])}")
        print(f"  ⚠️  Antiguas (conflictivas): {len(classified['legacy'])}")
        print(f"  ℹ️  Otras: {len(classified['unknown'])}")
        
        if classified["legacy"]:
            print("\n⚠️  Se encontraron constraints antiguas que pueden causar")
            print("   errores ConstraintValidationFailed durante la ingesta.")
            print("\n   Ejecuta con --fix para corregirlas automáticamente:")
            print("   python scripts/fix_neo4j_constraints.py --fix")
        else:
            print("\n✅ No se encontraron constraints conflictivas.")
        
        # Verificar constraints faltantes
        existing_names = {c.get("name") for c in all_constraints}
        missing = [name for name in EXPECTED_CONSTRAINTS.keys() if name not in existing_names]
        
        if missing:
            print(f"\n⚠️  Constraints esperadas faltantes: {', '.join(missing)}")
            print("   Ejecuta con --fix para crearlas.")
        
        print("=" * 80)
        
        return classified


def fix_constraints(clients, settings):
    """Elimina constraints antiguas y crea las correctas."""
    print("\n" + "=" * 80)
    print("CORRECCIÓN DE CONSTRAINTS NEO4J")
    print("=" * 80)
    
    with clients.neo4j.session(database=settings.neo4j.database) as session:
        all_constraints = get_all_constraints(session)
        classified = classify_constraints(all_constraints)
        
        # 1. Eliminar constraints antiguas
        if classified["legacy"]:
            print("\n[1/2] Eliminando constraints antiguas...")
            for c in classified["legacy"]:
                name = c.get("name")
                if drop_constraint(session, name):
                    print(f"  ✅ Eliminada: {name}")
        else:
            print("\n[1/2] No hay constraints antiguas que eliminar.")
        
        # 2. Crear constraints correctas
        print("\n[2/2] Creando constraints compuestas...")
        existing_names = {c.get("name") for c in get_all_constraints(session)}
        
        for name, config in EXPECTED_CONSTRAINTS.items():
            if name in existing_names:
                print(f"  ✓ Ya existe: {name}")
            else:
                if create_constraint(session, name, config["cypher"]):
                    print(f"  ✅ Creada: {name}")
        
        # Verificar resultado
        print("\n" + "-" * 80)
        print("VERIFICACIÓN POST-CORRECCIÓN")
        print("-" * 80)
        
        final_constraints = get_all_constraints(session)
        final_classified = classify_constraints(final_constraints)
        
        print(f"  ✅ Constraints correctas: {len(final_classified['correct'])}")
        print(f"  ⚠️  Constraints antiguas: {len(final_classified['legacy'])}")
        
        if not final_classified["legacy"]:
            print("\n✅ CORRECCIÓN COMPLETADA EXITOSAMENTE")
            print("   Ahora puedes ejecutar la ingesta sin errores de constraint.")
        else:
            print("\n⚠️  Aún quedan constraints antiguas. Revisa manualmente.")
        
        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Diagnostica y corrige constraints de Neo4j",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/fix_neo4j_constraints.py           # Solo diagnóstico
  python scripts/fix_neo4j_constraints.py --fix     # Diagnóstico y corrección
        """
    )
    parser.add_argument(
        "--fix", 
        action="store_true", 
        help="Eliminar constraints antiguas y crear las correctas"
    )
    
    args = parser.parse_args()
    
    # Cargar configuración
    settings = load_settings()
    clients = build_service_clients(settings)
    
    try:
        if args.fix:
            fix_constraints(clients, settings)
        else:
            diagnose(clients, settings)
    finally:
        clients.close()


if __name__ == "__main__":
    main()
