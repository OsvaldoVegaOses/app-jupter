import type { Neo4jGraph, Neo4jTable } from "../types";

export type Neo4jFormat = "raw" | "table" | "graph";
export type Neo4jExportFormat = "csv" | "json";

export interface Neo4jQueryRequest {
  cypher: string;
  params?: Record<string, unknown>;
  formats?: Neo4jFormat[];
  database?: string;
  project: string;
}

export interface Neo4jQueryResponse {
  raw?: Array<Record<string, unknown>>;
  table?: Neo4jTable;
  graph?: Neo4jGraph;
}

export interface Neo4jQueryResult {
  data: Neo4jQueryResponse;
  durationMs?: number;
}

const DEFAULT_ENDPOINT = "/api/neo4j/query";

/**
 * Construye los headers de autenticación usando la misma lógica que api.ts:
 * 1. JWT Bearer token si el usuario está logueado
 * 2. X-API-Key como fallback (para desarrollo local o scripts)
 */
function buildAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  
  // Priority 1: JWT Bearer token from localStorage (producción con usuarios logueados)
  const authToken = localStorage.getItem("access_token");
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
    return headers;
  }
  
  // Priority 2: API Key fallback (desarrollo local o integraciones)
  const envVars = import.meta.env as Record<string, string | undefined>;
  const apiKey = envVars.VITE_NEO4J_API_KEY || envVars.VITE_API_KEY;
  const endpoint = envVars.VITE_NEO4J_API_URL || DEFAULT_ENDPOINT;
  const forceSend = Boolean(envVars.VITE_NEO4J_ALWAYS_SEND_API_KEY);
  
  // Incluir API Key si: hay key Y (es endpoint remoto O forceSend está activo)
  const includeApiKey = Boolean(apiKey) && (endpoint !== DEFAULT_ENDPOINT || forceSend);
  if (includeApiKey && typeof apiKey === "string") {
    headers["X-API-Key"] = apiKey;
  }
  
  return headers;
}

export async function runNeo4jQuery(payload: Neo4jQueryRequest): Promise<Neo4jQueryResult> {
  const endpoint = import.meta.env.VITE_NEO4J_API_URL || DEFAULT_ENDPOINT;
  const headers = buildAuthHeaders();
  
  const response = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const text = await response.text();
    let errorMessage = text || `Error ${response.status}`;
    // Try to extract 'detail' field from FastAPI JSON error response
    try {
      const parsed = JSON.parse(text);
      if (parsed.detail) {
        errorMessage = parsed.detail;
      }
    } catch {
      // Not JSON, use raw text
    }
    throw new Error(errorMessage);
  }
  const durationHeader = response.headers?.get?.("X-Query-Duration") ?? undefined;
  const durationMs = durationHeader ? Number(durationHeader) : undefined;
  return {
    data: (await response.json()) as Neo4jQueryResponse,
    durationMs: Number.isFinite(durationMs) ? durationMs : undefined,
  };
}

export async function exportNeo4jQuery(
  payload: Neo4jQueryRequest,
  format: Neo4jExportFormat = "csv"
): Promise<{ blob: Blob; durationMs?: number }> {
  const endpoint = import.meta.env.VITE_NEO4J_API_URL || DEFAULT_ENDPOINT;
  const baseUrl = endpoint.replace(/\/?query\/?$/, "");
  const exportUrl = (baseUrl || endpoint).replace(/\/$/, "") + "/export";
  const headers = buildAuthHeaders();
  
  const response = await fetch(exportUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({ ...payload, export_format: format }),
  });
  if (!response.ok) {
    const text = await response.text();
    let errorMessage = text || `Error ${response.status}`;
    // Try to extract 'detail' field from FastAPI JSON error response
    try {
      const parsed = JSON.parse(text);
      if (parsed.detail) {
        errorMessage = parsed.detail;
      }
    } catch {
      // Not JSON, use raw text
    }
    throw new Error(errorMessage);
  }
  const durationHeader = response.headers?.get?.("X-Query-Duration") ?? undefined;
  const durationMs = durationHeader ? Number(durationHeader) : undefined;
  const blob = await response.blob();
  return {
    blob,
    durationMs: Number.isFinite(durationMs) ? durationMs : undefined,
  };
}
