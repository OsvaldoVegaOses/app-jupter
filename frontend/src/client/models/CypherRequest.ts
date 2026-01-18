/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CypherRequest = {
    /**
     * Consulta Cypher a ejecutar en Neo4j.
     */
    cypher: string;
    /**
     * Proyecto requerido para la consulta.
     */
    project?: (string | null);
    /**
     * Diccionario de parámetros (clave->valor).
     */
    params?: (Record<string, any> | null);
    /**
     * Lista de formatos a devolver (raw, table, graph, all).
     */
    formats?: (Array<string> | null);
    /**
     * Base de datos Neo4j opcional.
     */
    database?: (string | null);
};

