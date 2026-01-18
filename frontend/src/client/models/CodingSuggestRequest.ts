/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CodingSuggestRequest = {
    project: string;
    fragment_id: string;
    top_k?: number;
    archivo?: (string | null);
    area_tematica?: (string | null);
    actor_principal?: (string | null);
    requiere_protocolo_lluvia?: (boolean | null);
    include_coded?: boolean;
    run_id?: (string | null);
    persist?: boolean;
    llm_model?: (string | null);
};

