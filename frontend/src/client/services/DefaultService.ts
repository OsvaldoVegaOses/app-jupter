/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnalyzeRequest } from '../models/AnalyzeRequest';
import type { Body_login_for_access_token_token_post } from '../models/Body_login_for_access_token_token_post';
import type { CodingAssignRequest } from '../models/CodingAssignRequest';
import type { CodingSuggestRequest } from '../models/CodingSuggestRequest';
import type { CypherExportRequest } from '../models/CypherExportRequest';
import type { CypherRequest } from '../models/CypherRequest';
import type { CypherResponse } from '../models/CypherResponse';
import type { IngestRequest } from '../models/IngestRequest';
import type { PersistAnalysisRequest } from '../models/PersistAnalysisRequest';
import type { ProjectCreateRequest } from '../models/ProjectCreateRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Login For Access Token
     * @param formData
     * @returns any Successful Response
     * @throws ApiError
     */
    public static loginForAccessTokenTokenPost(
        formData: Body_login_for_access_token_token_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/token',
            formData: formData,
            mediaType: 'application/x-www-form-urlencoded',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Neo4J Query
     * @param requestBody
     * @param xApiKey
     * @returns CypherResponse Successful Response
     * @throws ApiError
     */
    public static neo4JQueryNeo4JQueryPost(
        requestBody: CypherRequest,
        xApiKey?: (string | null),
    ): CancelablePromise<CypherResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/neo4j/query',
            headers: {
                'X-API-Key': xApiKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Neo4J Export
     * @param requestBody
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static neo4JExportNeo4JExportPost(
        requestBody: CypherExportRequest,
        xApiKey?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/neo4j/export',
            headers: {
                'X-API-Key': xApiKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Healthcheck
     * @returns string Successful Response
     * @throws ApiError
     */
    public static healthcheckHealthzGet(): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/healthz',
        });
    }
    /**
     * Api Projects
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiProjectsApiProjectsGet(
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects',
            headers: {
                'X-API-Key': xApiKey,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Create Project
     * @param requestBody
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiCreateProjectApiProjectsPost(
        requestBody: ProjectCreateRequest,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects',
            headers: {
                'X-API-Key': xApiKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Status
     * @param project Proyecto requerido
     * @param updateState
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiStatusApiStatusGet(
        project: string,
        updateState: boolean = false,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/status',
            headers: {
                'X-API-Key': xApiKey,
            },
            query: {
                'project': project,
                'update_state': updateState,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Complete Stage
     * @param projectId
     * @param stage
     * @param runId
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiCompleteStageApiProjectsProjectIdStagesStageCompletePost(
        projectId: string,
        stage: string,
        runId?: (string | null),
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/projects/{project_id}/stages/{stage}/complete',
            path: {
                'project_id': projectId,
                'stage': stage,
            },
            headers: {
                'X-API-Key': xApiKey,
            },
            query: {
                'run_id': runId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Ingest
     * @param requestBody
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiIngestApiIngestPost(
        requestBody: IngestRequest,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ingest',
            headers: {
                'X-API-Key': xApiKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Coding Assign
     * @param requestBody
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiCodingAssignApiCodingAssignPost(
        requestBody: CodingAssignRequest,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/coding/assign',
            headers: {
                'X-API-Key': xApiKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Coding Suggest
     * @param requestBody
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiCodingSuggestApiCodingSuggestPost(
        requestBody: CodingSuggestRequest,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/coding/suggest',
            headers: {
                'X-API-Key': xApiKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Coding Stats
     * @param project Proyecto requerido
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiCodingStatsApiCodingStatsGet(
        project: string,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/coding/stats',
            headers: {
                'X-API-Key': xApiKey,
            },
            query: {
                'project': project,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Interviews
     * @param project Proyecto requerido
     * @param limit
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiInterviewsApiInterviewsGet(
        project: string,
        limit: number = 25,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/interviews',
            headers: {
                'X-API-Key': xApiKey,
            },
            query: {
                'limit': limit,
                'project': project,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Coding Codes
     * @param project Proyecto requerido
     * @param limit
     * @param search
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiCodingCodesApiCodingCodesGet(
        project: string,
        limit: number = 50,
        search?: (string | null),
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/coding/codes',
            headers: {
                'X-API-Key': xApiKey,
            },
            query: {
                'limit': limit,
                'search': search,
                'project': project,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Coding Fragments
     * @param archivo
     * @param project Proyecto requerido
     * @param limit
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiCodingFragmentsApiCodingFragmentsGet(
        archivo: string,
        project: string,
        limit: number = 25,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/coding/fragments',
            headers: {
                'X-API-Key': xApiKey,
            },
            query: {
                'archivo': archivo,
                'limit': limit,
                'project': project,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Coding Citations
     * @param codigo
     * @param project Proyecto requerido
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiCodingCitationsApiCodingCitationsGet(
        codigo: string,
        project: string,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/coding/citations',
            headers: {
                'X-API-Key': xApiKey,
            },
            query: {
                'codigo': codigo,
                'project': project,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Fragments Sample
     * @param project Proyecto requerido
     * @param limit
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiFragmentsSampleApiFragmentsSampleGet(
        project: string,
        limit: number = 8,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/fragments/sample',
            headers: {
                'X-API-Key': xApiKey,
            },
            query: {
                'limit': limit,
                'project': project,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Analyze
     * @param requestBody
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiAnalyzeApiAnalyzePost(
        requestBody: AnalyzeRequest,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/analyze',
            headers: {
                'X-API-Key': xApiKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Task Status
     * @param taskId
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getTaskStatusApiTasksTaskIdGet(
        taskId: string,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/tasks/{task_id}',
            path: {
                'task_id': taskId,
            },
            headers: {
                'X-API-Key': xApiKey,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Api Analyze Persist
     * @param requestBody
     * @param xApiKey
     * @returns any Successful Response
     * @throws ApiError
     */
    public static apiAnalyzePersistApiAnalyzePersistPost(
        requestBody: PersistAnalysisRequest,
        xApiKey?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/analyze/persist',
            headers: {
                'X-API-Key': xApiKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
