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
// Support both the explicit VITE_NEO4J_API_KEY and a legacy VITE_API_KEY env var
const DEFAULT_API_KEY_ENV = "VITE_NEO4J_API_KEY";
const LEGACY_API_KEY_ENV = "VITE_API_KEY";

export async function runNeo4jQuery(payload: Neo4jQueryRequest): Promise<Neo4jQueryResult> {
  const endpoint = import.meta.env.VITE_NEO4J_API_URL || DEFAULT_ENDPOINT;
  const envVars = import.meta.env as Record<string, string | undefined>;
  // prefer explicit VITE_NEO4J_API_KEY, fall back to legacy VITE_API_KEY for compatibility
  const apiKey = envVars[DEFAULT_API_KEY_ENV] || envVars[LEGACY_API_KEY_ENV];
  const headers: Record<string, string> = { "content-type": "application/json" };
  // By default we include the API key only when a non-default endpoint is
  // configured (i.e. a remote URL), to avoid leaking host env keys through the
  // local proxy. In some deployments the backend still expects the header even
  // when using the proxy; enable that behavior by setting
  // VITE_NEO4J_ALWAYS_SEND_API_KEY=true in the frontend env.
  const forceSend = Boolean(envVars.VITE_NEO4J_ALWAYS_SEND_API_KEY);
  const includeApiKey = Boolean(apiKey) && (endpoint !== DEFAULT_ENDPOINT || forceSend);
  if (includeApiKey && typeof apiKey === "string") {
    headers["X-API-Key"] = apiKey;
  }
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
  const envVars = import.meta.env as Record<string, string | undefined>;
  const apiKey = envVars[DEFAULT_API_KEY_ENV] || envVars[LEGACY_API_KEY_ENV];
  const headers: Record<string, string> = { "content-type": "application/json" };
  const includeApiKey = Boolean(apiKey) && endpoint !== DEFAULT_ENDPOINT;
  if (includeApiKey && typeof apiKey === "string") {
    headers["X-API-Key"] = apiKey;
  }
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
