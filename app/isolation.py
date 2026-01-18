"""
Helpers centralizados para aislamiento de datos por proyecto.

Este módulo proporciona funciones auxiliares para garantizar que todos
los accesos a datos estén correctamente filtrados por project_id.

Uso:
    from app.isolation import qdrant_project_filter, neo4j_project_clause

    # Qdrant
    filter = qdrant_project_filter("mi_proyecto", exclude_interviewer=True)
    client.search(..., query_filter=filter)

    # Neo4j
    clause = neo4j_project_clause("f")
    cypher = f"MATCH (f:Fragmento) WHERE {clause} RETURN f"
"""

from __future__ import annotations

from typing import Optional


def require_project_id(project_id: Optional[str]) -> str:
    """
    Valida que project_id sea válido y no vacío.
    
    Args:
        project_id: ID del proyecto
        
    Returns:
        project_id validado
        
    Raises:
        ValueError: Si project_id es None o vacío
    """
    if not project_id or not project_id.strip():
        raise ValueError("project_id es requerido para aislamiento de datos")
    return project_id.strip()


def qdrant_project_filter(
    project_id: str,
    exclude_interviewer: bool = False,
    additional_must: Optional[list] = None,
):
    """
    Genera un Filter de Qdrant para aislamiento por proyecto.
    
    Args:
        project_id: ID del proyecto
        exclude_interviewer: Excluir fragmentos del entrevistador
        additional_must: Condiciones adicionales opcionales
        
    Returns:
        qdrant_client.models.Filter configurado
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    must = [
        FieldCondition(key="project_id", match=MatchValue(value=project_id))
    ]
    
    if additional_must:
        must.extend(additional_must)
    
    must_not = []
    if exclude_interviewer:
        must_not.append(
            FieldCondition(key="speaker", match=MatchValue(value="interviewer"))
        )
    
    return Filter(
        must=must,
        must_not=must_not if must_not else None,
    )


def neo4j_project_clause(label: str = "n", param_name: str = "project_id") -> str:
    """
    Genera una cláusula WHERE para filtrado por project_id en Neo4j.
    
    Args:
        label: Alias del nodo en la consulta
        param_name: Nombre del parámetro para $project_id
        
    Returns:
        String de cláusula WHERE para Cypher
        
    Example:
        >>> neo4j_project_clause("f")
        'f.project_id = $project_id'
        >>> neo4j_project_clause("c", "pid")
        'c.project_id = $pid'
    """
    return f"{label}.project_id = ${param_name}"


def neo4j_project_match(label: str, node_type: str, param_name: str = "project_id") -> str:
    """
    Genera un patrón MATCH con project_id inline.
    
    Args:
        label: Alias del nodo
        node_type: Tipo de nodo (Fragmento, Codigo, etc.)
        param_name: Nombre del parámetro
        
    Returns:
        String de patrón MATCH
        
    Example:
        >>> neo4j_project_match("f", "Fragmento")
        '(f:Fragmento {project_id: $project_id})'
    """
    return f"({label}:{node_type} {{project_id: ${param_name}}})"


def pg_project_clause(column: str = "project_id") -> str:
    """
    Genera una cláusula WHERE para PostgreSQL.
    
    Args:
        column: Nombre de la columna
        
    Returns:
        String para usar con %s en psycopg2
        
    Example:
        >>> pg_project_clause()
        'project_id = %s'
    """
    return f"{column} = %s"


def pg_project_and_clause(column: str = "project_id") -> str:
    """
    Genera cláusula AND project_id para agregar a WHEREs existentes.
    
    Returns:
        String 'AND project_id = %s'
    """
    return f"AND {column} = %s"
