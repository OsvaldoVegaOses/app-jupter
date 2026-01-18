/**
 * @fileoverview Definiciones de tipos TypeScript para el dashboard.
 * 
 * Este archivo contiene todas las interfaces que definen la estructura
 * de datos intercambiados entre el frontend y el backend.
 * 
 * Categorías de interfaces:
 * - Proyecto y Estado: ProjectEntry, StatusSnapshot, StageEntry
 * - Ingesta: IngestResult
 * - Codificación: CodingAssignPayload, CodingSuggestion, CodingStats
 * - Neo4j: Neo4jTable, Neo4jGraph, Neo4jGraphNode, Neo4jGraphRelationship
 * 
 * @module types
 */

export interface LogHint {
  path?: string;
  modified_at?: string;
  size?: number;
  [key: string]: unknown;
}

export interface StageEntry {
  label?: string;
  completed?: boolean;
  last_run_id?: string;
  updated_at?: string;
  command?: string;
  subcommand?: string;
  verify?: string;
  notes?: string;
  log_hint?: LogHint | string;
  artifacts?: unknown;
  [key: string]: unknown;
}

export interface StatusSnapshot {
  project?: string;
  stages: Record<string, StageEntry>;
  manifest?: Record<string, any> | null;
  state_path?: string;
  updated?: boolean;
}

export interface ProjectEntry {
  id: string;
  name?: string;
  description?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface IngestResult {
  project: string;
  args?: string[];
  stdout?: string;
  stderr?: string;
  exit_code?: number;
  files?: string[];
  result?: Record<string, unknown>;
}

export interface CodingAssignPayload {
  fragmento_id: string;
  archivo?: string;
  codigo: string;
  cita: string;
  fuente?: string | null;
  memo?: string | null;
  [key: string]: unknown;
}

export interface CodingSuggestion {
  fragmento_id: string;
  score: number;
  archivo?: string | null;
  par_idx?: number | null;
  fragmento?: string | null;
  area_tematica?: string | null;
  actor_principal?: string | null;
  requiere_protocolo_lluvia?: boolean | null;
  [key: string]: unknown;
}

export interface CodingSuggestResponse {
  suggestions: CodingSuggestion[];
  [key: string]: unknown;
}

export interface CodingStats {
  total_citas?: number;
  codigos_unicos?: number;
  fragmentos_totales?: number;
  fragmentos_codificados?: number;
  fragmentos_sin_codigo?: number;
  porcentaje_cobertura?: number;
  relaciones_axiales?: number;
  [key: string]: number | string | undefined;
}

export interface CodingCitation {
  fragmento_id: string;
  archivo: string;
  fuente?: string | null;
  cita: string;
  memo?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface CodingCitationsResponse {
  citations: CodingCitation[];
  [key: string]: unknown;
}

export interface CodingNextFragment {
  fragmento_id: string;
  archivo: string;
  par_idx: number;
  fragmento: string;
  area_tematica?: string | null;
  actor_principal?: string | null;
  requiere_protocolo_lluvia?: boolean | null;
  [key: string]: unknown;
}

export interface CodingNextSuggestedCode {
  codigo: string;
  citas?: number;
  source?: string;
  [key: string]: unknown;
}

export interface CodingNextResponse {
  project: string;
  found: boolean;
  pending_total?: number;
  pending_in_archivo?: number | null;
  fragmento?: CodingNextFragment | null;
  suggested_codes?: CodingNextSuggestedCode[];
  reasons?: string[];
  [key: string]: unknown;
}

export interface FragmentSample {
  fragmento_id: string;
  archivo: string;
  par_idx: number;
  char_len: number;
  fragmento?: string | null;
  [key: string]: unknown;
}

export interface FragmentSampleResponse {
  samples: FragmentSample[];
  [key: string]: unknown;
}

export interface FragmentListResponse {
  fragments: FragmentSample[];
  [key: string]: unknown;
}

export interface InterviewSummary {
  archivo: string;
  fragmentos: number;
  actor_principal?: string | null;
  area_tematica?: string | null;
  actualizado?: string | null;
  [key: string]: unknown;
}

export interface InterviewSummaryResponse {
  interviews: InterviewSummary[];
  [key: string]: unknown;
}

export interface CodeSummary {
  codigo: string;
  citas: number;
  fragmentos: number;
  primera_cita?: string | null;
  ultima_cita?: string | null;
  [key: string]: unknown;
}

export interface CodeSummaryResponse {
  codes: CodeSummary[];
  [key: string]: unknown;
}

export interface Neo4jTable {
  columns: string[];
  rows: unknown[][];
}

export interface Neo4jGraphNode {
  id: unknown;
  labels?: string[];
  properties?: Record<string, unknown>;
}

export interface Neo4jGraphRelationship {
  id: unknown;
  type?: string;
  start?: unknown;
  end?: unknown;
  properties?: Record<string, unknown>;
}

export interface Neo4jGraph {
  nodes: Neo4jGraphNode[];
  relationships: Neo4jGraphRelationship[];
}
