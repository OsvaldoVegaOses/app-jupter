/**
 * @fileoverview Cliente HTTP genérico para comunicación con el backend.
 * 
 * Este módulo proporciona funciones wrapper sobre fetch() que:
 * - Construyen URLs usando VITE_API_BASE
 * - Añaden header X-API-Key automáticamente
 * - Establecen Content-Type: application/json
 * - Manejan errores HTTP de forma consistente
 * 
 * Variables de entorno soportadas:
 * - VITE_API_BASE: URL base del backend (preferido)
 * - VITE_BACKEND_URL: Alias legacy
 * - VITE_NEO4J_API_KEY: API key para autenticación
 * - VITE_API_KEY: Alias legacy
 * 
 * @example
 * import { apiFetchJson } from './services/api';
 * const data = await apiFetchJson<ProjectEntry[]>('/api/projects');
 * 
 * @module services/api
 */

import type { CodingNextResponse } from "../types";

// IMPORTANTE: VITE_BACKEND_URL es para el proxy de Vite, NO para el navegador.
// API_BASE puede ser vacío (usa proxy) o una URL absoluta (llamada directa al backend).
const API_BASE = import.meta.env.VITE_API_BASE || "";
const BACKEND_PROXY = import.meta.env.VITE_BACKEND_URL || "";
// Support both VITE_NEO4J_API_KEY (explicit) and legacy VITE_API_KEY
const API_KEY = import.meta.env.VITE_NEO4J_API_KEY || import.meta.env.VITE_API_KEY;
// Session ID único por sesión de navegador (para logs por sesión)
const SESSION_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

// =============================================================================
// API Error Event System
// =============================================================================

export interface ApiErrorEvent {
  status: number;
  message: string;
  path: string;
  timestamp: Date;
}

/**
 * Dispatch a global API error event that can be listened to by UI components.
 */
function dispatchApiError(status: number, message: string, path: string): void {
  const event = new CustomEvent<ApiErrorEvent>("api-error", {
    detail: {
      status,
      message,
      path,
      timestamp: new Date(),
    },
  });
  window.dispatchEvent(event);
}

// =============================================================================
// Retry Logic with Exponential Backoff
// =============================================================================

export interface RetryOptions {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  retryOn?: (response: Response) => boolean;
}

const DEFAULT_RETRY_OPTIONS: Required<RetryOptions> = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 10000,
  retryOn: (response: Response) => response.status >= 500 || response.status === 429,
};

/**
 * Sleep for a specified number of milliseconds.
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Calculate delay with exponential backoff and jitter.
 */
function calculateBackoff(attempt: number, baseDelay: number, maxDelay: number): number {
  const exponentialDelay = baseDelay * Math.pow(2, attempt);
  const jitter = Math.random() * 0.3 * exponentialDelay;
  return Math.min(exponentialDelay + jitter, maxDelay);
}

// =============================================================================
// Core API Functions
// =============================================================================

function buildUrl(path: string): string {
  if (!path.startsWith("/")) {
    return `${API_BASE}/${path}`;
  }
  return `${API_BASE}${path}`;
}

if (import.meta.env.DEV && API_BASE && BACKEND_PROXY && API_BASE !== BACKEND_PROXY) {
  // Avoid silent misconfiguration when mixing proxy and direct URLs.
  console.warn(
    "[api] VITE_API_BASE y VITE_BACKEND_URL apuntan a hosts distintos. " +
      "Usa proxy (VITE_API_BASE vacío) o unifica ambos valores."
  );
}

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

// =============================================================================
// Token Refresh Singleton (Sprint 31 - Fix race condition)
// =============================================================================
// Evita múltiples refresh concurrentes cuando varias requests fallan con 401
// simultáneamente. Solo un refresh se ejecuta; las demás esperan el resultado.

let _refreshPromise: Promise<boolean> | null = null;

async function refreshTokenSingleton(): Promise<boolean> {
  // Si ya hay un refresh en progreso, esperamos su resultado
  if (_refreshPromise) {
    console.log("[API] Waiting for existing token refresh...");
    return _refreshPromise;
  }

  // Crear nueva promesa de refresh
  _refreshPromise = (async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) {
      console.warn("[API] No refresh token available");
      return false;
    }

    try {
      console.log("[API] Starting singleton token refresh...");
      const refreshUrl = buildUrl("/api/auth/refresh");
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout

      const refreshResponse = await fetch(refreshUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (refreshResponse.ok) {
        const data = await refreshResponse.json();
        localStorage.setItem("access_token", data.access_token);
        console.log("[API] Token refresh successful");
        return true;
      } else {
        console.warn("[API] Token refresh failed:", refreshResponse.status);
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user");
        window.dispatchEvent(new CustomEvent("auth-session-expired"));
        return false;
      }
    } catch (err) {
      console.error("[API] Token refresh error:", err);
      return false;
    }
  })();

  try {
    return await _refreshPromise;
  } finally {
    _refreshPromise = null; // Limpiar para permitir futuros refreshes
  }
}

async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs = 30000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function apiFetch(
  path: string,
  options: RequestInit = {},
  retryOptions?: RetryOptions,
  _isRefreshRetry = false,  // Internal flag to prevent infinite loops
  timeoutMs = 30000  // Configurable timeout (default 30s, use 60000+ for runners)
): Promise<Response> {
  const url = buildUrl(path);
  const headers: Record<string, string> = {};

  // Priority 1: JWT Bearer token from localStorage (Sprint 20: fixed key name)
  const authToken = localStorage.getItem("access_token");
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  // Priority 2: API Key (fallback for scripts/integrations)
  else if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }

  headers["X-Session-ID"] = SESSION_ID;

  if (options.headers) {
    Object.assign(headers, options.headers as Record<string, string>);
  }

  const needsJson =
    options.body && !(headers["content-type"] || headers["Content-Type"]);
  if (needsJson) {
    headers["content-type"] = "application/json";
  }

  const retry = { ...DEFAULT_RETRY_OPTIONS, ...retryOptions };
  let lastError: Error | null = null;
  let lastResponse: Response | null = null;

  for (let attempt = 0; attempt <= retry.maxRetries; attempt++) {
    try {
      const response = await fetchWithTimeout(url, { ...options, headers }, timeoutMs);

      // If response is OK, return it
      if (response.ok) {
        return response;
      }

      // Sprint 20/31: Handle 401 with automatic token refresh (using singleton)
      if (response.status === 401 && !_isRefreshRetry) {
        console.log("[API] Access token expired, attempting refresh...");
        const refreshSuccess = await refreshTokenSingleton();
        if (refreshSuccess) {
          console.log("[API] Token refreshed successfully, retrying request...");
          // Retry original request with new token (marked as refresh retry)
          return apiFetch(path, options, retryOptions, true, timeoutMs);
        }
        // Refresh failed - session expired event was already dispatched by singleton
      }

      // Check if we should retry (for 5xx errors)
      if (attempt < retry.maxRetries && retry.retryOn(response)) {
        const delay = calculateBackoff(attempt, retry.baseDelayMs, retry.maxDelayMs);
        console.warn(`[API] Request to ${path} failed with ${response.status}, retrying in ${Math.round(delay)}ms (attempt ${attempt + 1}/${retry.maxRetries})`);
        await sleep(delay);
        continue;
      }

      // No more retries, dispatch error event and throw
      lastResponse = response;
      const detail = await response.text();
      const errorMessage = detail || `Error ${response.status}`;

      dispatchApiError(response.status, errorMessage, path);
      throw new Error(errorMessage);

    } catch (err) {
      // Handle network errors (fetch itself failed)
      if (err instanceof TypeError && err.message === "Failed to fetch") {
        if (attempt < retry.maxRetries) {
          const delay = calculateBackoff(attempt, retry.baseDelayMs, retry.maxDelayMs);
          console.warn(`[API] Network error for ${path}, retrying in ${Math.round(delay)}ms (attempt ${attempt + 1}/${retry.maxRetries})`);
          await sleep(delay);
          lastError = err;
          continue;
        }
        dispatchApiError(0, "No se pudo conectar al servidor. Verifica que el backend esté corriendo.", path);
        throw new Error("No se pudo conectar al servidor. Verifica que el backend esté corriendo.");
      }

      if (isAbortError(err)) {
        const timeoutSec = Math.round(timeoutMs / 1000);
        const timeoutMsg = `Timeout en ${path}: El servidor no respondió en ${timeoutSec}s. Verifica que el backend esté activo.`;
        dispatchApiError(0, timeoutMsg, path);
        throw new Error(timeoutMsg);
      }

      // Re-throw other errors
      throw err;
    }
  }

  // Should not reach here, but just in case
  if (lastError) {
    throw lastError;
  }
  if (lastResponse) {
    const detail = await lastResponse.text();
    throw new Error(detail || `Error ${lastResponse.status}`);
  }
  throw new Error("Unknown error in apiFetch");
}

export async function apiFetchJson<T>(
  path: string,
  options: RequestInit = {},
  retryOptions?: RetryOptions,
  timeoutMs = 30000  // Configurable timeout (default 30s, use 60000+ for runners)
): Promise<T> {
  const response = await apiFetch(path, options, retryOptions, false, timeoutMs);
  return (await response.json()) as T;
}

// =============================================================================
// Fase 1.5 — Code ID Transition (Admin / Maintenance)
// =============================================================================

export async function codeIdStatus(project: string): Promise<any> {
  return apiFetchJson(`/api/admin/code-id/status?project=${encodeURIComponent(project)}`);
}

export async function codeIdInconsistencies(project: string, limit = 50): Promise<any> {
  return apiFetchJson(
    `/api/admin/code-id/inconsistencies?project=${encodeURIComponent(project)}&limit=${encodeURIComponent(
      String(limit)
    )}`
  );
}

export async function codeIdBackfill(
  project: string,
  payload: {
    mode: "code_id" | "canonical_code_id" | "all";
    dry_run: boolean;
    confirm: boolean;
    batch_size: number;
  }
): Promise<any> {
  return apiFetchJson(`/api/admin/code-id/backfill?project=${encodeURIComponent(project)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function codeIdRepair(
  project: string,
  payload: {
    action: "derive_text_from_id" | "derive_id_from_text" | "fix_self_pointing_mapped";
    dry_run: boolean;
    confirm: boolean;
    batch_size: number;
  }
): Promise<any> {
  return apiFetchJson(`/api/admin/code-id/repair?project=${encodeURIComponent(project)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// =============================================================================
// Ontology Freeze (pre-axialidad)
// =============================================================================

export async function ontologyFreezeStatus(project: string): Promise<any> {
  return apiFetchJson(`/api/admin/ontology/freeze?project=${encodeURIComponent(project)}`);
}

export async function ontologyFreezeSet(
  project: string,
  payload: {
    note?: string | null;
  }
): Promise<any> {
  return apiFetchJson(`/api/admin/ontology/freeze/freeze?project=${encodeURIComponent(project)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function ontologyFreezeBreak(
  project: string,
  payload: {
    confirm: boolean;
    phrase: string;
    note?: string | null;
  }
): Promise<any> {
  return apiFetchJson(`/api/admin/ontology/freeze/break?project=${encodeURIComponent(project)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteFileData(project: string, file: string): Promise<any> {
  return apiFetchJson("/api/maintenance/delete_file", {
    method: "POST",
    body: JSON.stringify({ project, file }),
  });
}

// =============================================================================
// Admin Ops Panel (Ergonomía operativa)
// =============================================================================

export type AdminOpsOutcome = "OK" | "NOOP" | "ERROR" | "UNKNOWN";

export type AdminOpsRun = {
  request_id: string;
  session_id?: string;
  project_id?: string;
  timestamp?: string;
  path?: string;
  http_method?: string;
  status_code?: number;
  duration_ms?: number;
  event?: string;
  is_error?: boolean;
  dry_run?: boolean;
  confirm?: boolean;
  batch_size?: number;
  mode?: string;
  action?: string;
  updated?: any;
  admin_id?: string;
};

export type AdminOpsFilters = {
  kind?: "all" | "errors" | "mutations";
  op?: "all" | "backfill" | "repair" | "sync" | "maintenance" | "ontology";
  intent?: "all" | "write_intent_post";
  since?: string; // ISO
  until?: string; // ISO
};

export async function adminOpsRecent(
  project: string,
  limit = 20,
  filters: AdminOpsFilters = {}
): Promise<{ runs: AdminOpsRun[] }> {
  const params = new URLSearchParams();
  params.set("project", project);
  params.set("limit", String(limit));
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.op) params.set("op", filters.op);
  if (filters.intent) params.set("intent", filters.intent);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  return apiFetchJson(`/api/admin/ops/recent?${params.toString()}`);
}

export async function adminOpsLog(
  project: string,
  session: string,
  requestId?: string,
  tail = 400
): Promise<{ records: any[] }> {
  const rid = requestId ? `&request_id=${encodeURIComponent(requestId)}` : "";
  return apiFetchJson(
    `/api/admin/ops/log?project=${encodeURIComponent(project)}&session=${encodeURIComponent(session)}${rid}&tail=${encodeURIComponent(
      String(tail)
    )}`
  );
}

// Ejecuta un POST admin con headers extra (p.ej. X-Session-ID único por ejecución)
export async function adminPostJson<T>(
  path: string,
  payload: any,
  extraHeaders: Record<string, string> = {},
  timeoutMs = 60000
): Promise<T> {
  return apiFetchJson<T>(
    path,
    {
      method: "POST",
      headers: {
        ...(extraHeaders || {}),
      },
      body: JSON.stringify(payload),
    },
    undefined,
    timeoutMs
  );
}

// =============================================================================
// Stage 0 (Etapa 0: Preparación)
// =============================================================================

export type Stage0StatusResponse = {
  project: string;
  ready: boolean;
  checks: {
    protocol: boolean;
    actors: boolean;
    consents: boolean;
    sampling: boolean;
    analysis_plan: boolean;
  };
  counters: {
    protocols: number;
    actors: number;
    actors_missing_consent: number;
    sampling_versions: number;
    plan_versions: number;
  };
  override: null | {
    override_id: string;
    scope: "ingest" | "analyze" | "both";
    reason_category: string;
    requested_by: string;
    approved_by: string;
    approved_at?: string | null;
    expires_at?: string | null;
  };
  latency_ms?: number;
  timestamp?: string;
};

export type Stage0VersionedDocIn = {
  version: number;
  title?: string;
  content: Record<string, any>;
  status?: string;
};

export type Stage0Protocol = {
  project_id: string;
  version: number;
  title?: string | null;
  content: Record<string, any>;
  status?: string | null;
  created_by?: string | null;
  created_at?: string | null;
};

export type Stage0ProtocolLatestResponse = {
  project: string;
  protocol: Stage0Protocol | null;
};

export type Stage0Actor = {
  actor_id: string;
  alias: string;
  demographics_anon: Record<string, any>;
  tags?: Record<string, any> | null;
  notes?: string | null;
  created_at?: string | null;
  has_active_consent?: boolean;
  latest_consent_version?: number | null;
  latest_signed_at?: string | null;
};

export type Stage0ActorsResponse = {
  project: string;
  actors: Stage0Actor[];
};

export type Stage0ActorIn = {
  alias: string;
  demographics_anon: Record<string, any>;
  tags?: Record<string, any> | null;
  notes?: string | null;
};

export type Stage0ConsentIn = {
  version: number;
  signed_at?: string | null;
  scope: Record<string, any>;
  evidence_url?: string | null;
  notes?: string | null;
};

export type Stage0SamplingLatestResponse = {
  project: string;
  sampling: null | {
    project_id: string;
    version: number;
    content: Record<string, any>;
    created_by?: string | null;
    created_at?: string | null;
  };
};

export type Stage0AnalysisPlanLatestResponse = {
  project: string;
  analysis_plan: null | {
    project_id: string;
    version: number;
    content: Record<string, any>;
    created_by?: string | null;
    created_at?: string | null;
  };
};

export type Stage0OverrideRequestIn = {
  scope: "ingest" | "analyze" | "both";
  reason_category: "critical_incident" | "data_validation" | "service_continuity" | "protocol_exception" | "other";
  reason_details: string;
  requested_expires_hours: number;
};

export type Stage0OverrideDecisionIn = {
  decision_note: string;
  expires_hours: number;
};

export type Stage0OverrideEntry = {
  override_id: string;
  scope: "ingest" | "analyze" | "both";
  status: "pending" | "approved" | "rejected" | string;
  reason_category: string;
  reason_details?: string;
  requested_by?: string | null;
  requested_at?: string | null;
  decided_by?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
  expires_at?: string | null;
};

export type Stage0OverridesResponse = {
  project: string;
  overrides: Stage0OverrideEntry[];
};

export async function getStage0Status(project: string): Promise<Stage0StatusResponse> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/status?${params.toString()}`);
}

export async function getStage0ProtocolLatest(project: string): Promise<Stage0ProtocolLatestResponse> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/protocol/latest?${params.toString()}`);
}

export async function upsertStage0Protocol(project: string, payload: Stage0VersionedDocIn): Promise<any> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/protocol?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listStage0Actors(project: string): Promise<Stage0ActorsResponse> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/actors?${params.toString()}`);
}

export async function createStage0Actor(project: string, payload: Stage0ActorIn): Promise<any> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/actors?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createStage0Consent(project: string, actorId: string, payload: Stage0ConsentIn): Promise<any> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/actors/${encodeURIComponent(actorId)}/consents?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getStage0SamplingLatest(project: string): Promise<Stage0SamplingLatestResponse> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/sampling/latest?${params.toString()}`);
}

export async function upsertStage0Sampling(project: string, payload: Stage0VersionedDocIn): Promise<any> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/sampling?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getStage0AnalysisPlanLatest(project: string): Promise<Stage0AnalysisPlanLatestResponse> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/analysis-plan/latest?${params.toString()}`);
}

export async function upsertStage0AnalysisPlan(project: string, payload: Stage0VersionedDocIn): Promise<any> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/analysis-plan?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function requestStage0Override(project: string, payload: Stage0OverrideRequestIn): Promise<any> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/overrides?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getStage0Overrides(project: string, limit = 50): Promise<Stage0OverridesResponse> {
  const params = new URLSearchParams({ project, limit: String(limit) });
  return apiFetchJson(`/api/stage0/overrides?${params.toString()}`);
}

export async function approveStage0Override(project: string, overrideId: string, payload: Stage0OverrideDecisionIn): Promise<any> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/overrides/${encodeURIComponent(overrideId)}/approve?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function rejectStage0Override(project: string, overrideId: string, payload: Stage0OverrideDecisionIn): Promise<any> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/stage0/overrides/${encodeURIComponent(overrideId)}/reject?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// =============================================================================
// Familiarization (Etapa 2) progress tracking
// =============================================================================

export type FamiliarizationReviewsResponse = {
  project: string;
  total_interviews: number;
  reviewed_count: number;
  percentage: number;
  reviewed_files: Array<{ archivo: string; reviewed_at?: string | null; reviewed_by?: string | null }>;
};

export async function getFamiliarizationReviews(project: string): Promise<FamiliarizationReviewsResponse> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/familiarization/reviews?${params.toString()}`);
}

export async function setFamiliarizationReviewed(project: string, archivo: string, reviewed: boolean): Promise<FamiliarizationReviewsResponse> {
  return apiFetchJson("/api/familiarization/reviews", {
    method: "POST",
    body: JSON.stringify({ project, archivo, reviewed }),
  });
}

// =============================================================================
// Codificación abierta (Etapa 3) - Guided v1
// =============================================================================

export type CodingFeedbackAction = "accept" | "reject" | "edit";

export async function getCodingNext(params: {
  project: string;
  archivo?: string;
  strategy?: "recent" | "oldest" | "random";
  exclude_fragment_id?: string[];
}): Promise<CodingNextResponse> {
  const qs = new URLSearchParams({ project: params.project });
  if (params.archivo) qs.set("archivo", params.archivo);
  if (params.strategy) qs.set("strategy", params.strategy);
  for (const fid of params.exclude_fragment_id || []) {
    const clean = String(fid || "").trim();
    if (clean) qs.append("exclude_fragment_id", clean);
  }
  return apiFetchJson(`/api/coding/next?${qs.toString()}`);
}

export async function postCodingFeedback(payload: {
  project: string;
  fragmento_id: string;
  action: CodingFeedbackAction;
  suggested_code?: string | null;
  final_code?: string | null;
  meta?: Record<string, unknown>;
}): Promise<{ ok: boolean;[key: string]: unknown }> {
  return apiFetchJson(`/api/coding/feedback`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// =============================================================================
// Sprint 9: GraphRAG, Discovery API, Link Prediction
// =============================================================================

/** GraphRAG query request */
export interface GraphRAGRequest {
  query: string;
  project?: string;
  include_fragments?: boolean;
  chain_of_thought?: boolean;
  node_ids?: Array<string | number>;
}

/** GraphRAG response */
export interface GraphRAGResponse {
  query: string;
  answer: string;
  context: string;
  nodes: Array<{ id: string; type: string; centralidad?: number }>;
  relationships: Array<{ from: string; to: string; type: string }>;
  fragments: Array<{ fragmento_id: string; fragmento: string; archivo: string }>;
}

/** Discovery search request */
export interface DiscoverRequest {
  positive_texts: string[];
  negative_texts?: string[];
  target_text?: string;
  top_k?: number;
  project?: string;
}

/** Discovery search response */
export interface DiscoverResponse {
  fragments: Array<{
    id: string | number;
    score: number;
    payload?: any;
    fragmento?: string;
    archivo?: string;
    fragmento_id?: string;
  }>;
  count: number;
}

export interface GraphRAGSaveRequest {
  query: string;
  answer: string;
  context?: string;
  nodes?: any[];
  relationships?: any[];
  fragments?: any[];
  project?: string;
}

/**
 * Guarda el reporte de GraphRAG en el backend.
 */
export async function saveGraphRAGReport(payload: GraphRAGSaveRequest): Promise<{ path: string; filename: string }> {
  return apiFetchJson("/api/graphrag/save_report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Link prediction suggestion */
export interface LinkSuggestion {
  source: string;
  target: string;
  score: number;
  algorithm: string;
  source_type?: string;
  target_type?: string;
}

/**
 * Execute a GraphRAG query with graph context.
 */
export async function graphragQuery(request: GraphRAGRequest): Promise<GraphRAGResponse> {
  return apiFetchJson<GraphRAGResponse>("/api/graphrag/query", {
    method: "POST",
    body: JSON.stringify({
      query: request.query,
      project: request.project || "default",
      include_fragments: request.include_fragments ?? true,
      chain_of_thought: request.chain_of_thought ?? false,
      node_ids: request.node_ids ?? null,
    }),
  });
}

export async function discoverSearch(request: DiscoverRequest): Promise<DiscoverResponse> {
  return apiFetchJson<DiscoverResponse>("/api/search/discover", {
    method: "POST",
    body: JSON.stringify({
      positive_texts: request.positive_texts,
      negative_texts: request.negative_texts || [],
      target_text: request.target_text || null,
      top_k: request.top_k || 10,
      project: request.project || "default",
    }),
  });
}

export interface DiscoverySaveMemoRequest {
  positive_texts: string[];
  negative_texts?: string[];
  target_text?: string;
  fragments: any[];
  project?: string;
  memo_title?: string;
  ai_synthesis?: string;  // Síntesis generada por IA
}

/**
 * Guarda los resultados de Discovery como memo Markdown.
 */
export async function saveDiscoveryMemo(payload: DiscoverySaveMemoRequest): Promise<{ path: string; filename: string }> {
  return apiFetchJson("/api/discovery/save_memo", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface ReportArtifact {
  kind: string;
  source: "fs" | "db";
  label: string;
  path?: string | null;
  created_at?: string | null;
  excerpt?: string | null;
}

export interface ProductArtifactGenerated {
  name: string;
  path: string;
  sha256: string;
  bytes: number;
}

export interface ProductArtifactsGenerateResponse {
  project: string;
  generated_at: string;
  changed_by?: string | null;
  artifacts: ProductArtifactGenerated[];
}

export interface ReportJobHistoryItem {
  task_id: string;
  job_type: string;
  status: string;
  project_id?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
  user_id?: string | null;
  result_path?: string | null;
  blob_url?: string | null;
}

export interface ListReportJobsResponse {
  project: string;
  jobs: ReportJobHistoryItem[];
  count: number;
  limit?: number;
  offset?: number;
  next_offset?: number;
  has_more?: boolean;
  filters?: { status?: string | null; job_type?: string | null; user_id?: string | null };
}

export async function listReportArtifacts(
  project: string,
  limit: number = 50
): Promise<{ project: string; artifacts: ReportArtifact[]; count: number }> {
  const params = new URLSearchParams({
    project,
    limit: String(limit),
  });
  return apiFetchJson(`/api/reports/artifacts?${params.toString()}`);
}

export async function generateProductArtifacts(project: string): Promise<ProductArtifactsGenerateResponse> {
  const params = new URLSearchParams({ project });
  return apiFetchJson(`/api/reports/product/generate?${params.toString()}`, {
    method: "POST",
  });
}

export async function listReportJobs(
  project: string,
  options?: {
    limit?: number;
    offset?: number;
    status?: string;
    job_type?: string;
    task_id?: string;
    task_id_prefix?: string;
    q?: string;
  }
): Promise<ListReportJobsResponse> {
  const params = new URLSearchParams({
    project,
    limit: String(options?.limit ?? 50),
    offset: String(options?.offset ?? 0),
  });
  if (options?.status) params.set("status", options.status);
  if (options?.job_type) params.set("job_type", options.job_type);
  if (options?.task_id) params.set("task_id", options.task_id);
  if (options?.task_id_prefix) params.set("task_id_prefix", options.task_id_prefix);
  if (options?.q) params.set("q", options.q);
  return apiFetchJson(`/api/reports/jobs?${params.toString()}`);
}

export async function downloadReportArtifact(project: string, path: string): Promise<Blob> {
  const normalized = (path || "").replace(/\\/g, "/").replace(/^\/+/, "");

  // Notes are downloaded via the dedicated safe endpoint.
  // Expected patterns:
  // - notes/<project>/...  (Discovery memos)
  // - notes/<project>/runner_semantic/... (runner memos)
  if (normalized.startsWith("notes/")) {
    const parts = normalized.split("/");
    const notesProject = parts.length >= 2 ? parts[1] : project;
    const rel = normalized.replace(new RegExp(`^notes/${notesProject}/`), "");
    const noteParams = new URLSearchParams({ rel });
    const response = await apiFetch(`/api/notes/${encodeURIComponent(notesProject)}/download?${noteParams.toString()}`);
    if (!response.ok) {
      throw new Error(`Error descargando memo (${response.status})`);
    }
    return response.blob();
  }

  const params = new URLSearchParams({ project, path: normalized });
  const response = await apiFetch(`/api/reports/artifacts/download?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Error descargando artefacto (${response.status})`);
  }
  return response.blob();
}

export async function downloadFromBlobUrl(blobUrl: string): Promise<Blob> {
  // Proxy via backend so private containers work and we avoid browser CORS.
  const params = new URLSearchParams({ url: blobUrl });
  const response = await apiFetch(`/api/reports/blob/download?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Error descargando blob_url (${response.status})`);
  }
  return response.blob();
}

// -----------------------------------------------------------------------------
// Doctoral report jobs (async)
// -----------------------------------------------------------------------------

export interface DoctoralReportJobStartResponse {
  task_id: string;
  status: string;
}

export interface DoctoralReportJobStatusResponse {
  task_id: string;
  status: "pending" | "running" | "completed" | "error" | string;
  project: string;
  stage: string;
  message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  errors?: string[] | null;
}

export interface DoctoralReportJobResultResponse {
  task_id: string;
  status: "completed" | string;
  result: {
    content?: string;
    stage?: string;
    project?: string;
    path?: string;
    filename?: string;
    report_id?: number | string;
    [k: string]: any;
  };
}

export async function startDoctoralReportJob(payload: {
  stage: "stage3" | "stage4";
  project: string;
}): Promise<DoctoralReportJobStartResponse> {
  return apiFetchJson<DoctoralReportJobStartResponse>("/api/reports/doctoral/execute", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getDoctoralReportJobStatus(taskId: string): Promise<DoctoralReportJobStatusResponse> {
  return apiFetchJson<DoctoralReportJobStatusResponse>(`/api/reports/doctoral/status/${encodeURIComponent(taskId)}`);
}

export async function getDoctoralReportJobResult(taskId: string): Promise<DoctoralReportJobResultResponse> {
  return apiFetchJson<DoctoralReportJobResultResponse>(`/api/reports/doctoral/result/${encodeURIComponent(taskId)}`);
}

/**
 * Predict missing links in the axial graph.
 */
export async function predictLinks(
  algorithm: string = "common_neighbors",
  topK: number = 10,
  project: string = "default",
  categoria?: string
): Promise<{ suggestions: LinkSuggestion[]; algorithm: string }> {
  const params = new URLSearchParams({
    algorithm,
    top_k: String(topK),
    project,
  });
  if (categoria) {
    params.append("categoria", categoria);
  }
  return apiFetchJson(`/api/axial/predict?${params.toString()}`);
}

/**
 * Get community-based link suggestions.
 */
export async function getCommunityLinks(
  project: string = "default"
): Promise<{ suggestions: LinkSuggestion[]; method: string }> {
  return apiFetchJson(`/api/axial/community-links?project=${encodeURIComponent(project)}`);
}

/** AI Analysis response for link predictions */
export interface AnalyzePredictionsResponse {
  analysis: string | null;
  structured?: boolean;
  memo_statements?: EpistemicStatement[];
  algorithm: string;
  algorithm_description: string;
  suggestions_analyzed: number;
}

export interface AnalyzeHiddenRelationshipsResponse {
  analysis: string | null;
  structured?: boolean;
  memo_statements?: EpistemicStatement[];
  suggestions_analyzed: number;
}

export interface HiddenRelationshipsMetricsResponse {
  project: string;
  metrics: {
    codes: number;
    total_evidence_ids: number;
    unique_evidence_ids: number;
    coverage_unique_ids_ratio: number;
    avg_ids_per_code: number;
    unique_triples: number;
    max_triple_repeat: number;
    repeated_triples: Array<{ fragmentos: string[]; count: number }>;
    avg_pairwise_jaccard: number;
    max_pairwise_jaccard: number;

    // Added for UI clarity: evidence coverage across suggestions
    suggestions_total?: number;
    suggestions_with_direct_evidence?: number;
    direct_evidence_ratio?: number;
    suggestions_with_any_evidence?: number;
    any_evidence_ratio?: number;
  };
}

/**
 * Analyze link predictions with AI.
 */
export async function analyzePredictions(
  algorithm: string,
  suggestions: LinkSuggestion[],
  project: string = "default"
): Promise<AnalyzePredictionsResponse> {
  return apiFetchJson<AnalyzePredictionsResponse>("/api/axial/analyze-predictions", {
    method: "POST",
    body: JSON.stringify({
      project,
      algorithm,
      suggestions: suggestions.map(s => ({
        source: s.source,
        target: s.target,
        score: s.score,
      })),
    }),
  });
}

/**
 * Analyze hidden relationships with AI.
 */
export async function analyzeHiddenRelationships(
  suggestions: Array<{ source: string; target: string; score: number; reason?: string; evidence_ids?: string[] }>,
  project: string = "default"
): Promise<AnalyzeHiddenRelationshipsResponse> {
  return apiFetchJson<AnalyzeHiddenRelationshipsResponse>("/api/axial/analyze-hidden-relationships", {
    method: "POST",
    body: JSON.stringify({
      project,
      suggestions: suggestions.map((s) => ({
        source: s.source,
        target: s.target,
        score: s.score,
        reason: s.reason,
        evidence_ids: s.evidence_ids || [],
      })),
    }),
  });
}

/**
 * Compute evidence diversity/overlap metrics for hidden relationships.
 */
export async function getHiddenRelationshipsMetrics(
  suggestions: Array<{ source: string; target: string; evidence_ids?: string[] }>,
  project: string = "default"
): Promise<HiddenRelationshipsMetricsResponse> {
  return apiFetchJson<HiddenRelationshipsMetricsResponse>("/api/axial/hidden-relationships/metrics", {
    method: "POST",
    body: JSON.stringify({
      project,
      suggestions: suggestions.map((s) => ({
        source: s.source,
        target: s.target,
        evidence_ids: s.evidence_ids || [],
      })),
    }),
  });
}

/** Response for saving link predictions */
export interface SaveLinkPredictionsResponse {
  success: boolean;
  saved_count: number;
}

/**
 * Save link prediction suggestions to the Candidates Tray for validation.
 */
export async function saveLinkPredictions(
  project: string,
  suggestions: Array<{
    source: string;
    target: string;
    score: number;
    algorithm: string;
    reason?: string;
  }>
): Promise<SaveLinkPredictionsResponse> {
  return apiFetchJson<SaveLinkPredictionsResponse>("/api/link-prediction/save", {
    method: "POST",
    body: JSON.stringify({
      project,
      suggestions,
    }),
  });
}

/** Response for saving analysis reports */
export interface SaveAnalysisReportResponse {
  success: boolean;
  report_id: number;
}

/**
 * Save an AI analysis report to the database.
 */
export async function saveAnalysisReport(
  project: string,
  reportType: string,
  title: string,
  content: string,
  metadata: Record<string, any> = {}
): Promise<SaveAnalysisReportResponse> {
  return apiFetchJson<SaveAnalysisReportResponse>("/api/analysis/save-report", {
    method: "POST",
    body: JSON.stringify({
      project,
      report_type: reportType,
      title,
      content,
      metadata,
    }),
  });
}

/** AI Analysis response for Discovery */
export interface EpistemicStatement {
  type: "OBSERVATION" | "INTERPRETATION" | "HYPOTHESIS" | "NORMATIVE_INFERENCE" | string;
  text: string;
  evidence_ids?: number[] | null;
  id?: string;
  evidence?: {
    node_ids?: Array<string | number>;
    relationship_ids?: Array<string | number>;
  };
}

// =============================================================================
// Neo4j Explorer: AI analysis of visible subgraph
// =============================================================================

export interface Neo4jAnalyzeViewRequest {
  project: string;
  node_ids: Array<string | number>;
  relationship_ids?: Array<string | number>;
  max_nodes?: number;
  max_relationships?: number;
}

export interface Neo4jAnalyzeViewResponse {
  analysis: string;
  structured: boolean;
  memo_statements: EpistemicStatement[];
  limits: {
    max_nodes: number;
    max_relationships: number;
    nodes_analyzed: number;
    relationships_analyzed: number;
  };
}

export async function analyzeNeo4jView(payload: Neo4jAnalyzeViewRequest): Promise<Neo4jAnalyzeViewResponse> {
  return apiFetchJson<Neo4jAnalyzeViewResponse>("/api/neo4j/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface AnalyzeDiscoveryResponse {
  analysis: string | null;
  positive_texts: string[];
  negative_texts: string[];
  target_text: string | null;
  fragments_analyzed: number;
  // Sprint 22: Structured response fields
  structured?: boolean;
  memo_statements?: EpistemicStatement[];
  codigos_sugeridos?: string[];
  refinamiento_busqueda?: {
    positivos: string[];
    negativos: string[];
    target: string;
  } | null;
}

/**
 * Analyze Discovery results with AI.
 */
export async function analyzeDiscovery(
  positive_texts: string[],
  negative_texts: string[],
  target_text: string | null,
  fragments: any[],
  project: string = "default"
): Promise<AnalyzeDiscoveryResponse> {
  return apiFetchJson<AnalyzeDiscoveryResponse>("/api/discovery/analyze", {
    method: "POST",
    body: JSON.stringify({
      project,
      positive_texts,
      negative_texts,
      target_text,
      fragments,
    }),
  });
}

// =============================================================================
// Códigos Candidatos - Sistema de Consolidación
// =============================================================================

/** Código candidato */
export interface CandidateCode {
  id: number;
  project_id: string;
  codigo: string;
  cita?: string;
  fragmento_id?: string;
  archivo?: string;
  fuente_origen: string;
  fuente_detalle?: string;
  score_confianza?: number;
  estado: "pendiente" | "hipotesis" | "validado" | "rechazado" | "fusionado";
  validado_por?: string;
  validado_en?: string;
  fusionado_a?: string;
  memo?: string;
  promovido_por?: string;
  promovido_en?: string;
  created_at?: string;
}

/** Request para crear código candidato */
export interface CreateCandidateRequest {
  project: string;
  codigo: string;
  cita?: string;
  fragmento_id?: string;
  archivo?: string;
  fuente_origen: "llm" | "manual" | "discovery" | "semantic_suggestion" | "discovery_ai" | "link_prediction";
  fuente_detalle?: string;
  score_confianza?: number;
  memo?: string;
}

/** Estadísticas de candidatos por origen */
export interface CandidateStats {
  by_source: Record<string, Record<string, number>>;
  by_source_unique?: Record<string, Record<string, number>>;
  totals: Record<string, number>;
  total_candidatos: number;
  unique_totals?: Record<string, number>;
  unique_total_codigos?: number;
  validated_promoted_total?: number;
  validated_unpromoted_total?: number;
  validated_promoted_unique?: number;
  validated_unpromoted_unique?: number;
}

/** Historial de versiones de un código (codigo_versiones) */
export interface CodeHistoryEntry {
  id: number;
  version: number;
  memo_anterior: string | null;
  memo_nuevo: string | null;
  accion: string;
  changed_by: string | null;
  created_at: string | null;
}

/** Obtiene el historial de versiones de un código */
export async function getCodeHistory(
  project: string,
  codigo: string,
  limit: number = 20
): Promise<{ codigo: string; history: CodeHistoryEntry[]; total: number }> {
  if (!project || !project.trim()) {
    throw new Error("Missing required 'project' for getCodeHistory");
  }
  if (!codigo || !codigo.trim()) {
    throw new Error("Missing required 'codigo' for getCodeHistory");
  }

  const params = new URLSearchParams({
    project: project.trim(),
    limit: String(limit),
  });

  return apiFetchJson(`/api/coding/codes/${encodeURIComponent(codigo)}\/history?${params.toString()}`);
}

/**
 * Crea un nuevo código candidato.
 */
export async function submitCandidate(request: CreateCandidateRequest): Promise<{ success: boolean; inserted: number }> {
  return apiFetchJson("/api/codes/candidates", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

/**
 * Lista códigos candidatos con filtros.
 */
export async function listCandidates(
  project: string,
  options?: {
    estado?: string;
    fuente_origen?: string;
    archivo?: string;
    promovido?: boolean;
    limit?: number;
    offset?: number;
    sort_order?: "asc" | "desc";
  }
): Promise<{ candidates: CandidateCode[]; count: number }> {
  if (!project || !project.trim()) {
    throw new Error("Missing required 'project' for listCandidates");
  }
  const params = new URLSearchParams({ project: project.trim() });
  if (options?.estado) params.append("estado", options.estado);
  if (options?.fuente_origen) params.append("fuente_origen", options.fuente_origen);
  if (options?.archivo) params.append("archivo", options.archivo);
  if (typeof options?.promovido === "boolean") params.append("promovido", String(options.promovido));
  if (options?.limit) {
    // Backend enforces `limit <= 500` (FastAPI Query validation). Clamp client-side to avoid 422.
    const safeLimit = Math.max(1, Math.min(500, Number(options.limit)));
    params.append("limit", String(safeLimit));
  }
  if (options?.offset) params.append("offset", String(options.offset));
  if (options?.sort_order) params.append("sort_order", options.sort_order);

  return apiFetchJson(`/api/codes/candidates?${params.toString()}`);
}

/**
 * Valida un código candidato.
 */
export async function validateCandidate(
  candidateId: number,
  project: string,
  memo?: string
): Promise<{ success: boolean; candidate_id: number; estado: string }> {
  return apiFetchJson(`/api/codes/candidates/${candidateId}/validate`, {
    method: "PUT",
    body: JSON.stringify({ project, memo }),
  });
}

/**
 * Rechaza un código candidato.
 */
export async function rejectCandidate(
  candidateId: number,
  project: string,
  memo?: string
): Promise<{ success: boolean; candidate_id: number; estado: string }> {
  return apiFetchJson(`/api/codes/candidates/${candidateId}/reject`, {
    method: "PUT",
    body: JSON.stringify({ project, memo }),
  });
}

/**
 * Fusiona múltiples códigos candidatos en uno.
 */
export async function mergeCandidates(
  project: string,
  sourceIds: number[],
  targetCodigo: string,
  options?: { memo?: string; dry_run?: boolean; idempotency_key?: string | null }
): Promise<{ success: boolean; merged_count: number; target_codigo: string; dry_run?: boolean }> {
  const idempotencyKey =
    options?.idempotency_key ?? `ui-merge-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return apiFetchJson("/api/codes/candidates/merge", {
    method: "POST",
    body: JSON.stringify({
      project,
      source_ids: sourceIds,
      target_codigo: targetCodigo,
      memo: options?.memo,
      dry_run: Boolean(options?.dry_run),
      idempotency_key: idempotencyKey,
    }),
  });
}

/** Pair for auto-merge operation */
export interface AutoMergePair {
  source_codigo: string;
  target_codigo: string;
}

/** Response for auto-merge operation */
export interface AutoMergeResponse {
  success: boolean;
  total_merged: number;
  pairs_processed: number;
  dry_run?: boolean;
  details: Array<{
    source: string;
    target: string;
    merged_count: number;
    skipped?: string;
    dry_run?: boolean;
    details?: unknown;
  }>;
}

/**
 * Fusiona masivamente pares de códigos duplicados por nombre.
 * Más robusto que merge por IDs porque busca directamente por nombre de código.
 */
export async function autoMergeCandidates(
  project: string,
  pairs: AutoMergePair[],
  options?: { memo?: string; dry_run?: boolean; idempotency_key?: string | null }
): Promise<AutoMergeResponse> {
  const idempotencyKey =
    options?.idempotency_key ?? `ui-auto-merge-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return apiFetchJson<AutoMergeResponse>("/api/codes/candidates/auto-merge", {
    method: "POST",
    body: JSON.stringify({
      project,
      pairs,
      memo: options?.memo,
      dry_run: Boolean(options?.dry_run),
      idempotency_key: idempotencyKey,
    }),
  });
}

export interface RevertValidatedCandidatesResponse {
  success: boolean;
  project: string;
  dry_run: boolean;
  reverted_count?: number;
  would_revert?: number;
}

/**
 * Revierte todos los candidatos con estado 'validado' a 'pendiente' (por proyecto).
 * Nota: no afecta códigos ya promovidos a tablas definitivas.
 */
export async function revertValidatedCandidates(
  project: string,
  options?: { memo?: string; dry_run?: boolean }
): Promise<RevertValidatedCandidatesResponse> {
  if (!project || !project.trim()) {
    throw new Error("Missing required 'project' for revertValidatedCandidates");
  }
  return apiFetchJson<RevertValidatedCandidatesResponse>("/api/codes/candidates/revert-validated", {
    method: "POST",
    body: JSON.stringify({
      project: project.trim(),
      memo: options?.memo,
      dry_run: Boolean(options?.dry_run),
    }),
  });
}

/** Duplicate pair detected by Post-Hoc analysis */
export interface DuplicatePair {
  code1: string;
  code2: string;
  distance: number;
  similarity: number;
}

/** Response for duplicate detection */
export interface DetectDuplicatesResponse {
  success: boolean;
  project: string;
  threshold: number;
  duplicates: DuplicatePair[];
  count: number;
}

/**
 * Detecta códigos duplicados usando similitud de Levenshtein (Post-Hoc).
 */
export async function detectDuplicates(
  project: string,
  threshold: number = 0.80
): Promise<DetectDuplicatesResponse> {
  return apiFetchJson<DetectDuplicatesResponse>("/api/codes/detect-duplicates", {
    method: "POST",
    body: JSON.stringify({ project, threshold }),
  });
}

/** Hit from grouped search */
export interface GroupedHit {
  id: string;
  score: number;
  fragmento: string;
  archivo: string | null;
  speaker: string | null;
  actor_principal: string | null;
}

/** Group from grouped search */
export interface SearchGroup {
  group_key: string;
  hits: GroupedHit[];
}

/** Response for grouped search */
export interface GroupedSearchResponse {
  success: boolean;
  query: string;
  group_by: string;
  results: SearchGroup[];
  total_groups: number;
}

/**
 * Búsqueda semántica agrupada para evitar sesgo de fuente.
 * Garantiza diversidad: máximo N fragmentos por entrevista/speaker.
 * Soporta filtros demográficos para Comparación Constante.
 */
export async function searchGrouped(
  project: string,
  query: string,
  options: {
    limit?: number;
    group_by?: "archivo" | "speaker" | "actor_principal";
    group_size?: number;
    score_threshold?: number;
    // Filtros avanzados
    genero?: string | null;
    actor_principal?: string | null;
    area_tematica?: string | null;
    periodo?: string | null;
    archivo?: string | null;
  } = {}
): Promise<GroupedSearchResponse> {
  return apiFetchJson<GroupedSearchResponse>("/api/qdrant/search-grouped", {
    method: "POST",
    body: JSON.stringify({
      project,
      query,
      limit: options.limit || 10,
      group_by: options.group_by || "archivo",
      group_size: options.group_size || 2,
      score_threshold: options.score_threshold || 0.3,
      genero: options.genero,
      actor_principal: options.actor_principal,
      area_tematica: options.area_tematica,
      periodo: options.periodo,
      archivo: options.archivo,
    }),
  });
}

/**
 * Promueve códigos candidatos validados a la lista definitiva.
 */
export async function promoteCandidates(
  project: string,
  options?: { candidateIds?: number[]; promoteAllValidated?: boolean }
): Promise<{
  success: boolean;
  promoted_count: number;
  validated_total?: number;
  eligible_total?: number;
  skipped_total?: number;
  mode?: string;
}> {
  return apiFetchJson("/api/codes/candidates/promote", {
    method: "POST",
    body: JSON.stringify({
      project,
      candidate_ids: options?.candidateIds ?? [],
      promote_all_validated: Boolean(options?.promoteAllValidated),
    }),
  });
}

/**
 * Obtiene estadísticas de candidatos por origen.
 */
export async function getCandidateStatsBySource(project: string): Promise<CandidateStats> {
  return apiFetchJson(`/api/codes/stats/sources?project=${encodeURIComponent(project)}`);
}

/** Ejemplo canónico de un código */
export interface CanonicalExample {
  cita: string;
  fragmento_id: string;
  archivo: string;
  fuente?: string;
  memo?: string;
  created_at?: string;
}

/**
 * Obtiene ejemplos canónicos (citas previas validadas) de un código candidato.
 */
export async function getCanonicalExamples(
  candidateId: number,
  project: string,
  limit: number = 3
): Promise<{
  candidate_id: number;
  codigo: string;
  examples: CanonicalExample[];
  examples_count: number;
}> {
  const params = new URLSearchParams({
    project,
    limit: String(limit),
  });
  return apiFetchJson(`/api/codes/candidates/${candidateId}/examples?${params.toString()}`);
}

/** Salud del backlog de candidatos */
export interface BacklogHealth {
  is_healthy: boolean;
  pending_count: number;
  oldest_pending_days: number;
  avg_pending_age_hours: number;
  avg_resolution_hours?: number;
  alerts: string[];
  thresholds: {
    max_days: number;
    max_count: number;
  };
}

/**
 * Obtiene métricas de salud del backlog de candidatos.
 */
export async function getBacklogHealth(
  project: string,
  thresholdDays: number = 3,
  thresholdCount: number = 50
): Promise<BacklogHealth> {
  const params = new URLSearchParams({
    project,
    threshold_days: String(thresholdDays),
    threshold_count: String(thresholdCount),
  });
  return apiFetchJson(`/api/codes/candidates/health?${params.toString()}`);
}

/** Código similar (sinónimo potencial) */
export interface SimilarCode {
  codigo: string;
  score: number;
  occurrences: number;
}

/**
 * Obtiene códigos semánticamente similares para sugerir sinónimos o fusiones.
 */
export async function getSimilarCodes(
  codigo: string,
  project: string,
  topK: number = 5
): Promise<{
  codigo: string;
  similar_codes: SimilarCode[];
  count: number;
}> {
  const params = new URLSearchParams({
    codigo,
    project,
    top_k: String(topK),
  });
  return apiFetchJson(`/api/codes/similar?${params.toString()}`);
}

// =============================================================================
// Sprint 23: Pre-Hoc Deduplication
// =============================================================================

/** Result for a single code in batch check */
export interface BatchCheckResult {
  codigo: string;
  has_similar: boolean;
  similar: Array<{ existing: string; similarity: number }>;
  /** True si el mismo batch trae duplicados (por normalización) */
  duplicate_in_batch?: boolean;
  /** Tamaño del grupo normalizado dentro del batch */
  batch_group_size?: number;
}

/** Response for batch check */
export interface CheckBatchCodesResponse {
  project: string;
  threshold: number;
  results: BatchCheckResult[];
  has_any_similar: boolean;
  checked_count: number;
  existing_count: number;
  /** Métricas opcionales para prevenir "batch blindness" */
  batch_unique_count?: number;
  batch_duplicate_groups?: number;
  batch_duplicates_total?: number;
}

// =============================================================================
// Runner IA (solo propuestas): planes de merge auditables por run_id
// =============================================================================

export type AiPlanMergePair = {
  source_codigo: string;
  target_codigo: string;
  similarity: number;
  reason?: string;
};

export type AiPlanMergesResponse = {
  project: string;
  run_id: string;
  threshold: number;
  input_count: number;
  pairs_count: number;
  pairs: AiPlanMergePair[];
};

export type AiMergePlanRecord = {
  run_id: string;
  project_id: string;
  created_at: string;
  created_by?: string | null;
  source?: string | null;
  threshold?: number | null;
  input_codigos?: string[];
  pairs?: AiPlanMergePair[];
  meta?: Record<string, unknown>;
};

export async function aiPlanMerges(
  project: string,
  codigos: string[],
  threshold: number,
  limit: number = 200,
  source: string = "ui",
): Promise<AiPlanMergesResponse> {
  return apiFetchJson<AiPlanMergesResponse>("/api/codes/candidates/ai/plan-merges", {
    method: "POST",
    body: JSON.stringify({ project, codigos, threshold, limit, source }),
  }, undefined, 60000);
}

export async function getAiMergePlan(project: string, runId: string): Promise<AiMergePlanRecord> {
  const qs = new URLSearchParams({ project });
  return apiFetchJson<AiMergePlanRecord>(
    `/api/codes/candidates/ai/plan-merges/${encodeURIComponent(runId)}?${qs.toString()}`,
  );
}

export async function listAiMergePlans(
  project: string,
  limit: number = 20,
): Promise<{ project: string; plans: AiMergePlanRecord[]; count: number }> {
  const qs = new URLSearchParams({ project, limit: String(limit) });
  return apiFetchJson<{ project: string; plans: AiMergePlanRecord[]; count: number }>(
    `/api/codes/candidates/ai/plan-merges?${qs.toString()}`,
  );
}

/**
 * Sprint 23: Pre-hoc check for batch of codes before insert.
 * Returns which codes have similar existing codes for deduplication UI.
 */
export async function checkBatchCodes(
  project: string,
  codigos: string[],
  threshold: number = 0.85
): Promise<CheckBatchCodesResponse> {
  return apiFetchJson<CheckBatchCodesResponse>("/api/codes/check-batch", {
    method: "POST",
    body: JSON.stringify({ project, codigos, threshold }),
  });
}

// =============================================================================
// Sprint 24: Discovery Navigation Log
// =============================================================================

export interface LogNavigationRequest {
  project: string;
  positivos: string[];
  negativos: string[];
  target_text: string | null;
  fragments_count: number;
  codigos_sugeridos?: string[];
  refinamientos_aplicados?: Record<string, any>;
  ai_synthesis?: string;
  action_taken: "search" | "refine" | "send_codes";
  busqueda_origen_id?: string;
}

export interface NavigationHistoryEntry {
  id: number;
  busqueda_id: string;
  busqueda_origen_id: string | null;
  positivos: string[];
  negativos: string[];
  target_text: string | null;
  fragments_count: number;
  codigos_sugeridos: string[];
  refinamientos_aplicados: Record<string, any> | null;
  ai_synthesis: string | null;
  action_taken: string;
  created_at: string;
}

/**
 * Sprint 24: Log a discovery navigation step for traceability.
 */
export async function logDiscoveryNavigation(
  request: LogNavigationRequest
): Promise<{ success: boolean; busqueda_id: string; action_taken: string }> {
  return apiFetchJson("/api/discovery/log-navigation", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

/**
 * Sprint 24: Get discovery navigation history for a project.
 */
export async function getDiscoveryNavigationHistory(
  project: string,
  limit: number = 50
): Promise<{ project: string; history: NavigationHistoryEntry[]; count: number }> {
  return apiFetchJson(
    `/api/discovery/navigation-history?project=${encodeURIComponent(project)}&limit=${limit}`
  );
}

// =============================================================================
// Configuración de Proyecto
// =============================================================================

/** Configuración de un proyecto */
export interface ProjectConfig {
  discovery_threshold: number;
  analysis_temperature: number;
  analysis_max_tokens: number;
}

/** Response de configuración de proyecto */
export interface ProjectConfigResponse {
  project_id: string;
  config: ProjectConfig;
}

/**
 * Obtiene la configuración de un proyecto.
 */
export async function getProjectConfig(
  projectId: string
): Promise<ProjectConfigResponse> {
  return apiFetchJson(`/api/projects/${encodeURIComponent(projectId)}/config`);
}

/**
 * Actualiza la configuración de un proyecto.
 * Solo actualiza los campos proporcionados.
 */
export async function updateProjectConfig(
  projectId: string,
  updates: Partial<ProjectConfig>
): Promise<ProjectConfigResponse & { updated: string[] }> {
  return apiFetchJson(`/api/projects/${encodeURIComponent(projectId)}/config`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

