/**
 * @fileoverview Panel de Informes de Análisis por Entrevista.
 * 
 * Este componente muestra:
 * - Lista de informes por entrevista con métricas de codificación
 * - Matriz comparativa de códigos entre entrevistas
 * - Indicador de saturación teórica
 * - Resumen de Etapa 4 para transición a Etapa 5
 * 
 * @module components/ReportsPanel
 */

import React, { useState, useEffect, useCallback } from "react";
import {
  apiFetchJson,
  apiFetch,
  listReportArtifacts,
  generateProductArtifacts,
  listReportJobs,
  downloadReportArtifact,
  downloadFromBlobUrl,
  startDoctoralReportJob,
  getDoctoralReportJobStatus,
  getDoctoralReportJobResult,
  type ReportArtifact,
  type ReportJobHistoryItem,
  type EpistemicStatement,
} from "../services/api";

function memoBadgeStyle(type: string): React.CSSProperties {
  const t = (type || "").toUpperCase();
  if (t === "OBSERVATION") return { background: "#dcfce7", color: "#166534", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
  if (t === "INTERPRETATION") return { background: "#dbeafe", color: "#1e40af", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
  if (t === "HYPOTHESIS") return { background: "#fde68a", color: "#92400e", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
  if (t === "NORMATIVE_INFERENCE") return { background: "#fbcfe8", color: "#9d174d", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
  return { background: "#e5e7eb", color: "#374151", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
}

interface InterviewReport {
  archivo: string;
  project_id: string;
  fecha_analisis: string;
  codigos_generados: string[];
  codigos_nuevos: number;
  codigos_reutilizados: number;
  fragmentos_analizados: number;
  fragmentos_codificados: number;
  tasa_cobertura: number;
  categorias_generadas: string[];
  categorias_nuevas: number;
  relaciones_creadas: number;
  relaciones_por_tipo: Record<string, number>;
  aporte_novedad: number;
  contribucion_saturacion: string;
  llm_model?: string;
}

interface Stage4Summary {
  project_id: string;
  fecha_generacion: string;
  total_entrevistas: number;
  total_codigos_unicos: number;
  total_categorias: number;
  total_relaciones: number;
  relaciones_por_tipo: Record<string, number>;
  score_saturacion: number;
  saturacion_alcanzada: boolean;
  candidatos_nucleo: any[];
  informes_entrevistas: any[];
}

interface ReportsPanelProps {
  project: string;
}

export function ReportsPanel({ project }: ReportsPanelProps) {
  const [reports, setReports] = useState<InterviewReport[]>([]);
  const [summary, setSummary] = useState<Stage4Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"list" | "comparison" | "summary" | "jobs" | "artifacts">("list");
  const [selectedReport, setSelectedReport] = useState<InterviewReport | null>(null);

  // Artifacts (runner reports/memos, GraphRAG reports, etc.)
  const [artifacts, setArtifacts] = useState<ReportArtifact[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [productGenLoading, setProductGenLoading] = useState(false);
  const [productGenMessage, setProductGenMessage] = useState<string | null>(null);

  // Product insights preview (top_10_insights.json)
  type ProductInsightQuery = {
    action?: string;
    positivos?: string[];
    negativos?: string[];
    codes?: string[];
    target?: string | null;
    context?: string | null;
    min_fragments?: number | null;
    find_cooccurrence?: boolean | null;
    expand_semantic?: boolean | null;
    min_score?: number | null;
    [k: string]: any;
  };

  type ProductInsightItem = {
    id?: number | null;
    source_type?: string | null;
    source_id?: string | null;
    insight_type?: string;
    content?: string;
    suggested_query?: ProductInsightQuery | null;
    priority?: number;
    status?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
  };

  type TopInsightsArtifact = {
    schema_version?: number;
    project?: string;
    generated_at?: string;
    items?: ProductInsightItem[];
  };

  const [insightsPreviewOpen, setInsightsPreviewOpen] = useState(false);
  const [insightsPreviewLoading, setInsightsPreviewLoading] = useState(false);
  const [insightsPreviewError, setInsightsPreviewError] = useState<string | null>(null);
  const [insightsPreviewData, setInsightsPreviewData] = useState<TopInsightsArtifact | null>(null);
  const [insightsPreviewRaw, setInsightsPreviewRaw] = useState<string | null>(null);

  // Report jobs history
  const [jobs, setJobs] = useState<ReportJobHistoryItem[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsStatusFilter, setJobsStatusFilter] = useState<string>("");
  const [jobsTypeFilter, setJobsTypeFilter] = useState<string>("");
  const [jobsOffset, setJobsOffset] = useState<number>(0);
  const [jobsHasMore, setJobsHasMore] = useState<boolean>(false);

  // Search (applied vs draft)
  const [jobsTaskDraft, setJobsTaskDraft] = useState<string>("");
  const [jobsTextDraft, setJobsTextDraft] = useState<string>("");
  const [jobsTaskApplied, setJobsTaskApplied] = useState<string>("");
  const [jobsTextApplied, setJobsTextApplied] = useState<string>("");

  // Doctoral report state
  const [doctoralLoading, setDoctoralLoading] = useState(false);
  const [doctoralContent, setDoctoralContent] = useState<string | null>(null);
  const [doctoralMemoStatements, setDoctoralMemoStatements] = useState<EpistemicStatement[]>([]);
  const [showDoctoralTaggedMemo, setShowDoctoralTaggedMemo] = useState(true);
  const [doctoralMemoTypeFilters, setDoctoralMemoTypeFilters] = useState<Record<string, boolean>>({
    OBSERVATION: true,
    INTERPRETATION: true,
    HYPOTHESIS: true,
    NORMATIVE_INFERENCE: true,
  });
  const [doctoralStage, setDoctoralStage] = useState<"stage3" | "stage4">("stage3");
  const [doctoralTaskId, setDoctoralTaskId] = useState<string | null>(null);
  const [doctoralStatus, setDoctoralStatus] = useState<string>("idle");
  const [doctoralStatusMessage, setDoctoralStatusMessage] = useState<string | null>(null);

  // Stage4 final report (async job) state
  const [stage4FinalLoading, setStage4FinalLoading] = useState(false);
  const [stage4FinalTaskId, setStage4FinalTaskId] = useState<string | null>(null);
  const [stage4FinalStatus, setStage4FinalStatus] = useState<string>("idle");
  const [stage4FinalStatusMessage, setStage4FinalStatusMessage] = useState<string | null>(null);
  const [stage4FinalResult, setStage4FinalResult] = useState<any | null>(null);
  const [stage4FinalMemoStatements, setStage4FinalMemoStatements] = useState<EpistemicStatement[]>([]);
  const [showStage4FinalTaggedMemo, setShowStage4FinalTaggedMemo] = useState(true);
  const [stage4FinalMemoTypeFilters, setStage4FinalMemoTypeFilters] = useState<Record<string, boolean>>({
    OBSERVATION: true,
    INTERPRETATION: true,
    HYPOTHESIS: true,
    NORMATIVE_INFERENCE: true,
  });

  const loadReports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetchJson<{ reports: InterviewReport[] }>(
        `/api/reports/interviews?project=${encodeURIComponent(project)}`
      );
      setReports(data.reports || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar informes");
    } finally {
      setLoading(false);
    }
  }, [project]);

  const loadSummary = useCallback(async () => {
    try {
      const data = await apiFetchJson<Stage4Summary>(
        `/api/reports/stage4-summary?project=${encodeURIComponent(project)}`
      );
      setSummary(data);
    } catch (err) {
      console.error("Error loading summary", err);
    }
  }, [project]);

  const loadArtifacts = useCallback(async () => {
    setArtifactsLoading(true);
    try {
      const data = await listReportArtifacts(project, 80);
      setArtifacts(data.artifacts || []);
    } catch (err) {
      // Best-effort: do not block the whole panel if artifacts fail
      console.warn("Error loading artifacts", err);
    } finally {
      setArtifactsLoading(false);
    }
  }, [project]);

  const handleGenerateProductArtifacts = useCallback(async () => {
    setProductGenLoading(true);
    setProductGenMessage(null);
    try {
      const result = await generateProductArtifacts(project);
      setProductGenMessage(`Generado: ${result.artifacts?.length ?? 0} artefactos`);
      await loadArtifacts();
    } catch (err) {
      setProductGenMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setProductGenLoading(false);
    }
  }, [project, loadArtifacts]);

  const loadJobs = useCallback(
    async (opts?: { reset?: boolean; append?: boolean }) => {
      const reset = Boolean(opts?.reset);
      const append = Boolean(opts?.append);
      const nextOffset = reset ? 0 : (append ? jobsOffset : 0);

      setJobsLoading(true);
      try {
        const data = await listReportJobs(project, {
          limit: 50,
          offset: nextOffset,
          status: jobsStatusFilter || undefined,
          job_type: jobsTypeFilter || undefined,
          task_id: jobsTaskApplied.startsWith("=") ? jobsTaskApplied.slice(1).trim() || undefined : undefined,
          task_id_prefix: (!jobsTaskApplied.startsWith("=") && jobsTaskApplied.trim()) ? jobsTaskApplied.trim() : undefined,
          q: jobsTextApplied.trim() || undefined,
        });

        const newJobs = data.jobs || [];
        if (reset || !append) {
          setJobs(newJobs);
        } else {
          setJobs((prev) => [...prev, ...newJobs]);
        }

        const computedNextOffset = (data.next_offset ?? (nextOffset + newJobs.length)) as number;
        setJobsOffset(computedNextOffset);
        setJobsHasMore(Boolean(data.has_more ?? (newJobs.length === 50)));
      } catch (err) {
        // Best-effort: do not block the panel if jobs fail
        console.warn("Error loading jobs", err);
      } finally {
        setJobsLoading(false);
      }
    },
    [project, jobsOffset, jobsStatusFilter, jobsTypeFilter]
  );

  useEffect(() => {
    loadReports();
    loadSummary();
    loadArtifacts();
    loadJobs({ reset: true });
  }, [loadReports, loadSummary, loadArtifacts, loadJobs]);

  useEffect(() => {
    // Reset pagination when filters change
    setJobsOffset(0);
    loadJobs({ reset: true });
  }, [jobsStatusFilter, jobsTypeFilter]);

  const applyJobsSearch = () => {
    setJobsTaskApplied((jobsTaskDraft || "").trim());
    setJobsTextApplied((jobsTextDraft || "").trim());
    setJobsOffset(0);
    loadJobs({ reset: true });
  };

  const clearJobsSearch = () => {
    setJobsTaskDraft("");
    setJobsTextDraft("");
    setJobsTaskApplied("");
    setJobsTextApplied("");
    setJobsOffset(0);
    loadJobs({ reset: true });
  };

  const getSaturationColor = (level: string) => {
    switch (level) {
      case "alta": return "#ef4444";
      case "media": return "#f59e0b";
      case "baja": return "#22c55e";
      default: return "#64748b";
    }
  };

  const getSaturationLabel = (level: string) => {
    switch (level) {
      case "alta": return "🔴 Alta novedad";
      case "media": return "🟡 Novedad media";
      case "baja": return "🟢 Saturando";
      default: return level;
    }
  };

  const formatDate = (iso: string) => {
    return new Date(iso).toLocaleDateString("es-CL", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const exportToMarkdown = async () => {
    try {
      // Usamos apiFetch para manejar headers de autenticación automáticos
      const response = await apiFetch(`/api/reports/${encodeURIComponent(project)}/export`, {
        headers: {
          // Plain text response expected
        }
      });

      if (!response.ok) throw new Error("Error detallado al exportar informe");

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      // El nombre del archivo viene en el header Content-Disposition si quisiéramos parsearlo,
      // pero podemos generar uno aquí también o usar el del backend si lo extraemos.
      // Por simplicidad generamos uno aquí con timestamp.
      a.download = `Informe_Cientifico_${project}_${Date.now()}.md`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error exportando informe");
    }
  };

  const generateDoctoralReport = async () => {
    setDoctoralLoading(true);
    setError(null);
    setDoctoralContent(null);
    setDoctoralMemoStatements([]);
    setDoctoralTaskId(null);
    setDoctoralStatus("starting");
    setDoctoralStatusMessage(null);

    const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

    try {
      const started = await startDoctoralReportJob({ stage: doctoralStage, project });
      setDoctoralTaskId(started.task_id);
      setDoctoralStatus("pending");

      // Poll status until completion/error (max ~6 minutes)
      for (let attempt = 0; attempt < 180; attempt++) {
        const status = await getDoctoralReportJobStatus(started.task_id);
        setDoctoralStatus(status.status);
        setDoctoralStatusMessage(status.message || null);

        if (status.status === "completed") {
          const result = await getDoctoralReportJobResult(started.task_id);
          setDoctoralContent(result.result?.content || null);
          setDoctoralMemoStatements(Array.isArray((result as any).result?.memo_statements) ? (((result as any).result.memo_statements) as EpistemicStatement[]) : []);
          setDoctoralStatus("completed");
          break;
        }

        if (status.status === "error") {
          const msg = (status.errors && status.errors.length > 0) ? status.errors.join("\n") : (status.message || "Error generando informe de avance");
          setError(msg);
          break;
        }

        await sleep(2000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error generando informe de avance");
    } finally {
      setDoctoralLoading(false);
    }
  };

  const generateStage4FinalReport = async () => {
    setStage4FinalLoading(true);
    setError(null);
    setStage4FinalResult(null);
    setStage4FinalMemoStatements([]);
    setStage4FinalTaskId(null);
    setStage4FinalStatus("starting");
    setStage4FinalStatusMessage(null);

    const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

    try {
      const started = await apiFetchJson<{ task_id: string; status: string }>(
        `/api/reports/stage4-final/execute?project=${encodeURIComponent(project)}`,
        { method: "POST" }
      );
      setStage4FinalTaskId(started.task_id);
      setStage4FinalStatus("pending");

      for (let attempt = 0; attempt < 180; attempt++) {
        const status = await apiFetchJson<any>(
          `/api/reports/stage4-final/status/${encodeURIComponent(started.task_id)}`
        );
        setStage4FinalStatus(status.status);
        setStage4FinalStatusMessage(status.message || null);

        if (status.status === "completed") {
          const result = await apiFetchJson<any>(
            `/api/reports/stage4-final/result/${encodeURIComponent(started.task_id)}`
          );
          setStage4FinalResult(result.result || null);

          const report = result.result?.report;
          const memos = Array.isArray(report?.memo_statements) ? (report.memo_statements as EpistemicStatement[]) : [];
          setStage4FinalMemoStatements(memos);
          setStage4FinalStatus("completed");
          break;
        }

        if (status.status === "error") {
          const msg = (status.errors && status.errors.length > 0) ? status.errors.join("\n") : (status.message || "Error generando Stage4-final");
          setError(msg);
          break;
        }

        await sleep(2000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error generando Stage4-final");
    } finally {
      setStage4FinalLoading(false);
    }
  };

  const downloadDoctoralReport = () => {
    if (!doctoralContent) return;
    const blob = new Blob([doctoralContent], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Informe_Avance_${doctoralStage}_${project}_${Date.now()}.md`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  const downloadArtifact = async (artifact: ReportArtifact) => {
    if (!artifact.path) return;
    try {
      const blob = await downloadReportArtifact(project, artifact.path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = artifact.label || `artifact_${Date.now()}`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error descargando artefacto");
    }
  };

  const isTopInsightsArtifact = (artifact: ReportArtifact): boolean => {
    const label = (artifact.label || "").toLowerCase();
    const path = (artifact.path || "").toLowerCase();
    return label === "top_10_insights.json" || path.endsWith("/top_10_insights.json");
  };

  function insightTypeBadgeStyle(t: string): React.CSSProperties {
    const key = (t || "").toLowerCase();
    if (key === "explore") return { background: "#e0f2fe", color: "#075985" };
    if (key === "validate") return { background: "#dcfce7", color: "#166534" };
    if (key === "saturate") return { background: "#fef9c3", color: "#854d0e" };
    if (key === "merge") return { background: "#fae8ff", color: "#701a75" };
    return { background: "#e5e7eb", color: "#374151" };
  }

  const chipBase: React.CSSProperties = {
    borderRadius: "999px",
    padding: "0.15rem 0.5rem",
    fontSize: "0.75rem",
    fontWeight: 700,
    display: "inline-flex",
    alignItems: "center",
    gap: "0.25rem",
  };

  const openTopInsightsPreview = async (artifact: ReportArtifact) => {
    if (!artifact.path) return;
    setInsightsPreviewOpen(true);
    setInsightsPreviewLoading(true);
    setInsightsPreviewError(null);
    setInsightsPreviewData(null);
    setInsightsPreviewRaw(null);

    try {
      const blob = await downloadReportArtifact(project, artifact.path);
      const text = await blob.text();
      setInsightsPreviewRaw(text);
      const parsed = JSON.parse(text);

      // Backward compatible: accept either {items: [...]} or a raw array.
      const normalized: TopInsightsArtifact = Array.isArray(parsed)
        ? { schema_version: 0, project, generated_at: undefined, items: parsed as ProductInsightItem[] }
        : (parsed as TopInsightsArtifact);

      // Ensure items is always an array
      if (!Array.isArray(normalized.items)) {
        normalized.items = [];
      }

      setInsightsPreviewData(normalized);
    } catch (err) {
      setInsightsPreviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setInsightsPreviewLoading(false);
    }
  };

  const closeTopInsightsPreview = () => {
    setInsightsPreviewOpen(false);
    setInsightsPreviewLoading(false);
    setInsightsPreviewError(null);
    setInsightsPreviewData(null);
    setInsightsPreviewRaw(null);
  };

  const inferFilenameFromPath = (p?: string | null, fallback: string = `artifact_${Date.now()}`) => {
    if (!p) return fallback;
    const parts = p.replace(/\\/g, "/").split("/").filter(Boolean);
    return parts.length > 0 ? parts[parts.length - 1] : fallback;
  };

  const downloadJobOutput = async (job: ReportJobHistoryItem) => {
    try {
      let blob: Blob | null = null;

      if (job.result_path) {
        blob = await downloadReportArtifact(project, job.result_path);
      } else if (job.blob_url) {
        blob = await downloadFromBlobUrl(job.blob_url);
      }

      if (!blob) {
        throw new Error("Este job no tiene result_path ni blob_url para descargar");
      }

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = inferFilenameFromPath(job.result_path, `${job.job_type || "job"}_${job.task_id}.bin`);
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error descargando job");
    }
  };

  return (
    <div className="reports-panel">
      <header className="reports-panel__header">
        <h2>📊 Informes de Análisis</h2>
        <p>Seguimiento de codificación y saturación teórica por entrevista</p>
      </header>

      {/* Tabs */}
      <nav className="reports-panel__tabs">
        <button
          className={`reports-panel__tab ${activeTab === "list" ? "reports-panel__tab--active" : ""}`}
          onClick={() => setActiveTab("list")}
        >
          📋 Por Entrevista
        </button>
        <button
          className={`reports-panel__tab ${activeTab === "comparison" ? "reports-panel__tab--active" : ""}`}
          onClick={() => setActiveTab("comparison")}
        >
          ⚖️ Comparativo
        </button>
        <button
          className={`reports-panel__tab ${activeTab === "summary" ? "reports-panel__tab--active" : ""}`}
          onClick={() => setActiveTab("summary")}
        >
          🎯 Resumen E4
        </button>
        <button
          className={`reports-panel__tab ${activeTab === "jobs" ? "reports-panel__tab--active" : ""}`}
          onClick={() => setActiveTab("jobs")}
        >
          🧾 Jobs
        </button>
        <button
          className={`reports-panel__tab ${activeTab === "artifacts" ? "reports-panel__tab--active" : ""}`}
          onClick={() => setActiveTab("artifacts")}
        >
          🗂️ Artefactos
        </button>
      </nav>

      {/* Stage Report Generator */}
      <div className="reports-panel__doctoral">
        <div className="reports-panel__doctoral-header">
          <span>📄 Generar Informe de Avance:</span>
          <select
            value={doctoralStage}
            onChange={(e) => setDoctoralStage(e.target.value as "stage3" | "stage4")}
            disabled={doctoralLoading}
          >
            <option value="stage3">Etapa 3 - Codificación Abierta</option>
            <option value="stage4">Etapa 4 - Codificación Axial</option>
          </select>
          <button
            className="reports-panel__doctoral-btn"
            onClick={generateDoctoralReport}
            disabled={doctoralLoading}
          >
            {doctoralLoading ? "Generando..." : "🎓 Generar"}
          </button>
        </div>

        {(doctoralTaskId || doctoralStatus !== "idle" || doctoralStatusMessage) && (
          <div className="reports-panel__doctoral-status">
            <small>
              <strong>Estado:</strong> {doctoralStatus}
              {doctoralTaskId ? ` · task_id: ${doctoralTaskId}` : ""}
              {doctoralStatusMessage ? ` · ${doctoralStatusMessage}` : ""}
            </small>
          </div>
        )}

        {doctoralContent && (
          <div className="reports-panel__doctoral-preview">
            <div className="reports-panel__doctoral-actions">
              <button onClick={downloadDoctoralReport}>💾 Descargar .md</button>
              <button onClick={() => setDoctoralContent(null)}>✕ Cerrar</button>
            </div>

            {doctoralMemoStatements.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                  padding: "0.75rem",
                  border: "1px solid #d1fae5",
                  borderRadius: "0.75rem",
                  background: "#f0fdf4",
                  marginBottom: "0.75rem",
                }}
              >
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
                  <strong style={{ fontSize: "0.9rem" }}>Estatus epistemológico</strong>
                  <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem" }}>
                    <input
                      type="checkbox"
                      checked={showDoctoralTaggedMemo}
                      onChange={(e) => setShowDoctoralTaggedMemo(e.target.checked)}
                    />
                    Mostrar etiquetado
                  </label>
                  <span style={{ fontSize: "0.8rem", color: "#065f46" }}>
                    (OBSERVATION requiere evidencia)
                  </span>
                </div>

                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  {["OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"].map((t) => (
                    <label
                      key={t}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.35rem",
                        padding: "0.35rem 0.55rem",
                        borderRadius: "999px",
                        border: "1px solid rgba(6,95,70,0.15)",
                        background: "white",
                        fontSize: "0.82rem",
                        cursor: "pointer",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(doctoralMemoTypeFilters[t])}
                        onChange={(e) =>
                          setDoctoralMemoTypeFilters((prev) => ({
                            ...prev,
                            [t]: e.target.checked,
                          }))
                        }
                      />
                      <span style={memoBadgeStyle(t)}>{t}</span>
                    </label>
                  ))}
                </div>

                {showDoctoralTaggedMemo && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    {doctoralMemoStatements
                      .filter((s) => doctoralMemoTypeFilters[(s.type || "").toUpperCase()] !== false)
                      .map((s, idx) => {
                        const type = (s.type || "").toUpperCase();
                        const evid = Array.isArray(s.evidence_ids)
                          ? s.evidence_ids.filter((n) => typeof n === "number" && Number.isFinite(n))
                          : [];
                        return (
                          <div
                            key={`${type}-${idx}`}
                            style={{
                              display: "flex",
                              gap: "0.6rem",
                              alignItems: "flex-start",
                              padding: "0.55rem 0.6rem",
                              background: "white",
                              borderRadius: "0.6rem",
                              border: "1px solid rgba(0,0,0,0.06)",
                            }}
                          >
                            <div style={{ paddingTop: "0.05rem" }}>
                              <span style={memoBadgeStyle(type)}>{type}</span>
                            </div>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: "0.92rem", lineHeight: 1.35 }}>{s.text}</div>
                              {evid.length > 0 && (
                                <div style={{ marginTop: "0.2rem", fontSize: "0.78rem", color: "#6b7280" }}>
                                  Evidencia: {evid.join(", ")}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                  </div>
                )}
              </div>
            )}
            <pre>{doctoralContent}</pre>
          </div>
        )}
      </div>

      {loading && <div className="reports-panel__loading">Cargando informes...</div>}
      {error && <div className="reports-panel__error">{error}</div>}

      {/* Lista de informes */}
      {activeTab === "list" && !loading && (
        <div className="reports-panel__list">
          {reports.length === 0 ? (
            <p className="reports-panel__empty">
              No hay informes aún. Analiza una entrevista para generar el primer informe.
            </p>
          ) : (
            <>
              <div className="reports-panel__grid">
                {reports.map((report, idx) => (
                  <div
                    key={idx}
                    className={`reports-panel__card ${selectedReport?.archivo === report.archivo ? "reports-panel__card--selected" : ""}`}
                    onClick={() => setSelectedReport(selectedReport?.archivo === report.archivo ? null : report)}
                  >
                    <div className="reports-panel__card-header">
                      <h4>{report.archivo}</h4>
                      <span
                        className="reports-panel__badge"
                        style={{ backgroundColor: getSaturationColor(report.contribucion_saturacion) }}
                      >
                        {getSaturationLabel(report.contribucion_saturacion)}
                      </span>
                    </div>
                    <div className="reports-panel__card-date">
                      {formatDate(report.fecha_analisis)}
                    </div>
                    <div className="reports-panel__card-stats">
                      <div>
                        <strong>{report.codigos_nuevos}</strong>
                        <span>nuevos</span>
                      </div>
                      <div>
                        <strong>{report.codigos_reutilizados}</strong>
                        <span>reutilizados</span>
                      </div>
                      <div>
                        <strong>{report.categorias_generadas.length}</strong>
                        <span>categorías</span>
                      </div>
                      <div>
                        <strong>{report.relaciones_creadas}</strong>
                        <span>relaciones</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Detalle del informe seleccionado */}
              {selectedReport && (
                <div className="reports-panel__detail">
                  <h3>Detalle: {selectedReport.archivo}</h3>
                  <div className="reports-panel__detail-grid">
                    <div className="reports-panel__metric">
                      <label>Tasa de cobertura</label>
                      <div className="reports-panel__progress">
                        <div
                          className="reports-panel__progress-bar"
                          style={{ width: `${selectedReport.tasa_cobertura}%` }}
                        />
                        <span>{selectedReport.tasa_cobertura.toFixed(1)}%</span>
                      </div>
                    </div>
                    <div className="reports-panel__metric">
                      <label>Aporte de novedad</label>
                      <div className="reports-panel__progress">
                        <div
                          className="reports-panel__progress-bar reports-panel__progress-bar--novelty"
                          style={{ width: `${selectedReport.aporte_novedad}%` }}
                        />
                        <span>{selectedReport.aporte_novedad.toFixed(1)}%</span>
                      </div>
                    </div>
                    <div className="reports-panel__metric">
                      <label>Códigos generados</label>
                      <div className="reports-panel__codes">
                        {selectedReport.codigos_generados.slice(0, 10).map((code, i) => (
                          <span key={i} className="reports-panel__code-tag">{code}</span>
                        ))}
                        {selectedReport.codigos_generados.length > 10 && (
                          <span className="reports-panel__more">+{selectedReport.codigos_generados.length - 10} más</span>
                        )}
                      </div>
                    </div>
                    <div className="reports-panel__metric">
                      <label>Categorías generadas</label>
                      <div className="reports-panel__codes">
                        {selectedReport.categorias_generadas.map((cat, i) => (
                          <span key={i} className="reports-panel__cat-tag">{cat}</span>
                        ))}
                      </div>
                    </div>
                    <div className="reports-panel__metric">
                      <label>Relaciones por tipo</label>
                      <div className="reports-panel__rel-types">
                        {Object.entries(selectedReport.relaciones_por_tipo).map(([tipo, count]) => (
                          <div key={tipo} className="reports-panel__rel-type">
                            <span>{tipo}</span>
                            <strong>{count}</strong>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Vista comparativa */}
      {activeTab === "comparison" && !loading && (
        <div className="reports-panel__comparison">
          <h3>Matriz Comparativa de Códigos</h3>
          {reports.length < 2 ? (
            <p className="reports-panel__empty">
              Se necesitan al menos 2 entrevistas analizadas para la comparación.
            </p>
          ) : (
            <div className="reports-panel__matrix">
              <table>
                <thead>
                  <tr>
                    <th>Métrica</th>
                    {reports.slice(0, 6).map((r, i) => (
                      <th key={i} title={r.archivo}>
                        E{i + 1}
                      </th>
                    ))}
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Códigos nuevos</td>
                    {reports.slice(0, 6).map((r, i) => (
                      <td key={i}>{r.codigos_nuevos}</td>
                    ))}
                    <td><strong>{reports.reduce((sum, r) => sum + r.codigos_nuevos, 0)}</strong></td>
                  </tr>
                  <tr>
                    <td>Códigos reutilizados</td>
                    {reports.slice(0, 6).map((r, i) => (
                      <td key={i}>{r.codigos_reutilizados}</td>
                    ))}
                    <td><strong>{reports.reduce((sum, r) => sum + r.codigos_reutilizados, 0)}</strong></td>
                  </tr>
                  <tr>
                    <td>Categorías</td>
                    {reports.slice(0, 6).map((r, i) => (
                      <td key={i}>{r.categorias_generadas.length}</td>
                    ))}
                    <td><strong>{summary?.total_categorias || "-"}</strong></td>
                  </tr>
                  <tr>
                    <td>Relaciones</td>
                    {reports.slice(0, 6).map((r, i) => (
                      <td key={i}>{r.relaciones_creadas}</td>
                    ))}
                    <td><strong>{summary?.total_relaciones || "-"}</strong></td>
                  </tr>
                  <tr>
                    <td>Saturación</td>
                    {reports.slice(0, 6).map((r, i) => (
                      <td key={i}>
                        <span style={{ color: getSaturationColor(r.contribucion_saturacion) }}>
                          {r.contribucion_saturacion === "baja" ? "🟢" : r.contribucion_saturacion === "media" ? "🟡" : "🔴"}
                        </span>
                      </td>
                    ))}
                    <td>
                      {summary?.saturacion_alcanzada ? "✅" : "⏳"}
                    </td>
                  </tr>
                </tbody>
              </table>
              <p className="reports-panel__matrix-legend">
                E1-E6 = Entrevistas en orden cronológico. 🟢 = Saturando, 🟡 = Media, 🔴 = Alta novedad
              </p>
            </div>
          )}
        </div>
      )}

      {/* Resumen Etapa 4 */}
      {activeTab === "summary" && !loading && (
        <div className="reports-panel__summary">
          {summary ? (
            <>
              <div className="reports-panel__summary-header">
                <h3>🎯 Resumen Etapa 4 - Codificación Axial</h3>
                <button
                  className="reports-panel__export"
                  onClick={exportToMarkdown}
                >
                  💾 Exportar Informe
                </button>
              </div>

              <div style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
                padding: "0.75rem",
                borderRadius: "0.75rem",
                border: "1px solid #e2e8f0",
                background: "#ffffff",
                marginBottom: "1rem",
              }}>
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
                  <strong style={{ color: "#0f172a" }}>Informe final Etapa 4 (IA)</strong>
                  <button
                    className="reports-panel__export"
                    onClick={generateStage4FinalReport}
                    disabled={stage4FinalLoading}
                    title="Genera el informe final Etapa 4 con análisis IA (async job)"
                  >
                    {stage4FinalLoading ? "Generando..." : "⚡ Generar Stage4-final"}
                  </button>
                  {(stage4FinalTaskId || stage4FinalStatus !== "idle" || stage4FinalStatusMessage) && (
                    <small style={{ color: "#475569" }}>
                      <strong>Estado:</strong> {stage4FinalStatus}
                      {stage4FinalTaskId ? ` · task_id: ${stage4FinalTaskId}` : ""}
                      {stage4FinalStatusMessage ? ` · ${stage4FinalStatusMessage}` : ""}
                    </small>
                  )}
                </div>

                {stage4FinalResult?.report?.ia_analysis && (
                  <div style={{
                    marginTop: "0.5rem",
                    padding: "0.75rem",
                    borderRadius: "0.75rem",
                    background: "#f8fafc",
                    border: "1px solid #e2e8f0",
                  }}>
                    <h4 style={{ margin: "0 0 0.5rem 0" }}>🧠 Análisis (IA)</h4>

                    {stage4FinalMemoStatements.length > 0 && (
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.75rem",
                          padding: "0.75rem",
                          border: "1px solid #c4b5fd",
                          borderRadius: "0.75rem",
                          background: "rgba(255,255,255,0.9)",
                          marginBottom: "0.75rem",
                        }}
                      >
                        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
                          <strong style={{ fontSize: "0.9rem" }}>Estatus epistemológico</strong>
                          <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem" }}>
                            <input
                              type="checkbox"
                              checked={showStage4FinalTaggedMemo}
                              onChange={(e) => setShowStage4FinalTaggedMemo(e.target.checked)}
                            />
                            Mostrar etiquetado
                          </label>
                          <span style={{ fontSize: "0.8rem", color: "#6b21a8" }}>
                            (OBSERVATION requiere evidencia)
                          </span>
                        </div>

                        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                          {["OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"].map((t) => (
                            <label
                              key={t}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.35rem",
                                padding: "0.35rem 0.55rem",
                                borderRadius: "999px",
                                border: "1px solid rgba(91,33,182,0.15)",
                                background: "white",
                                fontSize: "0.82rem",
                                cursor: "pointer",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={Boolean(stage4FinalMemoTypeFilters[t])}
                                onChange={(e) =>
                                  setStage4FinalMemoTypeFilters((prev) => ({
                                    ...prev,
                                    [t]: e.target.checked,
                                  }))
                                }
                              />
                              <span style={memoBadgeStyle(t)}>{t}</span>
                            </label>
                          ))}
                        </div>

                        {showStage4FinalTaggedMemo && (
                          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                            {stage4FinalMemoStatements
                              .filter((s) => stage4FinalMemoTypeFilters[(s.type || "").toUpperCase()] !== false)
                              .map((s, idx) => {
                                const type = (s.type || "").toUpperCase();
                                const evid = Array.isArray(s.evidence_ids)
                                  ? s.evidence_ids.filter((n) => typeof n === "number" && Number.isFinite(n))
                                  : [];
                                return (
                                  <div
                                    key={`${type}-${idx}`}
                                    style={{
                                      display: "flex",
                                      gap: "0.6rem",
                                      alignItems: "flex-start",
                                      padding: "0.55rem 0.6rem",
                                      background: "white",
                                      borderRadius: "0.6rem",
                                      border: "1px solid rgba(0,0,0,0.06)",
                                    }}
                                  >
                                    <div style={{ paddingTop: "0.05rem" }}>
                                      <span style={memoBadgeStyle(type)}>{type}</span>
                                    </div>
                                    <div style={{ flex: 1 }}>
                                      <div style={{ fontSize: "0.92rem", lineHeight: 1.35 }}>{s.text}</div>
                                      {evid.length > 0 && (
                                        <div style={{ marginTop: "0.2rem", fontSize: "0.78rem", color: "#6b7280" }}>
                                          Evidencia: {evid.join(", ")}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                          </div>
                        )}
                      </div>
                    )}

                    <div>
                      {(String(stage4FinalResult.report.ia_analysis) || "").split("\n").map((line: string, idx: number) => (
                        <p key={idx} style={{ margin: "0.35rem 0", lineHeight: 1.5 }}>{line}</p>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="reports-panel__summary-cards">
                <div className="reports-panel__summary-card">
                  <span className="reports-panel__summary-icon">📝</span>
                  <div>
                    <strong>{summary.total_entrevistas}</strong>
                    <label>Entrevistas</label>
                  </div>
                </div>
                <div className="reports-panel__summary-card">
                  <span className="reports-panel__summary-icon">🏷️</span>
                  <div>
                    <strong>{summary.total_codigos_unicos}</strong>
                    <label>Códigos únicos</label>
                  </div>
                </div>
                <div className="reports-panel__summary-card">
                  <span className="reports-panel__summary-icon">📂</span>
                  <div>
                    <strong>{summary.total_categorias}</strong>
                    <label>Categorías</label>
                  </div>
                </div>
                <div className="reports-panel__summary-card">
                  <span className="reports-panel__summary-icon">🔗</span>
                  <div>
                    <strong>{summary.total_relaciones}</strong>
                    <label>Relaciones</label>
                  </div>
                </div>
              </div>

              <div className="reports-panel__saturation-box">
                <h4>Score de Saturación Teórica</h4>
                <div className="reports-panel__saturation-meter">
                  <div
                    className="reports-panel__saturation-fill"
                    style={{
                      width: `${summary.score_saturacion * 100}%`,
                      backgroundColor: summary.saturacion_alcanzada ? "#22c55e" : "#f59e0b",
                    }}
                  />
                  <span>{(summary.score_saturacion * 100).toFixed(0)}%</span>
                </div>
                <p>
                  {summary.saturacion_alcanzada
                    ? "✅ Saturación teórica alcanzada. Puede proceder a Etapa 5."
                    : "⏳ Continúe analizando entrevistas hasta que los códigos nuevos disminuyan."}
                </p>
              </div>

              {summary.saturacion_alcanzada && (
                <div className="reports-panel__next-step">
                  <h4>🚀 Siguiente paso: Etapa 5 - Selección del Núcleo</h4>
                  <p>
                    Con la saturación teórica alcanzada, puede proceder a identificar
                    la categoría central que integra todas las demás.
                  </p>
                </div>
              )}
            </>
          ) : (
            <p className="reports-panel__empty">
              No hay datos suficientes para generar el resumen.
            </p>
          )}
        </div>
      )}

      {/* Jobs (historial de ejecuciones) */}
      {activeTab === "jobs" && (
        <div className="reports-panel__summary">
          <div className="reports-panel__summary-header" style={{ marginBottom: "0.75rem" }}>
            <h3>🧾 Historial de ejecuciones (Jobs)</h3>
            <button className="reports-panel__export" onClick={() => loadJobs({ reset: true })} disabled={jobsLoading}>
              {jobsLoading ? "Actualizando..." : "↻ Refrescar"}
            </button>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.75rem" }}>
            <label style={{ display: "flex", gap: "0.4rem", alignItems: "center", color: "#475569", fontSize: "0.9rem" }}>
              Status:
              <select
                value={jobsStatusFilter}
                onChange={(e) => setJobsStatusFilter(e.target.value)}
                disabled={jobsLoading}
              >
                <option value="">(todos)</option>
                <option value="pending">pending</option>
                <option value="running">running</option>
                <option value="completed">completed</option>
                <option value="error">error</option>
              </select>
            </label>

            <label style={{ display: "flex", gap: "0.4rem", alignItems: "center", color: "#475569", fontSize: "0.9rem" }}>
              Tipo:
              <input
                value={jobsTypeFilter}
                onChange={(e) => setJobsTypeFilter(e.target.value)}
                disabled={jobsLoading}
                placeholder="doctoral | stage4-final | ..."
                style={{ padding: "0.35rem 0.5rem", border: "1px solid #e2e8f0", borderRadius: "0.5rem", minWidth: "220px" }}
              />
            </label>

            <label style={{ display: "flex", gap: "0.4rem", alignItems: "center", color: "#475569", fontSize: "0.9rem" }}>
              task_id:
              <input
                value={jobsTaskDraft}
                onChange={(e) => setJobsTaskDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") applyJobsSearch();
                }}
                disabled={jobsLoading}
                placeholder="prefijo o =exacto"
                style={{ padding: "0.35rem 0.5rem", border: "1px solid #e2e8f0", borderRadius: "0.5rem", minWidth: "220px" }}
                title="Usa prefijo para buscar rápido. Usa '=task_id' para exacto."
              />
            </label>

            <label style={{ display: "flex", gap: "0.4rem", alignItems: "center", color: "#475569", fontSize: "0.9rem" }}>
              texto:
              <input
                value={jobsTextDraft}
                onChange={(e) => setJobsTextDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") applyJobsSearch();
                }}
                disabled={jobsLoading}
                placeholder="buscar en message"
                style={{ padding: "0.35rem 0.5rem", border: "1px solid #e2e8f0", borderRadius: "0.5rem", minWidth: "240px" }}
              />
            </label>

            <button
              className="reports-panel__export"
              onClick={applyJobsSearch}
              disabled={jobsLoading}
              title="Aplicar búsqueda"
            >
              🔎 Buscar
            </button>
            <button
              className="reports-panel__export"
              onClick={clearJobsSearch}
              disabled={jobsLoading}
              title="Limpiar búsqueda"
            >
              ✨ Limpiar
            </button>
          </div>

          {jobsLoading ? (
            <div className="reports-panel__loading">Cargando jobs...</div>
          ) : jobs.length === 0 ? (
            <p className="reports-panel__empty">Aún no hay ejecuciones registradas para este proyecto.</p>
          ) : (
            <div style={{ display: "grid", gap: "0.6rem" }}>
              {jobs.slice(0, 80).map((job) => {
                const status = (job.status || "").toLowerCase();
                const badgeColor = status === "completed" ? "#22c55e" : status === "error" ? "#ef4444" : "#f59e0b";
                const canDownload = Boolean(job.result_path || job.blob_url);

                return (
                  <div key={job.task_id} className="reports-panel__card" style={{ cursor: "default" }}>
                    <div className="reports-panel__card-header">
                      <h4 style={{ margin: 0 }}>
                        {job.job_type || "job"} · <span style={{ color: "#64748b" }}>{job.task_id}</span>
                      </h4>
                      <span className="reports-panel__badge" style={{ backgroundColor: badgeColor }}>
                        {job.status}
                      </span>
                    </div>
                    {(job.started_at || job.finished_at || job.created_at) && (
                      <div className="reports-panel__card-date">
                        {job.finished_at ? `Finalizado: ${formatDate(job.finished_at)}`
                          : job.started_at ? `Iniciado: ${formatDate(job.started_at)}`
                          : job.created_at ? `Creado: ${formatDate(job.created_at)}` : ""}
                      </div>
                    )}
                    {job.message && (
                      <div style={{ color: "#334155", fontSize: "0.9rem", whiteSpace: "pre-wrap" }}>
                        {job.message}
                      </div>
                    )}

                    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.6rem", alignItems: "center" }}>
                      <button
                        className="reports-panel__export"
                        onClick={() => downloadJobOutput(job)}
                        disabled={!canDownload}
                        title={job.result_path ? "Descargar (backend preferirá Blob si existe)" : job.blob_url ? "Descargar desde blob_url (proxy backend)" : "Sin salida descargable"}
                      >
                        ⬇️ Descargar
                      </button>
                      {job.result_path && (
                        <div style={{ color: "#0369a1", fontSize: "0.85rem", overflow: "hidden", textOverflow: "ellipsis" }}>
                          result_path: {job.result_path}
                        </div>
                      )}
                      {!job.result_path && job.blob_url && (
                        <div style={{ color: "#0369a1", fontSize: "0.85rem", overflow: "hidden", textOverflow: "ellipsis" }}>
                          blob_url: {job.blob_url}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              <div style={{ display: "flex", justifyContent: "center", marginTop: "0.75rem" }}>
                <button
                  className="reports-panel__export"
                  onClick={() => loadJobs({ append: true })}
                  disabled={jobsLoading || !jobsHasMore}
                  title={jobsHasMore ? "Cargar más" : "No hay más resultados"}
                >
                  {jobsLoading ? "Cargando..." : jobsHasMore ? "Cargar más" : "Sin más resultados"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Artefactos */}
      {activeTab === "artifacts" && (
        <div className="reports-panel__summary">
          <div className="reports-panel__summary-header">
            <h3>🗂️ Artefactos recientes</h3>
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              <button
                className="reports-panel__export"
                onClick={handleGenerateProductArtifacts}
                disabled={productGenLoading}
                title="Genera executive_summary.md, top_10_insights.json y open_questions.md"
              >
                {productGenLoading ? "Generando..." : "✨ Generar resumen producto"}
              </button>
              <button className="reports-panel__export" onClick={loadArtifacts} disabled={artifactsLoading}>
                {artifactsLoading ? "Actualizando..." : "↻ Refrescar"}
              </button>
            </div>
          </div>

          {productGenMessage && (
            <div style={{ marginBottom: "0.75rem", color: "#334155", fontSize: "0.9rem" }}>
              {productGenMessage}
            </div>
          )}

          {artifactsLoading ? (
            <div className="reports-panel__loading">Cargando artefactos...</div>
          ) : artifacts.length === 0 ? (
            <p className="reports-panel__empty">
              Aún no hay artefactos detectados. Ejecuta análisis, Discovery, GraphRAG o Runner.
            </p>
          ) : (
            <div style={{ display: "grid", gap: "0.75rem" }}>
              {artifacts.slice(0, 80).map((a, idx) => (
                <div
                  key={`${a.source}-${a.kind}-${a.label}-${idx}`}
                  className="reports-panel__card"
                  style={{ cursor: a.path ? "pointer" : "default" }}
                  onClick={() => {
                    if (!a.path) return;
                    if (isTopInsightsArtifact(a)) {
                      void openTopInsightsPreview(a);
                    } else {
                      void downloadArtifact(a);
                    }
                  }}
                  title={a.path ? (isTopInsightsArtifact(a) ? "Click para previsualizar" : "Click para descargar") : "Sin archivo descargable"}
                >
                  <div className="reports-panel__card-header">
                    <h4 style={{ margin: 0 }}>{a.label}</h4>
                    <span className="reports-panel__badge" style={{ backgroundColor: "#64748b" }}>
                      {a.source}:{a.kind}
                    </span>
                  </div>
                  {a.created_at && <div className="reports-panel__card-date">{formatDate(a.created_at)}</div>}
                  {a.excerpt && (
                    <div style={{ color: "#334155", fontSize: "0.9rem", whiteSpace: "pre-wrap" }}>
                      {a.excerpt}
                    </div>
                  )}
                  {a.path && (
                    <div style={{ marginTop: "0.35rem", color: "#0369a1", fontSize: "0.85rem" }}>
                      Descargar: {a.path}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Modal: Top insights preview */}
          {insightsPreviewOpen && (
            <div
              role="dialog"
              aria-modal="true"
              onClick={closeTopInsightsPreview}
              style={{
                position: "fixed",
                inset: 0,
                background: "rgba(15, 23, 42, 0.55)",
                display: "flex",
                justifyContent: "center",
                alignItems: "flex-start",
                padding: "2rem 1rem",
                zIndex: 1000,
                overflow: "auto",
              }}
            >
              <div
                onClick={(e) => e.stopPropagation()}
                style={{
                  width: "min(980px, 100%)",
                  background: "white",
                  borderRadius: "0.9rem",
                  border: "1px solid #e2e8f0",
                  boxShadow: "0 16px 40px rgba(0,0,0,0.25)",
                  padding: "1rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
                  <div>
                    <h3 style={{ margin: 0, color: "#0f172a" }}>Top Insights (vista previa)</h3>
                    <div style={{ color: "#64748b", fontSize: "0.85rem", marginTop: "0.25rem" }}>
                      {insightsPreviewData?.project || project}
                      {insightsPreviewData?.generated_at ? ` · ${formatDate(insightsPreviewData.generated_at)}` : ""}
                      {typeof insightsPreviewData?.schema_version === "number" ? ` · schema v${insightsPreviewData.schema_version}` : ""}
                    </div>
                  </div>
                  <button className="reports-panel__export" onClick={closeTopInsightsPreview}>
                    Cerrar
                  </button>
                </div>

                {insightsPreviewLoading ? (
                  <div className="reports-panel__loading">Cargando top_10_insights.json…</div>
                ) : insightsPreviewError ? (
                  <div className="reports-panel__error" style={{ marginTop: "0.75rem" }}>
                    {insightsPreviewError}
                  </div>
                ) : !insightsPreviewData ? (
                  <div className="reports-panel__empty">Sin datos</div>
                ) : (
                  <div style={{ marginTop: "0.75rem", display: "grid", gap: "0.75rem" }}>
                    {(insightsPreviewData.items || []).length === 0 ? (
                      <div className="reports-panel__empty">No hay insights en este artefacto.</div>
                    ) : (
                      (insightsPreviewData.items || []).slice(0, 50).map((it, i) => {
                        const t = (it.insight_type || "insight").toLowerCase();
                        const pr = typeof it.priority === "number" ? it.priority : (it.priority ? Number(it.priority) : 0);
                        const minFrags = it.suggested_query?.min_fragments;

                        return (
                          <div key={`${it.id ?? i}`} style={{ border: "1px solid #e2e8f0", borderRadius: "0.75rem", padding: "0.9rem" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
                              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                                <span style={{ ...chipBase, ...insightTypeBadgeStyle(t) }}>{(t || "insight").toUpperCase()}</span>
                                <span style={{ ...chipBase, background: "#f1f5f9", color: "#0f172a" }}>PRIORIDAD: {Math.round((isFinite(pr) ? pr : 0) * 100)}%</span>
                                <span style={{ ...chipBase, background: "#f8fafc", color: "#334155" }}>
                                  #FRAGS≥{typeof minFrags === "number" ? minFrags : "?"}
                                </span>
                              </div>
                              <div style={{ color: "#64748b", fontSize: "0.8rem", textAlign: "right" }}>
                                {it.status ? <div>status: {it.status}</div> : null}
                                {it.source_type ? <div>source: {it.source_type}</div> : null}
                              </div>
                            </div>

                            <div style={{ marginTop: "0.6rem", color: "#0f172a", fontSize: "0.95rem", whiteSpace: "pre-wrap" }}>
                              {it.content || "(sin contenido)"}
                            </div>

                            <div style={{ marginTop: "0.75rem" }}>
                              <div style={{ fontWeight: 700, color: "#0f172a", marginBottom: "0.35rem" }}>Evidencia (suggested_query)</div>
                              {it.suggested_query ? (
                                <div style={{ display: "grid", gap: "0.5rem" }}>
                                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                                    {it.suggested_query.action ? (
                                      <span style={{ ...chipBase, background: "#e2e8f0", color: "#0f172a" }}>action: {String(it.suggested_query.action)}</span>
                                    ) : null}
                                    {Array.isArray(it.suggested_query.positivos) && it.suggested_query.positivos.length > 0 ? (
                                      <span style={{ ...chipBase, background: "#dcfce7", color: "#166534" }}>+ {it.suggested_query.positivos.slice(0, 6).join(", ")}</span>
                                    ) : null}
                                    {Array.isArray(it.suggested_query.negativos) && it.suggested_query.negativos.length > 0 ? (
                                      <span style={{ ...chipBase, background: "#fee2e2", color: "#991b1b" }}>- {it.suggested_query.negativos.slice(0, 6).join(", ")}</span>
                                    ) : null}
                                    {Array.isArray(it.suggested_query.codes) && it.suggested_query.codes.length > 0 ? (
                                      <span style={{ ...chipBase, background: "#fae8ff", color: "#701a75" }}>codes: {it.suggested_query.codes.slice(0, 6).join(", ")}</span>
                                    ) : null}
                                  </div>
                                  <pre
                                    style={{
                                      margin: 0,
                                      background: "#0b1220",
                                      color: "#e5e7eb",
                                      padding: "0.75rem",
                                      borderRadius: "0.6rem",
                                      overflowX: "auto",
                                      fontSize: "0.8rem",
                                    }}
                                  >
                                    {JSON.stringify(it.suggested_query, null, 2)}
                                  </pre>
                                </div>
                              ) : (
                                <div style={{ color: "#64748b" }}>(sin suggested_query)</div>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}

                    {/* Optional raw JSON for debugging (collapsed) */}
                    {insightsPreviewRaw && (
                      <details style={{ marginTop: "0.5rem" }}>
                        <summary style={{ cursor: "pointer", color: "#0369a1" }}>Ver JSON crudo</summary>
                        <pre
                          style={{
                            marginTop: "0.5rem",
                            background: "#0b1220",
                            color: "#e5e7eb",
                            padding: "0.75rem",
                            borderRadius: "0.6rem",
                            overflowX: "auto",
                            fontSize: "0.8rem",
                          }}
                        >
                          {insightsPreviewRaw}
                        </pre>
                      </details>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <style>{`
        .reports-panel {
          padding: 1.5rem;
          background: #f8fafc;
          border-radius: 0.75rem;
        }
        .reports-panel__header h2 {
          margin: 0 0 0.25rem 0;
          font-size: 1.25rem;
          color: #1e293b;
        }
        .reports-panel__header p {
          margin: 0;
          color: #64748b;
          font-size: 0.875rem;
        }
        .reports-panel__tabs {
          display: flex;
          gap: 0.5rem;
          margin: 1rem 0;
          border-bottom: 1px solid #e2e8f0;
          padding-bottom: 0.5rem;
        }
        .reports-panel__tab {
          padding: 0.5rem 1rem;
          background: none;
          border: none;
          border-radius: 0.5rem;
          cursor: pointer;
          color: #64748b;
          font-weight: 500;
        }
        .reports-panel__tab--active {
          background: #3b82f6;
          color: white;
        }
        .reports-panel__loading {
          padding: 2rem;
          text-align: center;
          color: #64748b;
        }
        .reports-panel__error {
          padding: 1rem;
          background: #fef2f2;
          border: 1px solid #fecaca;
          border-radius: 0.5rem;
          color: #dc2626;
        }
        .reports-panel__empty {
          padding: 2rem;
          text-align: center;
          color: #94a3b8;
          font-style: italic;
        }
        .reports-panel__grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 1rem;
        }
        .reports-panel__card {
          background: white;
          border: 1px solid #e2e8f0;
          border-radius: 0.75rem;
          padding: 1rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        .reports-panel__card:hover {
          border-color: #3b82f6;
          box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
        }
        .reports-panel__card--selected {
          border-color: #3b82f6;
          background: #eff6ff;
        }
        .reports-panel__card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 0.5rem;
        }
        .reports-panel__card-header h4 {
          margin: 0;
          font-size: 0.9rem;
          color: #1e293b;
          word-break: break-word;
        }
        .reports-panel__badge {
          padding: 0.2rem 0.5rem;
          border-radius: 1rem;
          font-size: 0.7rem;
          color: white;
          white-space: nowrap;
        }
        .reports-panel__card-date {
          font-size: 0.75rem;
          color: #94a3b8;
          margin: 0.5rem 0;
        }
        .reports-panel__card-stats {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 0.5rem;
          margin-top: 0.75rem;
        }
        .reports-panel__card-stats div {
          text-align: center;
        }
        .reports-panel__card-stats strong {
          display: block;
          font-size: 1.25rem;
          color: #1e293b;
        }
        .reports-panel__card-stats span {
          font-size: 0.65rem;
          color: #94a3b8;
        }
        .reports-panel__detail {
          margin-top: 1.5rem;
          padding: 1.5rem;
          background: white;
          border-radius: 0.75rem;
          border: 1px solid #e2e8f0;
        }
        .reports-panel__detail h3 {
          margin: 0 0 1rem 0;
          color: #1e293b;
        }
        .reports-panel__detail-grid {
          display: grid;
          gap: 1rem;
        }
        .reports-panel__metric label {
          display: block;
          font-size: 0.8rem;
          color: #64748b;
          margin-bottom: 0.5rem;
        }
        .reports-panel__progress {
          height: 1.5rem;
          background: #e2e8f0;
          border-radius: 0.5rem;
          position: relative;
          overflow: hidden;
        }
        .reports-panel__progress-bar {
          height: 100%;
          background: linear-gradient(90deg, #3b82f6, #2563eb);
          border-radius: 0.5rem;
        }
        .reports-panel__progress-bar--novelty {
          background: linear-gradient(90deg, #f59e0b, #d97706);
        }
        .reports-panel__progress span {
          position: absolute;
          right: 0.5rem;
          top: 50%;
          transform: translateY(-50%);
          font-size: 0.75rem;
          font-weight: 600;
          color: #1e293b;
        }
        .reports-panel__codes {
          display: flex;
          flex-wrap: wrap;
          gap: 0.3rem;
        }
        .reports-panel__code-tag {
          padding: 0.2rem 0.5rem;
          background: #dbeafe;
          color: #1e40af;
          border-radius: 0.25rem;
          font-size: 0.75rem;
        }
        .reports-panel__cat-tag {
          padding: 0.2rem 0.5rem;
          background: #fef3c7;
          color: #92400e;
          border-radius: 0.25rem;
          font-size: 0.75rem;
        }
        .reports-panel__more {
          font-size: 0.75rem;
          color: #64748b;
        }
        .reports-panel__rel-types {
          display: flex;
          gap: 1rem;
          flex-wrap: wrap;
        }
        .reports-panel__rel-type {
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 0.5rem;
          background: #f1f5f9;
          border-radius: 0.5rem;
        }
        .reports-panel__rel-type span {
          font-size: 0.7rem;
          color: #64748b;
        }
        .reports-panel__rel-type strong {
          font-size: 1.1rem;
          color: #1e293b;
        }
        .reports-panel__matrix {
          overflow-x: auto;
        }
        .reports-panel__matrix table {
          width: 100%;
          border-collapse: collapse;
          background: white;
        }
        .reports-panel__matrix th,
        .reports-panel__matrix td {
          padding: 0.75rem;
          text-align: center;
          border: 1px solid #e2e8f0;
        }
        .reports-panel__matrix th {
          background: #f1f5f9;
          font-weight: 600;
          color: #475569;
        }
        .reports-panel__matrix td:first-child {
          text-align: left;
          font-weight: 500;
        }
        .reports-panel__matrix-legend {
          margin-top: 0.75rem;
          font-size: 0.75rem;
          color: #64748b;
        }
        .reports-panel__summary-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }
        .reports-panel__summary-header h3 {
          margin: 0;
        }
        .reports-panel__export {
          padding: 0.5rem 1rem;
          background: linear-gradient(135deg, #059669, #10b981);
          color: white;
          border: none;
          border-radius: 0.5rem;
          cursor: pointer;
          font-weight: 600;
        }
        .reports-panel__export:hover {
          background: linear-gradient(135deg, #047857, #059669);
        }
        .reports-panel__summary-cards {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 1rem;
          margin-bottom: 1.5rem;
        }
        .reports-panel__summary-card {
          display: flex;
          align-items: center;
          gap: 1rem;
          padding: 1rem;
          background: white;
          border-radius: 0.75rem;
          border: 1px solid #e2e8f0;
        }
        .reports-panel__summary-icon {
          font-size: 2rem;
        }
        .reports-panel__summary-card strong {
          display: block;
          font-size: 1.5rem;
          color: #1e293b;
        }
        .reports-panel__summary-card label {
          font-size: 0.75rem;
          color: #64748b;
        }
        .reports-panel__saturation-box {
          padding: 1.5rem;
          background: white;
          border-radius: 0.75rem;
          border: 1px solid #e2e8f0;
          margin-bottom: 1rem;
        }
        .reports-panel__saturation-box h4 {
          margin: 0 0 1rem 0;
          color: #1e293b;
        }
        .reports-panel__saturation-meter {
          height: 2rem;
          background: #e2e8f0;
          border-radius: 1rem;
          position: relative;
          overflow: hidden;
        }
        .reports-panel__saturation-fill {
          height: 100%;
          border-radius: 1rem;
          transition: width 0.5s ease;
        }
        .reports-panel__saturation-meter span {
          position: absolute;
          right: 1rem;
          top: 50%;
          transform: translateY(-50%);
          font-weight: 700;
          color: #1e293b;
        }
        .reports-panel__saturation-box p {
          margin: 1rem 0 0 0;
          color: #64748b;
        }
        .reports-panel__next-step {
          padding: 1.5rem;
          background: linear-gradient(135deg, #ecfdf5, #d1fae5);
          border: 1px solid #a7f3d0;
          border-radius: 0.75rem;
        }
        .reports-panel__next-step h4 {
          margin: 0 0 0.5rem 0;
          color: #065f46;
        }
        .reports-panel__next-step p {
          margin: 0;
          color: #047857;
        }
        /* Doctoral Report Styles */
        .reports-panel__doctoral {
          margin: 1rem 0;
          padding: 1rem;
          background: linear-gradient(135deg, #f5f3ff, #ede9fe);
          border: 1px solid #c4b5fd;
          border-radius: 0.75rem;
        }
        .reports-panel__doctoral-header {
          display: flex;
          align-items: center;
          gap: 1rem;
          flex-wrap: wrap;
        }
        .reports-panel__doctoral-header span {
          font-weight: 600;
          color: #5b21b6;
        }
        .reports-panel__doctoral-header select {
          padding: 0.5rem 1rem;
          border-radius: 0.5rem;
          border: 1px solid #c4b5fd;
          background: white;
        }
        .reports-panel__doctoral-btn {
          padding: 0.5rem 1.5rem;
          background: linear-gradient(135deg, #7c3aed, #8b5cf6);
          color: white;
          border: none;
          border-radius: 0.5rem;
          cursor: pointer;
          font-weight: 600;
        }
        .reports-panel__doctoral-btn:disabled {
          opacity: 0.6;
          cursor: wait;
        }
        .reports-panel__doctoral-preview {
          margin-top: 1rem;
          background: white;
          border-radius: 0.5rem;
          border: 1px solid #e5e7eb;
          max-height: 400px;
          overflow: auto;
        }
        .reports-panel__doctoral-actions {
          display: flex;
          gap: 0.5rem;
          padding: 0.75rem;
          background: #f9fafb;
          border-bottom: 1px solid #e5e7eb;
        }
        .reports-panel__doctoral-actions button {
          padding: 0.4rem 0.8rem;
          border: 1px solid #d1d5db;
          background: white;
          border-radius: 0.5rem;
          cursor: pointer;
        }
        .reports-panel__doctoral-actions button:first-child {
          background: #22c55e;
          color: white;
          border-color: #22c55e;
        }
        .reports-panel__doctoral-preview pre {
          padding: 1rem;
          white-space: pre-wrap;
          font-size: 0.8rem;
          line-height: 1.5;
          margin: 0;
        }
      `}</style>
    </div>
  );
}

export default ReportsPanel;
