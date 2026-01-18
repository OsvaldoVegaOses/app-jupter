"""
Operaciones de base de datos de grafos Neo4j.

Este módulo encapsula todas las operaciones con Neo4j para almacenamiento
de relaciones entre:
- Entrevistas y Fragmentos
- Categorías y Códigos (codificación axial)

Modelo de datos Neo4j:
    (:Entrevista)-[:CONTIENE]->(:Fragmento)
    (:Categoria)-[:TIPO_RELACION]->(:Codigo)
    
Tipos de relación válidos (ALLOWED_REL_TYPES):
    - "partede": Agrupación jerárquica (código pertenece a categoría)
    - "causa": Relación causal (A origina/causa B)
    - "condicion": Dependencia condicional (A depende de B)
    - "consecuencia": Resultado de (A es consecuencia de B)

Funciones principales:
    - ensure_constraints(): Crea constraints de unicidad básicos
    - ensure_category_constraints(): Constraint para Categorías
    - ensure_code_constraints(): Constraint para Códigos
    - merge_fragments(): Inserta Entrevistas y Fragmentos
    - merge_category_code_relationship(): Crea relaciones axiales
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from neo4j import Driver


# Tipos de relación válidos para codificación axial
ALLOWED_REL_TYPES = {"causa", "condicion", "consecuencia", "partede"}


def ensure_constraints(driver: Driver, database: str) -> None:
    """
    Crea constraints básicos para Entrevista y Fragmento.
    
    NOTA: Las constraints son compuestas por (nombre/id, project_id) para
    garantizar aislamiento entre proyectos.
    """
    with driver.session(database=database) as session:
        session.run("RETURN 'pong' AS ping")
        # Constraint compuesta para Entrevista: mismo nombre permitido en diferentes proyectos
        session.run("""
            CREATE CONSTRAINT ent_nombre_project IF NOT EXISTS 
            FOR (e:Entrevista) REQUIRE (e.nombre, e.project_id) IS UNIQUE
        """)
        # Constraint compuesta para Fragmento: mismo ID permitido en diferentes proyectos
        session.run("""
            CREATE CONSTRAINT frag_id_project IF NOT EXISTS 
            FOR (f:Fragmento) REQUIRE (f.id, f.project_id) IS UNIQUE
        """)


def ensure_code_constraints(driver: Driver, database: str) -> None:
    """
    Crea constraint de unicidad compuesta para nodos Codigo.
    
    Permite que diferentes proyectos tengan códigos con el mismo nombre
    sin colisión.
    """
    with driver.session(database=database) as session:
        session.run("""
            CREATE CONSTRAINT codigo_nombre_project IF NOT EXISTS 
            FOR (c:Codigo) REQUIRE (c.nombre, c.project_id) IS UNIQUE
        """)


def ensure_category_constraints(driver: Driver, database: str) -> None:
    """
    Crea constraint de unicidad compuesta para nodos Categoria.
    
    Permite que diferentes proyectos tengan categorías con el mismo nombre
    sin colisión.
    """
    with driver.session(database=database) as session:
        session.run("""
            CREATE CONSTRAINT categoria_nombre_project IF NOT EXISTS 
            FOR (c:Categoria) REQUIRE (c.nombre, c.project_id) IS UNIQUE
        """)


def merge_fragments(driver: Driver, database: str, rows: Iterable[Mapping[str, object]]) -> None:
    """
    Inserta o actualiza Entrevistas y Fragmentos en Neo4j.
    
    Crea nodos (:Entrevista) y (:Fragmento) con relación [:TIENE_FRAGMENTO].
    Usa MERGE con claves compuestas (nombre/id + project_id) para aislamiento.
    """
    cypher = """
    UNWIND $rows AS r
    MERGE (e:Entrevista {nombre: r.archivo, project_id: r.project_id})
      ON CREATE SET
        e.actor_principal = r.actor_principal,
        e.metadata = r.metadata,
        e.genero = r.genero,
        e.periodo = r.periodo
      ON MATCH SET
        e.actor_principal = coalesce(r.actor_principal, e.actor_principal),
        e.metadata = coalesce(r.metadata, e.metadata),
        e.genero = coalesce(r.genero, e.genero),
        e.periodo = coalesce(r.periodo, e.periodo)
    MERGE (f:Fragmento {id: r.id, project_id: r.project_id})
      ON CREATE SET
        f.texto = r.fragmento,
        f.par_idx = r.par_idx,
        f.char_len = r.char_len,
        f.actor_principal = r.actor_principal,
        f.metadata = r.metadata,
        f.genero = r.genero,
        f.periodo = r.periodo,
        f.speaker = r.speaker,
        f.interviewer_tokens = r.interviewer_tokens,
        f.interviewee_tokens = r.interviewee_tokens
      ON MATCH SET
        f.texto = coalesce(r.fragmento, f.texto),
        f.char_len = r.char_len,
        f.actor_principal = coalesce(r.actor_principal, f.actor_principal),
        f.metadata = coalesce(r.metadata, f.metadata),
        f.genero = coalesce(r.genero, f.genero),
        f.periodo = coalesce(r.periodo, f.periodo),
        f.speaker = coalesce(r.speaker, f.speaker),
        f.interviewer_tokens = coalesce(r.interviewer_tokens, f.interviewer_tokens),
        f.interviewee_tokens = coalesce(r.interviewee_tokens, f.interviewee_tokens)
    MERGE (e)-[rel:TIENE_FRAGMENTO]->(f)
      ON CREATE SET
        rel.char_len = r.char_len,
        rel.speaker = r.speaker
      ON MATCH SET
        rel.char_len = coalesce(r.char_len, rel.char_len),
        rel.speaker = coalesce(rel.speaker, r.speaker)
    """
    data = list(rows)
    if not data:
        return
    with driver.session(database=database) as session:
        session.run(cypher, rows=data)


def merge_fragment_code(driver: Driver, database: str, fragment_id: str, codigo: str, project_id: str) -> None:
    """
    Asocia un fragmento con un código en Neo4j.
    
    Crea relación (:Fragmento)-[:TIENE_CODIGO]->(:Codigo).
    Usa claves compuestas para aislamiento por proyecto.
    """
    cypher = """
    MATCH (f:Fragmento {id: $fragment_id, project_id: $project_id})
    MERGE (c:Codigo {nombre: $codigo, project_id: $project_id})
    MERGE (f)-[rel:TIENE_CODIGO]->(c)
    """
    with driver.session(database=database) as session:
        session.run(cypher, fragment_id=fragment_id, codigo=codigo, project_id=project_id)


def delete_fragment_code(driver: Driver, database: str, fragment_id: str, codigo: str, project_id: str) -> int:
    """
    Elimina la relación TIENE_CODIGO entre un fragmento y un código en Neo4j.
    
    Solo elimina la relación, NO elimina los nodos.
    Usa claves compuestas para garantizar aislamiento por proyecto.
    
    Args:
        driver: Driver de Neo4j
        database: Nombre de la base de datos
        fragment_id: ID del fragmento
        codigo: Nombre del código
        project_id: ID del proyecto
        
    Returns:
        Número de relaciones eliminadas (0 o 1)
    """
    cypher = """
    MATCH (f:Fragmento {id: $fragment_id, project_id: $project_id})
          -[rel:TIENE_CODIGO]->
          (c:Codigo {nombre: $codigo, project_id: $project_id})
    DELETE rel
    RETURN count(rel) as deleted
    """
    with driver.session(database=database) as session:
        result = session.run(cypher, fragment_id=fragment_id, codigo=codigo, project_id=project_id)
        record = result.single()
        return record["deleted"] if record else 0


def merge_category_code_relationship(
    driver: Driver,
    database: str,
    categoria: str,
    codigo: str,
    relacion: str,
    evidencia: Sequence[str],
    memo: str | None = None,
    project_id: str | None = None,
) -> None:
    """
    Crea una relación axial entre Categoria y Codigo.
    
    Esta es la función principal para persistir resultados de codificación axial.
    Usa claves compuestas para garantizar aislamiento por proyecto.
    
    Args:
        driver: Driver de Neo4j
        database: Nombre de la base de datos
        categoria: Nombre de la categoría axial
        codigo: Nombre del código a relacionar
        relacion: Tipo de relación (partede, causa, condicion, consecuencia)
        evidencia: Lista de IDs de fragmentos que soportan la relación
        memo: Nota explicativa opcional
        project_id: ID del proyecto (requerido para aislamiento)
        
    Raises:
        ValueError: Si el tipo de relación no es válido o falta project_id
    """
    if relacion not in ALLOWED_REL_TYPES:
        raise ValueError(f"Tipo de relacion '{relacion}' invalido.")
    if not project_id:
        raise ValueError("project_id es requerido para aislamiento entre proyectos")
    evidencia_unique = list(dict.fromkeys(evidencia))
    cypher = """
    MERGE (cat:Categoria {nombre: $categoria, project_id: $project_id})
    MERGE (cod:Codigo {nombre: $codigo, project_id: $project_id})
    MERGE (cat)-[rel:REL {tipo: $relacion}]->(cod)
    SET rel.evidencia = $evidencia,
        rel.memo = $memo,
        rel.actualizado_en = datetime()
    """
    with driver.session(database=database) as session:
        session.run(
            cypher,
            categoria=categoria,
            codigo=codigo,
            relacion=relacion,
            evidencia=evidencia_unique,
            memo=memo,
            project_id=project_id,
        )


def merge_category_code_relationships(
    driver: Driver,
    database: str,
    rows: Iterable[Mapping[str, object]],
) -> None:
    """
    Inserta relaciones axiales en batch.

    Cada row debe incluir: categoria, codigo, relacion, evidencia, memo, project_id.
    """
    data = list(rows)
    if not data:
        return
    cypher = """
    UNWIND $rows AS r
    MERGE (cat:Categoria {nombre: r.categoria, project_id: r.project_id})
    MERGE (cod:Codigo {nombre: r.codigo, project_id: r.project_id})
    MERGE (cat)-[rel:REL {tipo: r.relacion}]->(cod)
    SET rel.evidencia = r.evidencia,
        rel.memo = r.memo,
        rel.actualizado_en = datetime()
    """
    with driver.session(database=database) as session:
        session.run(cypher, rows=data)

