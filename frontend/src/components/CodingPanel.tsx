/**
 * @fileoverview Panel completo de codificación abierta y axial.
 * 
 * Componente más grande del frontend (1017 líneas). Implementa:
 * 
 * Pestañas:
 * 1. "Asignar código" - Asignar códigos manualmente a fragmentos
 * 2. "Sugerencias semánticas" - Fragmentos similares via Qdrant
 * 3. "Cobertura y avance" - Estadísticas de codificación
 * 4. "Citas por código" - Ver citas asociadas a cada código
 * 
 * Funcionalidades:
 * - Lista de entrevistas disponibles
 * - Selección de fragmentos
 * - Asignación de códigos con cita y memo
 * - Sugerencias semánticas basadas en embeddings
 * - Estadísticas de cobertura (% fragmentos codificados)
 * 
 * API endpoints utilizados:
 * - GET /api/interviews
 * - GET /api/coding/fragments
 * - GET /api/coding/codes
 * - POST /api/coding/assign
 * - POST /api/coding/suggest
 * - GET /api/coding/stats
 * - GET /api/coding/citations
 * 
 * @module components/CodingPanel
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  CodingAssignPayload,
  CodingCitationsResponse,
  CodingNextResponse,
  CodingStats,
  CodingSuggestion,
  CodingSuggestResponse,
  CodeSummary,
  CodeSummaryResponse,
  FragmentSample,
  FragmentSampleResponse,
  FragmentListResponse,
  InterviewSummary,
  InterviewSummaryResponse
} from "../types";
import { apiFetch, apiFetchJson, getCodingNext, postCodingFeedback, submitCandidate, logDiscoveryNavigation } from "../services/api";
import { formatPercentage } from "../utils/format";
import { FragmentContextModal } from "./FragmentContextModal";
import { ActionSuggestionCard } from "./ActionSuggestionCard";

type TabKey = "guided" | "assign" | "suggest" | "insights" | "citations";

const tabs: Array<{ key: TabKey; label: string; description: string }> = [
  { key: "guided", label: "🧭 Siguiente recomendado", description: "Flujo guiado: siguiente fragmento + decisión rápida" },
  { key: "assign", label: "📝 Asignar código", description: "Asigna códigos manualmente a fragmentos" },
  { key: "suggest", label: "🔍 Sugerencias semánticas", description: "Fragmentos similares para comparación constante" },
  { key: "insights", label: "📊 Cobertura y avance", description: "Estadísticas de codificación" },
  { key: "citations", label: "📎 Citas por código", description: "Ver citas asociadas a cada código" }
];

interface CodingPanelProps {
  project: string;
  refreshKey?: number;
  initialArchivo?: string | null;
}

interface FetchError {
  error?: string;
  [key: string]: unknown;
}

interface CodingSuggestRunnerExecuteResponse {
  task_id: string;
  status: string;
}

interface CodingSuggestRunnerResumeResponse {
  task_id: string;
  status: string;
  resumed_from?: string;
}

interface CodingSuggestRunnerStatusResponse {
  task_id: string;
  status: "pending" | "running" | "completed" | "error";
  current_step: number;
  total_steps: number;
  visited_seeds: number;
  unique_suggestions: number;
  current_archivo?: string | null;
  current_step_in_interview?: number;
  steps_per_interview?: number;
  interview_index?: number;
  interviews_total?: number;
  memos_saved?: number;
  candidates_submitted?: number;
  candidates_pending_before_db?: number | null;
  candidates_pending_after_db?: number | null;
  llm_calls?: number;
  llm_failures?: number;
  qdrant_failures?: number;
  qdrant_retries?: number;
  last_suggested_code?: string | null;
  saturated?: boolean;
  message?: string | null;
  errors?: string[] | null;
  report_path?: string | null;
}

interface CodingSuggestRunnerResultResponse {
  task_id: string;
  project: string;
  status: string;
  steps_requested: number;
  steps_completed: number;
  seed_fragment_id: string;
  visited_seed_ids: string[];
  suggestions: CodingSuggestion[];
  iterations: Array<{
    step: number;
    seed_fragment_id?: string;
    archivo?: string;
    step_in_interview?: number;
    returned?: number;
    elapsed_ms?: number;
    next_seed?: string | null;
    suggested_code?: string | null;
    memo_path?: string | null;
    candidates_inserted?: number;
  }>;
  memos?: Array<{
    filename?: string;
    path?: string;
    rel?: string;
    archivo?: string;
    step?: number;
    step_in_interview?: number;
    seed_fragment_id?: string;
    suggested_code?: string | null;
  }>;
  candidates_submitted?: number;
  candidates_pending_before_db?: number | null;
  candidates_pending_after_db?: number | null;
  llm_calls?: number;
  llm_failures?: number;
  errors?: string[] | null;
  report_path?: string | null;
}

// Clave de localStorage para persistir el scope de entrevista
const INTERVIEW_SCOPE_KEY = "qualy-interview-scope";

export function CodingPanel({ project, refreshKey, initialArchivo }: CodingPanelProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("guided");

  // Filtro global de entrevista para Etapa 3 (análisis por entrevista individual)
  // Persistido en localStorage para mantener contexto entre sesiones
  const [activeInterviewFilter, setActiveInterviewFilter] = useState<string>(() => {
    try {
      const stored = localStorage.getItem(`${INTERVIEW_SCOPE_KEY}-${project}`);
      return stored || "";
    } catch {
      return "";
    }
  });

  // Derivar el modo de scope del filtro activo
  const scopeMode = activeInterviewFilter ? "case" : "project";

  // Persistir el filtro de entrevista en localStorage cuando cambia
  useEffect(() => {
    try {
      if (activeInterviewFilter) {
        localStorage.setItem(`${INTERVIEW_SCOPE_KEY}-${project}`, activeInterviewFilter);
      } else {
        localStorage.removeItem(`${INTERVIEW_SCOPE_KEY}-${project}`);
      }
    } catch {
      // localStorage no disponible
    }
  }, [activeInterviewFilter, project]);

  // Permite que otras vistas (p.ej. Inicio/Panorama) sugieran una entrevista.
  // No pisa la selección del usuario si ya eligió una.
  useEffect(() => {
    const next = (initialArchivo || "").trim();
    if (!next) return;
    setActiveInterviewFilter((prev) => (prev ? prev : next));
  }, [initialArchivo]);

  // Guided v1: siguiente fragmento recomendado + logging de feedback
  const [guidedLoading, setGuidedLoading] = useState(false);
  const [guidedError, setGuidedError] = useState<string | null>(null);
  const [guidedNext, setGuidedNext] = useState<CodingNextResponse | null>(null);
  const [guidedSelectedSuggestion, setGuidedSelectedSuggestion] = useState<string>("");
  const [guidedFinalCode, setGuidedFinalCode] = useState<string>("");
  const [guidedBusy, setGuidedBusy] = useState<string | null>(null);
  const [guidedExcludedIds, setGuidedExcludedIds] = useState<string[]>([]);
  const [guidedStrategy, setGuidedStrategy] = useState<"recent" | "oldest" | "random">("recent");

  const [assignFragmentId, setAssignFragmentId] = useState("");
  const [assignCodigo, setAssignCodigo] = useState("");
  const [assignFuente, setAssignFuente] = useState("");
  const [assignCita, setAssignCita] = useState("");
  const [assignBusy, setAssignBusy] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [assignInfo, setAssignInfo] = useState<string | null>(null); // Mensaje informativo (no error)
  const [assignResult, setAssignResult] = useState<CodingAssignPayload | null>(null);

  const [suggestFragmentId, setSuggestFragmentId] = useState("");
  const [suggestTopK, setSuggestTopK] = useState(5);
  const [suggestArchivo, setSuggestArchivo] = useState("");
  const [suggestArea, setSuggestArea] = useState("");
  const [suggestActor, setSuggestActor] = useState("");
  const [suggestLluvia, setSuggestLluvia] = useState<string>("any");
  const [suggestIncludeCoded, setSuggestIncludeCoded] = useState(false);
  const [suggestInterviewFilter, setSuggestInterviewFilter] = useState<string>(""); // Filtro de entrevista para sugerencias
  const [suggestBusy, setSuggestBusy] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<CodingSuggestion[]>([]);

  // Runner: automatiza el loop de sugerencias (seed-loop)
  const [suggestRunnerSteps, setSuggestRunnerSteps] = useState<number>(6);
  const [suggestRunnerLoading, setSuggestRunnerLoading] = useState(false);
  const [suggestRunnerError, setSuggestRunnerError] = useState<string | null>(null);
  const [suggestRunnerTask, setSuggestRunnerTask] = useState<CodingSuggestRunnerStatusResponse | null>(null);
  const [suggestRunnerResult, setSuggestRunnerResult] = useState<CodingSuggestRunnerResultResponse | null>(null);
  const [suggestRunnerPendingCount, setSuggestRunnerPendingCount] = useState<number | null>(null);
  const suggestRunnerIntervalRef = useRef<number | null>(null);
  const [samples, setSamples] = useState<FragmentSample[]>([]);
  const [samplesLoading, setSamplesLoading] = useState(false);
  const [samplesError, setSamplesError] = useState<string | null>(null);
  const [samplesLoaded, setSamplesLoaded] = useState(false);

  const [interviews, setInterviews] = useState<InterviewSummary[]>([]);
  const [interviewsLoading, setInterviewsLoading] = useState(false);
  const [interviewsError, setInterviewsError] = useState<string | null>(null);
  const [selectedInterview, setSelectedInterview] = useState<InterviewSummary | null>(null);
  const [interviewFragments, setInterviewFragments] = useState<FragmentSample[]>([]);
  const [interviewFragmentsLoading, setInterviewFragmentsLoading] = useState(false);
  const [interviewFragmentsError, setInterviewFragmentsError] = useState<string | null>(null);

  // Persisted memos from runner_semantic (disk), independent from task state
  const [runnerSemanticMemos, setRunnerSemanticMemos] = useState<Array<{ filename?: string; rel?: string }>>([]);
  const [runnerSemanticMemosLoading, setRunnerSemanticMemosLoading] = useState(false);
  const [runnerSemanticMemosError, setRunnerSemanticMemosError] = useState<string | null>(null);

  const [codes, setCodes] = useState<CodeSummary[]>([]);
  const [codesLoading, setCodesLoading] = useState(false);
  const [codesError, setCodesError] = useState<string | null>(null);
  const [codesArchivoFilter, setCodesArchivoFilter] = useState<string>("");

  const [stats, setStats] = useState<CodingStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState<string | null>(null);

  const [citationsCodigo, setCitationsCodigo] = useState("");
  const [citationsBusy, setCitationsBusy] = useState(false);
  const [citationsError, setCitationsError] = useState<string | null>(null);
  const [citations, setCitations] = useState<CodingCitationsResponse["citations"]>([]);
  const [analyzeBusy, setAnalyzeBusy] = useState<string | null>(null);
  const [unassignBusy, setUnassignBusy] = useState<string | null>(null);  // fragmento_id siendo desvinculado
  const [contextModalFragmentId, setContextModalFragmentId] = useState<string | null>(null);  // ID para modal de contexto

  // Estado para mostrar fragmentos con el código seleccionado (desde "Usar en asignación")
  const [selectedCodeContext, setSelectedCodeContext] = useState<string | null>(null);
  const [codeContextCitations, setCodeContextCitations] = useState<CodingCitationsResponse["citations"]>([]);
  const [codeContextLoading, setCodeContextLoading] = useState(false);

  // Sprint 17: Selección múltiple y Sugerencia de Acción IA
  const [selectedSuggestionIds, setSelectedSuggestionIds] = useState<Set<string>>(new Set());
  const [showActionSuggestion, setShowActionSuggestion] = useState(false);
  const [actionSuggestionCode, setActionSuggestionCode] = useState("");
  const [actionSuggestionMemo, setActionSuggestionMemo] = useState("");
  const [actionSuggestionConfidence, setActionSuggestionConfidence] = useState<"alta" | "media" | "baja" | "ninguna">("ninguna");
  const [actionSuggestionBusy, setActionSuggestionBusy] = useState(false);
  const [batchSubmitBusy, setBatchSubmitBusy] = useState(false);
  const [saveMemoLoading, setSaveMemoLoading] = useState(false);

  const assignSectionRef = useRef<HTMLDivElement | null>(null);
  const suggestSectionRef = useRef<HTMLDivElement | null>(null);
  const citationsSectionRef = useRef<HTMLDivElement | null>(null);
  const assignCodeInputRef = useRef<HTMLInputElement | null>(null);
  const citationsInputRef = useRef<HTMLInputElement | null>(null);
  const suggestFragmentInputRef = useRef<HTMLInputElement | null>(null);

  const lluviaValue = useMemo(() => {
    if (suggestLluvia === "true") {
      return true;
    }
    if (suggestLluvia === "false") {
      return false;
    }
    return null;
  }, [suggestLluvia]);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    setStatsError(null);
    try {
      const data = await apiFetchJson<CodingStats & FetchError>(
        `/api/coding/stats?project=${encodeURIComponent(project)}`
      );
      if (data.error) {
        throw new Error(data.error || "No se pudieron recuperar los indicadores.");
      }
      setStats(data);
    } catch (error) {
      setStats(null);
      setStatsError(error instanceof Error ? error.message : "Error desconocido");
    } finally {
      setStatsLoading(false);
    }
  }, [project]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  const loadInterviews = useCallback(async () => {
    setInterviewsLoading(true);
    setInterviewsError(null);
    try {
      const data = await apiFetchJson<InterviewSummaryResponse & FetchError>(
        `/api/interviews?project=${encodeURIComponent(project)}&limit=25`
      );
      if (data.error) {
        throw new Error(data.error || "No se pudieron recuperar entrevistas.");
      }
      const rawEntries = Array.isArray(data)
        ? data
        : Array.isArray((data as InterviewSummaryResponse).interviews)
          ? (data as InterviewSummaryResponse).interviews
          : [];
      const normalized = rawEntries.map((entry: any) => ({
        archivo: entry.archivo ?? entry.filename ?? String(entry.id ?? "sin_archivo"),
        fragmentos: entry.fragmentos ?? entry.segments_count ?? 0,
        actor_principal: entry.actor_principal ?? null,
        area_tematica: entry.area_tematica ?? null,
        actualizado: entry.actualizado ?? entry.updated_at ?? null,
      }));
      setInterviews(normalized);
    } catch (error) {
      setInterviews([]);
      setInterviewsError(error instanceof Error ? error.message : "Error desconocido");
    } finally {
      setInterviewsLoading(false);
    }
  }, [project]);

  const loadGuidedNext = useCallback(async () => {
    setGuidedLoading(true);
    setGuidedError(null);
    try {
      const data = await getCodingNext({
        project,
        // Etapa 3: si hay entrevista activa, la recomendación debe limitarse a esa entrevista.
        archivo: activeInterviewFilter || undefined,
        strategy: guidedStrategy,
        exclude_fragment_id: guidedExcludedIds,
      });
      setGuidedNext(data);

      if (data.found && data.fragmento) {
        const nextFragmentId = String(data.fragmento.fragmento_id || "");
        const nextArchivo = String(data.fragmento.archivo || "");

        if (nextFragmentId) {
          setAssignFragmentId(nextFragmentId);
          setSuggestFragmentId(nextFragmentId);
        }
        if (nextArchivo) {
          setActiveInterviewFilter(nextArchivo);
        }

        const firstSuggested = Array.isArray(data.suggested_codes) && data.suggested_codes.length
          ? String(data.suggested_codes[0]?.codigo || "")
          : "";
        setGuidedSelectedSuggestion(firstSuggested);
        setGuidedFinalCode(firstSuggested);
      } else {
        setGuidedSelectedSuggestion("");
        setGuidedFinalCode("");
      }
    } catch (error) {
      setGuidedNext(null);
      setGuidedError(error instanceof Error ? error.message : "Error cargando recomendación");
    } finally {
      setGuidedLoading(false);
    }
  }, [project, activeInterviewFilter, guidedStrategy, guidedExcludedIds]);

  // Si el usuario cambia de entrevista o de estrategia, reiniciamos exclusiones para evitar filtros “fantasma”.
  useEffect(() => {
    setGuidedExcludedIds([]);
  }, [activeInterviewFilter, guidedStrategy]);

  useEffect(() => {
    if (activeTab === "guided") {
      void loadGuidedNext();
    }
  }, [activeTab, loadGuidedNext, refreshKey]);

  const loadCodes = useCallback(async () => {
    setCodesLoading(true);
    setCodesError(null);
    try {
      let url = `/api/coding/codes?project=${encodeURIComponent(project)}&limit=50`;
      if (codesArchivoFilter) {
        url += `&archivo=${encodeURIComponent(codesArchivoFilter)}`;
      }
      const data = await apiFetchJson<CodeSummaryResponse & FetchError>(url);
      if (data.error) {
        throw new Error(data.error || "No se pudieron recuperar códigos.");
      }
      setCodes(Array.isArray(data.codes) ? data.codes : []);
    } catch (error) {
      setCodes([]);
      setCodesError(error instanceof Error ? error.message : "Error desconocido");
    } finally {
      setCodesLoading(false);
    }
  }, [project, codesArchivoFilter]);

  const assignCodeDirect = useCallback(
    async (fragmentId: string, codigo: string, cita: string, fuente?: string) => {
      const fragmentInput = fragmentId.trim();
      const codigoInput = codigo.trim();
      const citaInput = cita.trim();
      const fuenteInput = (fuente || "").trim();

      if (!fragmentInput || !codigoInput || !citaInput) {
        throw new Error("Debes completar fragmento, codigo y cita.");
      }

      const data = await apiFetchJson<CodingAssignPayload & FetchError>("/api/coding/assign", {
        method: "POST",
        body: JSON.stringify({
          project,
          fragment_id: fragmentInput,
          codigo: codigoInput,
          cita: citaInput,
          fuente: fuenteInput || undefined,
        }),
      });

      if (data.error) {
        throw new Error(data.error || "No se pudo registrar la codificacion.");
      }

      void loadStats();
      void loadCodes();
      return data;
    },
    [project, loadStats, loadCodes]
  );

  const handleGuidedOpenInAssign = useCallback(() => {
    if (!guidedNext?.found || !guidedNext.fragmento) return;
    setAssignFragmentId(guidedNext.fragmento.fragmento_id);
    setAssignFuente(guidedNext.fragmento.archivo || "");
    setAssignCita((guidedNext.fragmento.fragmento || "").slice(0, 300));
    if (guidedFinalCode.trim()) {
      setAssignCodigo(guidedFinalCode.trim());
    }
    setAssignError(null);
    setAssignResult(null);
    setActiveTab("assign");
    window.requestAnimationFrame(() => {
      assignSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      assignCodeInputRef.current?.focus({ preventScroll: true });
    });
  }, [guidedNext, guidedFinalCode]);

  const handleGuidedReject = useCallback(async () => {
    if (!guidedNext?.found || !guidedNext.fragmento) return;
    setGuidedBusy("reject");
    setGuidedError(null);
    try {
      const rejectedId = String(guidedNext.fragmento.fragmento_id || "");
      if (rejectedId) {
        setGuidedExcludedIds((prev) => {
          const next = [...prev, rejectedId];
          // cap to avoid unbounded query strings
          return next.slice(Math.max(0, next.length - 50));
        });
      }
      await postCodingFeedback({
        project,
        fragmento_id: guidedNext.fragmento.fragmento_id,
        action: "reject",
        suggested_code: guidedSelectedSuggestion || null,
        final_code: null,
        meta: { ui: "guided_v1" },
      });
      void loadGuidedNext();
    } catch (error) {
      setGuidedError(error instanceof Error ? error.message : "Error registrando feedback");
    } finally {
      setGuidedBusy(null);
    }
  }, [guidedNext, guidedSelectedSuggestion, loadGuidedNext, project]);

  const handleGuidedAccept = useCallback(async () => {
    if (!guidedNext?.found || !guidedNext.fragmento) return;

    const fragmentId = guidedNext.fragmento.fragmento_id;
    const suggested = guidedSelectedSuggestion.trim();
    const finalCode = guidedFinalCode.trim();
    const chosen = finalCode || suggested;
    if (!chosen) {
      setGuidedError("Selecciona o escribe un código para aceptar.");
      return;
    }

    const cita = (guidedNext.fragmento.fragmento || "").trim();
    const fuente = guidedNext.fragmento.archivo || "";

    setGuidedBusy("accept");
    setGuidedError(null);
    try {
      await assignCodeDirect(fragmentId, chosen, cita.slice(0, 300), fuente);

      const action = suggested && finalCode && suggested !== finalCode ? "edit" : "accept";
      await postCodingFeedback({
        project,
        fragmento_id: fragmentId,
        action,
        suggested_code: suggested || null,
        final_code: chosen,
        meta: { ui: "guided_v1" },
      });

      setAssignInfo("✅ Código registrado desde flujo guiado.");
      // Reset exclusions on successful accept to avoid filtering too aggressively.
      setGuidedExcludedIds([]);
      void loadGuidedNext();
    } catch (error) {
      setGuidedError(error instanceof Error ? error.message : "Error aceptando recomendación");
    } finally {
      setGuidedBusy(null);
    }
  }, [assignCodeDirect, guidedFinalCode, guidedNext, guidedSelectedSuggestion, loadGuidedNext, project]);

  // Atajos de teclado (solo en flujo guiado y sin interferir con inputs).
  useEffect(() => {
    if (activeTab !== "guided") return;

    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = (target?.tagName || "").toLowerCase();
      const isEditable =
        tag === "input" || tag === "textarea" || tag === "select" || (target as any)?.isContentEditable;
      if (isEditable) return;

      const key = (e.key || "").toLowerCase();
      if (key === "enter") {
        e.preventDefault();
        void handleGuidedAccept();
        return;
      }
      if (key === "r") {
        e.preventDefault();
        void handleGuidedReject();
        return;
      }
      if (key === "a") {
        e.preventDefault();
        handleGuidedOpenInAssign();
        return;
      }
      if (key === "n") {
        e.preventDefault();
        void loadGuidedNext();
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeTab, handleGuidedAccept, handleGuidedReject, handleGuidedOpenInAssign, loadGuidedNext]);

  const loadInterviewFragments = useCallback(
    async (archivo: string) => {
      setInterviewFragmentsLoading(true);
      setInterviewFragmentsError(null);
      try {
        const data = await apiFetchJson<FragmentListResponse & FetchError>(
          `/api/coding/fragments?project=${encodeURIComponent(project)}&archivo=${encodeURIComponent(
            archivo
          )}&limit=30`
        );
        if (data.error) {
          throw new Error(data.error || "No se pudieron obtener los fragmentos del archivo.");
        }
        const fragments = Array.isArray(data.fragments) ? data.fragments : [];
        setInterviewFragments(fragments);
        if (fragments.length) {
          setSuggestFragmentId(fragments[0].fragmento_id);
        }
      } catch (error) {
        setInterviewFragments([]);
        setInterviewFragmentsError(error instanceof Error ? error.message : "Error desconocido");
      } finally {
        setInterviewFragmentsLoading(false);
      }
    },
    [project]
  );

  const loadRunnerSemanticMemos = useCallback(
    async (archivo: string) => {
      if (!archivo) {
        setRunnerSemanticMemos([]);
        return;
      }
      setRunnerSemanticMemosLoading(true);
      setRunnerSemanticMemosError(null);
      try {
        const data = await apiFetchJson<{ memos?: Array<{ filename?: string; rel?: string }>; error?: string }>(
          `/api/coding/suggest/runner/memos?project=${encodeURIComponent(project)}&archivo=${encodeURIComponent(archivo)}&limit=25`
        );
        if ((data as any).error) {
          throw new Error((data as any).error);
        }
        setRunnerSemanticMemos(Array.isArray((data as any).memos) ? (data as any).memos : []);
      } catch (error) {
        setRunnerSemanticMemos([]);
        setRunnerSemanticMemosError(error instanceof Error ? error.message : "Error desconocido");
      } finally {
        setRunnerSemanticMemosLoading(false);
      }
    },
    [project]
  );

  useEffect(() => {
    void loadInterviews();
    void loadCodes();
  }, [loadInterviews, loadCodes]);

  // Reload data when refreshKey changes (triggered by external events like ingestion)
  useEffect(() => {
    if (refreshKey !== undefined && refreshKey > 0) {
      void loadInterviews();
      void loadCodes();
      void loadStats();
      setSamplesLoaded(false);
    }
  }, [refreshKey, loadInterviews, loadCodes, loadStats]);

  const fetchCitations = useCallback(
    async (codigo: string) => {
      setCitationsBusy(true);
      setCitationsError(null);
      setCitations([]);
      try {
        const data = await apiFetchJson<CodingCitationsResponse & FetchError>(
          `/api/coding/citations?project=${encodeURIComponent(project)}&codigo=${encodeURIComponent(
            codigo
          )}`
        );
        if (data.error) {
          throw new Error(data.error || "No fue posible recuperar las citas.");
        }
        setCitations(data.citations ?? []);
      } catch (error) {
        setCitationsError(error instanceof Error ? error.message : "Error desconocido");
      } finally {
        setCitationsBusy(false);
      }
    },
    [project]
  );

  const loadSamples = useCallback(async () => {
    setSamplesLoading(true);
    setSamplesError(null);
    try {
      let url = `/api/fragments/sample?project=${encodeURIComponent(project)}&limit=8`;
      // Respetar el filtro de entrevista si está activo
      if (suggestInterviewFilter) {
        url += `&archivo=${encodeURIComponent(suggestInterviewFilter)}`;
      }
      const data = await apiFetchJson<FragmentSampleResponse & FetchError>(url);
      if (data.error) {
        throw new Error(data.error || "No se pudieron recuperar fragmentos.");
      }
      setSamples(Array.isArray(data.samples) ? data.samples : []);
    } catch (error) {
      setSamples([]);
      setSamplesError(error instanceof Error ? error.message : "Error desconocido");
    } finally {
      setSamplesLoading(false);
      setSamplesLoaded(true);
    }
  }, [project, suggestInterviewFilter]);

  useEffect(() => {
    if (activeTab === "suggest" && !samplesLoaded && !samplesLoading) {
      void loadSamples();
    }
  }, [activeTab, samplesLoaded, samplesLoading, loadSamples]);

  // Recargar fragmentos cuando cambia el filtro de entrevista
  useEffect(() => {
    if (activeTab === "suggest") {
      setSamplesLoaded(false);
      void loadSamples();
    }
  }, [suggestInterviewFilter]);

  const handleRefreshSamples = () => {
    setSamplesLoaded(false);
    void loadSamples();
  };

  const handleRefreshInterviews = () => {
    void loadInterviews();
    if (selectedInterview) {
      void loadInterviewFragments(selectedInterview.archivo);
    }
  };

  const handleRefreshCodes = () => {
    void loadCodes();
  };

  const handleRefreshInterviewFragments = () => {
    if (selectedInterview) {
      void loadInterviewFragments(selectedInterview.archivo);
    }
  };

  const handleUseInterview = (interview: InterviewSummary) => {
    setSelectedInterview(interview);
    setInterviewFragments([]);
    setInterviewFragmentsError(null);
    setSuggestArchivo(interview.archivo);
    setActiveTab("suggest");
    setSuggestError(null);
    void loadInterviewFragments(interview.archivo);
    void loadRunnerSemanticMemos(interview.archivo);
  };

  const handleUseCode = async (entry: CodeSummary) => {
    setAssignCodigo(entry.codigo);
    setAssignResult(null);
    setAssignError(null);

    // Guardar el código seleccionado para mostrar contexto
    setSelectedCodeContext(entry.codigo);
    setCodeContextLoading(true);
    setCodeContextCitations([]);

    // Cargar fragmentos que ya tienen este código asignado
    try {
      const data = await apiFetchJson<CodingCitationsResponse & FetchError>(
        `/api/coding/citations?project=${encodeURIComponent(project)}&codigo=${encodeURIComponent(entry.codigo)}`
      );
      if (!data.error) {
        setCodeContextCitations(data.citations ?? []);
      }
    } catch {
      // Si falla, simplemente no mostramos el contexto
    } finally {
      setCodeContextLoading(false);
    }

    // Cambiar a pestaña de sugerencias para que seleccione un fragmento
    setAssignInfo(`✨ Código "${entry.codigo}" seleccionado (${entry.count} usos). Selecciona un fragmento de la lista para asignar este código.`);
    setActiveTab("suggest");

    // Scroll al inicio de la sección de fragmentos
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  };

  const handleInspectCode = (entry: CodeSummary) => {
    setCitationsCodigo(entry.codigo);
    setActiveTab("citations");
    setCitationsError(null);
    void fetchCitations(entry.codigo);
    window.requestAnimationFrame(() => {
      citationsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      citationsInputRef.current?.focus({ preventScroll: true });
    });
  };

  // Handler para aplicar una cita existente al formulario de asignación
  const handleApplyCitation = (citation: CodingCitationsResponse["citations"][0]) => {
    setAssignFragmentId(citation.fragmento_id);
    setAssignCodigo(citationsCodigo); // Usar el código actual de la consulta
    setAssignCita(citation.cita || "");
    setAssignFuente(citation.fuente || "");
    setAssignError(null);
    setAssignResult(null);
    setActiveTab("assign");
    window.requestAnimationFrame(() => {
      assignSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  // Handler para desvincular un código de un fragmento
  const handleUnassignCode = async (citation: CodingCitationsResponse["citations"][0]) => {
    const codigoToUnassign = citationsCodigo;
    if (!codigoToUnassign) {
      return;
    }

    const confirmed = window.confirm(
      `¿Desvincular el código "${codigoToUnassign}" del fragmento ${citation.fragmento_id.slice(0, 15)}...?\n\nEsta acción elimina la relación pero el fragmento y otros códigos asociados permanecerán intactos.`
    );
    if (!confirmed) return;

    setUnassignBusy(citation.fragmento_id);
    try {
      const response = await apiFetch("/api/coding/unassign", {
        method: "DELETE",
        body: JSON.stringify({
          project,
          fragment_id: citation.fragmento_id,
          codigo: codigoToUnassign,
        }),
      });
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Error al desvincular");
      }
      // Refrescar la lista de citas y códigos
      await fetchCitations(codigoToUnassign);
      void loadCodes();
      void loadStats();
    } catch (error) {
      setCitationsError(error instanceof Error ? error.message : "Error desconocido");
    } finally {
      setUnassignBusy(null);
    }
  };

  const handleSelectSample = (sample: FragmentSample) => {
    // Auto-completar todos los campos del formulario de asignación
    setSuggestFragmentId(sample.fragmento_id);
    setAssignFragmentId(sample.fragmento_id);
    setAssignError(null);
    setAssignInfo(null);

    // Auto-completar Fuente desde nombre de archivo (sin extensión)
    if (sample.archivo) {
      setSuggestArchivo(sample.archivo);
      // Generar fuente descriptiva desde el nombre del archivo
      const baseName = sample.archivo.replace(/\.(docx?|txt|pdf)$/i, "");
      setAssignFuente(baseName.replace(/_/g, " "));
    }

    // Auto-completar Cita con el texto del fragmento (truncado a 300 chars)
    if (sample.fragmento) {
      const citaPreview = sample.fragmento.slice(0, 300);
      setAssignCita(citaPreview + (sample.fragmento.length > 300 ? "..." : ""));
    }

    setSuggestError(null);

    // Cambiar a pestaña de sugerencias semánticas y hacer scroll
    setActiveTab("suggest");
    window.requestAnimationFrame(() => {
      suggestSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      suggestFragmentInputRef.current?.focus({ preventScroll: true });
    });
  };

  // Handler para agregar una sugerencia semántica al código actual
  const handleAddSuggestionToCode = (suggestion: CodingSuggestion) => {
    // Usar el fragmento sugerido como el nuevo fragmento a codificar
    setAssignFragmentId(suggestion.fragmento_id);
    // Mantener el código actual (el que el usuario ya tiene escrito)
    // Si no hay código, usar el texto del fragmento como pista
    setAssignCita((suggestion.fragmento || "").slice(0, 300));
    setAssignFuente(suggestion.archivo || "");
    setAssignError(null);
    setAssignResult(null);
    setActiveTab("assign");
    window.requestAnimationFrame(() => {
      assignSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      assignCodeInputRef.current?.focus({ preventScroll: true });
    });
  };

  const handleAssign = async (event: React.FormEvent) => {
    event.preventDefault();
    const fragmentInput = assignFragmentId.trim();
    const codigoInput = assignCodigo.trim();
    const citaInput = assignCita.trim();
    const fuenteInput = assignFuente.trim();
    if (!fragmentInput || !codigoInput || !citaInput) {
      setAssignError("Debes completar fragmento, codigo y cita.");
      return;
    }
    if (fragmentInput.toLowerCase().endsWith(".docx") || fragmentInput.toLowerCase().endsWith(".doc")) {
      setAssignError(
        "Ingresaste el nombre del archivo. Copia el fragmento_id (UUID) desde 'Fragmentos recientes' o la lista de la entrevista y vuelve a intentar."
      );
      return;
    }
    setAssignBusy(true);
    setAssignError(null);
    setAssignInfo(null);
    setAssignResult(null);
    try {
      const data = await apiFetchJson<CodingAssignPayload & FetchError>("/api/coding/assign", {
        method: "POST",
        body: JSON.stringify({
          project,
          fragment_id: fragmentInput,
          codigo: codigoInput,
          cita: citaInput,
          fuente: fuenteInput || undefined
        })
      });
      if (data.error) {
        throw new Error(data.error || "No se pudo registrar la codificacion.");
      }
      setAssignResult(data);
      setAssignFragmentId("");
      setAssignCodigo("");
      setAssignFuente("");
      setAssignCita("");
      void loadStats();
      void loadCodes();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Error desconocido";
      if (message.toLowerCase().includes("no existe en postgresql") || message.toLowerCase().includes("fragmento '")) {
        setAssignError(
          "No encontramos ese fragmento. Elige uno desde la entrevista seleccionada o 'Fragmentos recientes'; al presionar 'Usar fragmento' lo pegamos aquí automáticamente."
        );
      } else {
        setAssignError(message);
      }
    } finally {
      setAssignBusy(false);
    }
  };

  const handleSuggest = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!suggestFragmentId.trim()) {
      setSuggestError("Debes indicar el fragmento semilla.");
      return;
    }
    setSuggestBusy(true);
    setSuggestError(null);
    setSuggestions([]);
    try {
      const data = await apiFetchJson<CodingSuggestResponse & FetchError>("/api/coding/suggest", {
        method: "POST",
        body: JSON.stringify({
          project,
          fragment_id: suggestFragmentId.trim(),
          top_k: suggestTopK,
          archivo: suggestArchivo.trim() || undefined,
          area_tematica: suggestArea.trim() || undefined,
          actor_principal: suggestActor.trim() || undefined,
          requiere_protocolo_lluvia: lluviaValue,
          include_coded: suggestIncludeCoded
        })
      });
      if (data.error) {
        throw new Error(data.error || "No se pudieron obtener sugerencias.");
      }
      const resultSuggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
      setSuggestions(resultSuggestions);
      
      // E3-1.2: Log E3 suggest action for traceability
      try {
        await logDiscoveryNavigation({
          project,
          positivos: [],
          negativos: [],
          target_text: null,
          fragments_count: resultSuggestions.length,
          codigos_sugeridos: [],
          action_taken: "e3_suggest",
          seed_fragmento_id: suggestFragmentId.trim(),
          scope_archivo: activeInterviewFilter || undefined,
          top_k: suggestTopK,
          include_coded: suggestIncludeCoded,
        });
      } catch {
        // Non-blocking: log failure but don't interrupt user flow
        console.warn("E3 navigation log failed (non-blocking)");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Error desconocido";
      if (message.toLowerCase().includes("no existe en postgresql") || message.includes("Fragmento")) {
        setSuggestError(
          "No encontramos el fragmento ingresado. Selecciona una opción de la lista o confirma el identificador en PostgreSQL."
        );
      } else {
        setSuggestError(message);
      }
    } finally {
      setSuggestBusy(false);
    }
  };

  const clearSuggestRunnerInterval = useCallback(() => {
    if (suggestRunnerIntervalRef.current) {
      window.clearInterval(suggestRunnerIntervalRef.current);
      suggestRunnerIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearSuggestRunnerInterval();
    };
  }, [clearSuggestRunnerInterval]);

  const pollSuggestRunnerStatus = useCallback(async (taskId: string) => {
    try {
      // Sprint 31: Timeout de 60s para runner (en lugar de 30s default)
      const status = await apiFetchJson<CodingSuggestRunnerStatusResponse>(
        `/api/coding/suggest/runner/status/${taskId}`,
        {},
        undefined,
        60000  // 60s timeout for runner operations
      );
      setSuggestRunnerTask(status);

      if (status.status === "completed") {
        clearSuggestRunnerInterval();
        setSuggestRunnerLoading(false);
        setSuggestRunnerError(null);

        // Fetch final result once
        if (!suggestRunnerResult) {
          const result = await apiFetchJson<CodingSuggestRunnerResultResponse>(
            `/api/coding/suggest/runner/result/${taskId}`,
            {},
            undefined,
            60000  // 60s timeout for runner operations
          );
          setSuggestRunnerResult(result);
          setSuggestions(Array.isArray(result.suggestions) ? result.suggestions : []);
          setSelectedSuggestionIds(new Set());
          setShowActionSuggestion(false);

          // Refresh pending candidates count (real total)
          try {
            const pending = await apiFetchJson<{ project: string; pending_count: number }>(
              `/api/codes/candidates/pending_count?project=${encodeURIComponent(project)}`
            );
            setSuggestRunnerPendingCount(typeof pending.pending_count === "number" ? pending.pending_count : null);
          } catch {
            setSuggestRunnerPendingCount(null);
          }
        }
      } else if (status.status === "error") {
        clearSuggestRunnerInterval();
        setSuggestRunnerLoading(false);
        setSuggestRunnerError(status.message || "Error durante ejecución del runner");
      }
    } catch (err) {
      console.warn("Suggest runner poll failed:", err);
    }
  }, [clearSuggestRunnerInterval, suggestRunnerResult, project]);

  const handleRunSuggestRunner = useCallback(async () => {
    if (!project) {
      setSuggestRunnerError("Selecciona un proyecto primero");
      return;
    }
    if (!suggestFragmentId.trim()) {
      setSuggestRunnerError("Debes indicar el fragmento semilla");
      return;
    }

    setSuggestRunnerLoading(true);
    setSuggestRunnerError(null);
    setSuggestRunnerTask(null);
    setSuggestRunnerResult(null);
    setSuggestRunnerPendingCount(null);
    setSuggestError(null);
    clearSuggestRunnerInterval();

    try {
      const lluviaValue =
        suggestLluvia === "any" ? undefined : suggestLluvia === "true";

      const data = await apiFetchJson<CodingSuggestRunnerExecuteResponse>(
        "/api/coding/suggest/runner/execute",
        {
          method: "POST",
          body: JSON.stringify({
            project,
            seed_fragment_id: suggestFragmentId.trim(),
            steps: Math.max(1, Number(suggestRunnerSteps) || 1),
            top_k: suggestTopK,
            archivo: suggestArchivo.trim() || undefined,
            area_tematica: suggestArea.trim() || undefined,
            actor_principal: suggestActor.trim() || undefined,
            requiere_protocolo_lluvia: lluviaValue,
            include_coded: suggestIncludeCoded,
            strategy: "best-score",

            // Runner completo (v2)
            sweep_all_interviews: true,
            llm_suggest: true,
            llm_model: "chat",
            save_memos: true,
            submit_candidates: true,
          }),
        },
        undefined,
        60000  // 60s timeout for runner operations
      );

      await pollSuggestRunnerStatus(data.task_id);
      suggestRunnerIntervalRef.current = window.setInterval(() => pollSuggestRunnerStatus(data.task_id), 2000);
    } catch (err) {
      setSuggestRunnerError(err instanceof Error ? err.message : "Error iniciando runner");
      setSuggestRunnerLoading(false);
    }
  }, [
    project,
    suggestFragmentId,
    suggestRunnerSteps,
    suggestTopK,
    suggestArchivo,
    suggestArea,
    suggestActor,
    suggestLluvia,
    suggestIncludeCoded,
    clearSuggestRunnerInterval,
    pollSuggestRunnerStatus,
  ]);

  const handleResumeSuggestRunner = useCallback(async () => {
    if (!project) {
      setSuggestRunnerError("Selecciona un proyecto primero");
      return;
    }
    if (!suggestRunnerTask?.task_id) {
      setSuggestRunnerError("No hay una tarea previa para reanudar");
      return;
    }

    setSuggestRunnerLoading(true);
    setSuggestRunnerError(null);
    setSuggestRunnerResult(null);
    setSuggestRunnerPendingCount(null);
    clearSuggestRunnerInterval();

    try {
      const data = await apiFetchJson<CodingSuggestRunnerResumeResponse>(
        "/api/coding/suggest/runner/resume",
        {
          method: "POST",
          body: JSON.stringify({
            project,
            task_id: suggestRunnerTask.task_id,
          }),
        },
        undefined,
        60000  // 60s timeout for runner operations
      );

      await pollSuggestRunnerStatus(data.task_id);
      suggestRunnerIntervalRef.current = window.setInterval(() => pollSuggestRunnerStatus(data.task_id), 2000);
    } catch (err) {
      setSuggestRunnerError(err instanceof Error ? err.message : "Error reanudando runner");
      setSuggestRunnerLoading(false);
    }
  }, [project, suggestRunnerTask?.task_id, clearSuggestRunnerInterval, pollSuggestRunnerStatus]);

  const handleCitations = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!citationsCodigo.trim()) {
      setCitationsError("Debes ingresar el codigo a consultar.");
      return;
    }
    await fetchCitations(citationsCodigo.trim());
  };

  const handleAnalyze = async (archivo: string) => {
    if (!window.confirm(`¿Deseas ejecutar el análisis IA para ${archivo}? Esto puede tardar unos minutos.`)) {
      return;
    }
    setAnalyzeBusy(archivo);
    try {
      const data = await apiFetchJson<FetchError>("/api/analyze", {
        method: "POST",
        body: JSON.stringify({
          project,
          docx_path: archivo,
          persist: true
        })
      });
      if (data.error) {
        throw new Error(data.error || "Error en el análisis.");
      }
      void loadCodes();
    } catch (error) {
      alert(`Error: ${error instanceof Error ? error.message : "Error desconocido"}`);
    } finally {
      setAnalyzeBusy(null);
    }
  };

  // Sprint 17: Toggle selección de sugerencia
  const handleToggleSuggestionSelection = (fragmentId: string) => {
    setSelectedSuggestionIds(prev => {
      const next = new Set(prev);
      if (next.has(fragmentId)) {
        next.delete(fragmentId);
      } else {
        next.add(fragmentId);
      }
      return next;
    });
  };

  // Sprint 17: Seleccionar/deseleccionar todas las sugerencias
  const handleSelectAllSuggestions = () => {
    if (selectedSuggestionIds.size === suggestions.length) {
      setSelectedSuggestionIds(new Set());
    } else {
      setSelectedSuggestionIds(new Set(suggestions.map(s => s.fragmento_id)));
    }
  };

  // Sprint 17: Generar sugerencia de código IA
  const handleGenerateActionSuggestion = async () => {
    if (selectedSuggestionIds.size === 0) {
      setSuggestError("Selecciona al menos un fragmento para generar sugerencia.");
      return;
    }

    setActionSuggestionBusy(true);
    setSuggestError(null);

    try {
      const selectedFragments = suggestions.filter(s => selectedSuggestionIds.has(s.fragmento_id));

      const data = await apiFetchJson<{
        suggested_code?: string;
        memo?: string;
        confidence?: "alta" | "media" | "baja" | "ninguna";
        error?: string;
      }>("/api/coding/suggest-code", {
        method: "POST",
        body: JSON.stringify({
          project,
          fragments: selectedFragments,
          llm_model: "chat",
        }),
      });

      if (data.error) {
        throw new Error(data.error);
      }

      setActionSuggestionCode(data.suggested_code || "");
      setActionSuggestionMemo(data.memo || "");
      setActionSuggestionConfidence(data.confidence || "ninguna");
      setShowActionSuggestion(true);
    } catch (error) {
      setSuggestError(error instanceof Error ? error.message : "Error generando sugerencia");
    } finally {
      setActionSuggestionBusy(false);
    }
  };

  // Sprint 17: Enviar selección a bandeja de candidatos
  const handleSubmitToCandidates = async () => {
    if (!actionSuggestionCode.trim()) {
      setSuggestError("El código es requerido.");
      return;
    }

    setBatchSubmitBusy(true);
    setSuggestError(null);

    try {
      const selectedFragments = suggestions.filter(s => selectedSuggestionIds.has(s.fragmento_id));

      const data = await apiFetchJson<{ submitted?: number; error?: string }>("/api/codes/candidates/batch", {
        method: "POST",
        body: JSON.stringify({
          project,
          codigo: actionSuggestionCode.trim(),
          memo: actionSuggestionMemo.trim() || undefined,
          fragments: selectedFragments.map(s => ({
            fragmento_id: s.fragmento_id,
            archivo: s.archivo || "",
            cita: (s.fragmento || "").slice(0, 300),
            score: s.score,
          })),
        }),
      });

      if (data.error) {
        throw new Error(data.error);
      }

      // E3-1.2: Log E3 send_candidates action for traceability
      try {
        await logDiscoveryNavigation({
          project,
          positivos: [actionSuggestionCode.trim()],
          negativos: [],
          target_text: null,
          fragments_count: data.submitted || selectedFragments.length,
          codigos_sugeridos: [actionSuggestionCode.trim()],
          ai_synthesis: actionSuggestionMemo.trim() || undefined,
          action_taken: "e3_send_candidates",
          seed_fragmento_id: suggestFragmentId.trim() || undefined,
          scope_archivo: activeInterviewFilter || undefined,
        });
      } catch {
        // Non-blocking
        console.warn("E3 navigation log failed (non-blocking)");
      }

      // Limpiar estado y mostrar éxito
      setShowActionSuggestion(false);
      setSelectedSuggestionIds(new Set());
      setActionSuggestionCode("");
      setActionSuggestionMemo("");
      setAssignInfo(`✅ ${data.submitted} fragmentos enviados a la bandeja de candidatos con código "${actionSuggestionCode}".`);

      // Refrescar datos
      void loadCodes();
      void loadStats();
    } catch (error) {
      setSuggestError(error instanceof Error ? error.message : "Error enviando a bandeja");
    } finally {
      setBatchSubmitBusy(false);
    }
  };

  // Sprint 17: Cancelar sugerencia de acción
  const handleCancelActionSuggestion = () => {
    setShowActionSuggestion(false);
    setActionSuggestionCode("");
    setActionSuggestionMemo("");
  };

  // Sprint 21: Guardar memo IA independientemente
  const handleSaveMemo = async () => {
    if (!actionSuggestionMemo.trim()) {
      return;
    }

    setSaveMemoLoading(true);
    try {
      const selectedFragments = suggestions.filter(s => selectedSuggestionIds.has(s.fragmento_id));

      const result = await apiFetchJson<{ status: string; path?: string; filename?: string }>("/api/discovery/save_memo", {
        method: "POST",
        body: JSON.stringify({
          positive_texts: [actionSuggestionCode || "Sugerencia IA"],
          fragments: selectedFragments.map(s => ({
            fragmento_id: s.fragmento_id,
            archivo: s.archivo || "",
            fragmento: s.fragmento || "",
            score: s.score,
          })),
          project,
          ai_synthesis: actionSuggestionMemo,
          memo_title: `Memo IA: ${actionSuggestionCode || "Sin código"}`,
        }),
      });

      // Show success message visible to user
      const filename = result.filename || "memo.md";
      alert(`✅ Memo guardado exitosamente!\n\nArchivo: ${filename}\nUbicación: notes/${project}/`);
      setAssignInfo("📝 Memo guardado exitosamente.");
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : "Error guardando memo";
      alert(`❌ Error guardando memo:\n${errorMsg}`);
      setSuggestError(errorMsg);
    } finally {
      setSaveMemoLoading(false);
    }
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case "guided": {
        const fragment = guidedNext && guidedNext.found && guidedNext.fragmento ? guidedNext.fragmento : null;
        const suggestedCodes = guidedNext && Array.isArray(guidedNext.suggested_codes) ? guidedNext.suggested_codes : [];
        const reasons = guidedNext && Array.isArray(guidedNext.reasons) ? guidedNext.reasons : [];
        const pendingTotal = guidedNext && typeof guidedNext.pending_total === "number" ? guidedNext.pending_total : null;
        const pendingInArchivo = guidedNext && typeof guidedNext.pending_in_archivo === "number" ? guidedNext.pending_in_archivo : null;

        return (
          <div className="coding__panel">
            <div className="coding__panel-header" style={{ marginBottom: 0 }}>
              <h2>🧭 Siguiente recomendado</h2>
              <p>Flujo: toma un fragmento (idealmente de la entrevista activa), decide un código rápido y registramos feedback para aprender.</p>
            </div>

            <div className="coding__toolbar" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <button type="button" className="primary-action" onClick={() => void loadGuidedNext()} disabled={guidedLoading || !!guidedBusy}>
                {guidedLoading ? "Cargando..." : "🔄 Siguiente recomendado"}
              </button>

              <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ opacity: 0.85 }}>Estrategia:</span>
                <select
                  value={guidedStrategy}
                  onChange={(e) => setGuidedStrategy(e.target.value as any)}
                  disabled={guidedLoading || !!guidedBusy}
                >
                  <option value="recent">Recientes</option>
                  <option value="oldest">Antiguas</option>
                  <option value="random">Aleatoria</option>
                </select>
              </label>

              {guidedExcludedIds.length > 0 && (
                <button type="button" onClick={() => setGuidedExcludedIds([])} disabled={guidedLoading || !!guidedBusy}>
                  🧹 Limpiar rechazados ({guidedExcludedIds.length})
                </button>
              )}

              <button type="button" onClick={handleGuidedOpenInAssign} disabled={!fragment || !!guidedBusy}>
                📝 Abrir en Asignar
              </button>
            </div>

            <div style={{ marginTop: 8, opacity: 0.9 }}>
              <strong>Entrevista activa:</strong> {activeInterviewFilter ? activeInterviewFilter : "(todas)"}
              {!activeInterviewFilter ? (
                <span style={{ marginLeft: 8 }}>
                  · Recomendación puede mezclar entrevistas (mejor elegir una para Etapa 3).
                </span>
              ) : null}
            </div>

            {(pendingTotal !== null || pendingInArchivo !== null) && (
              <div style={{ marginTop: 6, opacity: 0.9 }}>
                <strong>Pendientes:</strong>{" "}
                {pendingInArchivo !== null ? (
                  <span>
                    en esta entrevista = {pendingInArchivo}
                    {pendingTotal !== null ? <span style={{ marginLeft: 8 }}>· total = {pendingTotal}</span> : null}
                  </span>
                ) : (
                  <span>{pendingTotal !== null ? `total = ${pendingTotal}` : "(sin datos)"}</span>
                )}
              </div>
            )}

            {guidedError && <div className="app__error">{guidedError}</div>}

            {!guidedLoading && !fragment && (
              <div className="critical-info">
                No hay fragmentos pendientes (o no se pudo sugerir). Revisa que existan fragmentos en PostgreSQL y que haya avance de codificación.
              </div>
            )}

            {fragment && (
              <div style={{ display: "grid", gap: 12 }}>
                <div className="coding__card">
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                    <div>
                      <strong>Archivo:</strong> {fragment.archivo}
                      {typeof fragment.par_idx === "number" ? (
                        <span style={{ marginLeft: 8, opacity: 0.85 }}>
                          <strong>Par:</strong> {fragment.par_idx}
                        </span>
                      ) : null}
                    </div>
                    <div className="technical-detail">
                      <strong>fragmento_id:</strong> {fragment.fragmento_id}
                    </div>
                  </div>

                  <div style={{ marginTop: 10, whiteSpace: "pre-wrap" }}>
                    {fragment.fragmento}
                  </div>

                  <details style={{ marginTop: 10 }}>
                    <summary className="technical-detail">Modo avanzado (detalles)</summary>
                    <div className="technical-detail" style={{ marginTop: 8, display: "grid", gap: 8 }}>
                      <div>
                        <strong>Atajos:</strong> Enter = aceptar · R = rechazar · N = siguiente · A = abrir en asignar
                      </div>
                      {reasons.length > 0 ? (
                        <div>
                          <strong>Razones:</strong>
                          <ul style={{ marginTop: 6 }}>
                            {reasons.map((r, idx) => (
                              <li key={`${idx}-${r}`}>{r}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>
                  </details>
                </div>

                <div className="coding__card">
                  <div style={{ display: "grid", gap: 10 }}>
                    <div>
                      <strong>Decisión</strong>
                      <div className="technical-detail" style={{ marginTop: 4 }}>
                        Selecciona un código sugerido o escribe uno, luego acepta o rechaza.
                      </div>
                    </div>

                    {suggestedCodes.length > 0 ? (
                      <div style={{ display: "grid", gap: 6 }}>
                        {suggestedCodes.slice(0, 8).map((s) => (
                          <label key={s.codigo} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <input
                              type="radio"
                              name="guided-suggested-code"
                              value={s.codigo}
                              checked={guidedSelectedSuggestion === s.codigo}
                              onChange={() => {
                                setGuidedSelectedSuggestion(s.codigo);
                                setGuidedFinalCode(s.codigo);
                              }}
                              disabled={!!guidedBusy}
                            />
                            <span style={{ fontWeight: 600 }}>{s.codigo}</span>
                            {typeof s.citas === "number" ? (
                              <span className="technical-detail">(citas: {s.citas})</span>
                            ) : null}
                            {s.source ? <span className="technical-detail">· {s.source}</span> : null}
                          </label>
                        ))}
                      </div>
                    ) : (
                      <div style={{ opacity: 0.85 }}>
                        Sin sugerencias aún. Puedes escribir un código manualmente abajo.
                      </div>
                    )}

                    <div className="coding__field">
                      <label htmlFor="guided-final-code">Código final</label>
                      <input
                        id="guided-final-code"
                        value={guidedFinalCode}
                        onChange={(e) => setGuidedFinalCode(e.target.value)}
                        placeholder="Escribe o ajusta el código..."
                        disabled={!!guidedBusy}
                      />
                    </div>

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button type="button" className="primary-action" onClick={() => void handleGuidedAccept()} disabled={!!guidedBusy}>
                        {guidedBusy === "accept" ? "Registrando..." : "✅ Aceptar y registrar"}
                      </button>
                      <button type="button" onClick={() => void handleGuidedReject()} disabled={!!guidedBusy}>
                        {guidedBusy === "reject" ? "Guardando..." : "🚫 Rechazar"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      }
      case "assign":
        return (
          <div className="coding__panel" ref={assignSectionRef}>
            <p className="coding__hint">En el flujo de la sección 'panel cualitativo de busqueda semantica'</p>
            <form className="coding__form" onSubmit={handleAssign}>
              <div className="coding__field">
                <label htmlFor="coding-fragment">fragmento_id</label>
                <input
                  id="coding-fragment"
                  value={assignFragmentId}
                  onChange={(event) => setAssignFragmentId(event.target.value)}
                  placeholder="entrevista/001#p12"
                  disabled={assignBusy}
                  required
                />
              </div>
              <div className="coding__field">
                <label htmlFor="coding-code">Codigo</label>
                <input
                  id="coding-code"
                  ref={assignCodeInputRef}
                  value={assignCodigo}
                  onChange={(event) => setAssignCodigo(event.target.value)}
                  placeholder="Resiliencia comunitaria"
                  disabled={assignBusy}
                  required
                />
              </div>
              <div className="coding__field">
                <label htmlFor="coding-source">Fuente (opcional)</label>
                <input
                  id="coding-source"
                  value={assignFuente}
                  onChange={(event) => setAssignFuente(event.target.value)}
                  placeholder="Entrevistada F12"
                  disabled={assignBusy}
                />
              </div>
              <div className="coding__field coding__field--full">
                <label htmlFor="coding-quote">Cita / memo</label>
                <textarea
                  id="coding-quote"
                  rows={3}
                  value={assignCita}
                  onChange={(event) => setAssignCita(event.target.value)}
                  placeholder="Fragmento icónico que justifica el codigo..."
                  disabled={assignBusy}
                  required
                />
              </div>
              <button type="submit" disabled={assignBusy}>
                {assignBusy ? "Asignando..." : "Registrar codigo"}
              </button>
            </form>
            <p className="coding__hint">
              Selecciona un fragmento desde la lista de entrevistas o "Fragmentos recientes" y usa el botón "Usar
              fragmento" para autocompletar el fragmento_id y evitar errores de copia.
            </p>
            {assignInfo && (
              <div className="app__info" style={{
                background: 'linear-gradient(135deg, #e8f4fd 0%, #d4e9f7 100%)',
                border: '1px solid #2196F3',
                borderRadius: '8px',
                padding: '12px 16px',
                marginBottom: '12px',
                color: '#1565C0',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                <span>{assignInfo}</span>
              </div>
            )}
            {assignError && (
              <div className="app__error">
                <strong>Error al codificar.</strong>
                <span>{assignError}</span>
              </div>
            )}
            {assignResult && (
              <div className="coding__feedback">
                <h3>Codigo registrado</h3>
                <dl>
                  <div>
                    <dt>fragmento_id</dt>
                    <dd>{assignResult.fragmento_id}</dd>
                  </div>
                  <div>
                    <dt>Codigo</dt>
                    <dd>{assignResult.codigo}</dd>
                  </div>
                  <div>
                    <dt>Archivo</dt>
                    <dd>{assignResult.archivo}</dd>
                  </div>
                  <div>
                    <dt>Fuente</dt>
                    <dd>{assignResult.fuente || "-"}</dd>
                  </div>
                  <div className="coding__feedback-text">
                    <dt>Cita</dt>
                    <dd>{assignResult.cita}</dd>
                  </div>
                </dl>
              </div>
            )}
          </div>
        );
      case "suggest":
        return (
          <div className="coding__panel" ref={suggestSectionRef}>
            <p className="coding__hint">En el flujo de la sección 'panel cualitativo de busqueda semantica'</p>
            {/* Filtro de entrevista para alinear sugerencias */}
            <div className="coding__interview-filter" style={{
              background: 'linear-gradient(135deg, #f0f9ff, #e0f2fe)',
              border: '1px solid #0ea5e9',
              borderRadius: '0.5rem',
              padding: '0.75rem 1rem',
              marginBottom: '1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              flexWrap: 'wrap'
            }}>
              <label style={{ fontWeight: 600, color: '#0369a1' }}>
                📁 Entrevista activa:
              </label>
              <select
                value={suggestInterviewFilter}
                onChange={(e) => {
                  setSuggestInterviewFilter(e.target.value);
                  setSuggestArchivo(e.target.value);
                  // Si se selecciona una entrevista, cargar sus fragmentos
                  if (e.target.value) {
                    const interview = interviews.find(i => i.archivo === e.target.value);
                    if (interview) {
                      setSelectedInterview(interview);
                      void loadInterviewFragments(e.target.value);
                    }
                  } else {
                    setSelectedInterview(null);
                  }
                }}
                style={{
                  padding: '0.4rem 0.75rem',
                  borderRadius: '0.375rem',
                  border: '1px solid #0ea5e9',
                  background: 'white',
                  minWidth: '250px'
                }}
              >
                <option value="">Todas las entrevistas</option>
                {interviews.map((interview) => (
                  <option key={interview.archivo} value={interview.archivo}>
                    {interview.archivo} ({interview.fragmentos} fragmentos)
                  </option>
                ))}
              </select>
              {suggestInterviewFilter && (
                <span style={{ fontSize: '0.85rem', color: '#0369a1' }}>
                  ✓ Las sugerencias y fragmentos mostrarán solo de esta entrevista
                </span>
              )}
            </div>

            {/* Sección de contexto: fragmentos con el código seleccionado */}
            {selectedCodeContext && (
              <div className="coding__code-context" style={{
                background: 'linear-gradient(135deg, #fef3c7, #fde68a)',
                border: '2px solid #f59e0b',
                borderRadius: '0.75rem',
                padding: '1rem',
                marginBottom: '1rem'
              }}>
                <header style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '0.75rem'
                }}>
                  <div>
                    <h4 style={{ margin: 0, color: '#92400e', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      🏷️ Fragmentos con código: <strong style={{ color: '#b45309' }}>"{selectedCodeContext}"</strong>
                    </h4>
                    <p style={{ margin: '0.25rem 0 0', fontSize: '0.85rem', color: '#a16207' }}>
                      {codeContextLoading
                        ? 'Cargando...'
                        : `${codeContextCitations.length} fragmento(s) ya tienen este código asignado`}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCodeContext(null);
                      setCodeContextCitations([]);
                    }}
                    style={{
                      background: 'transparent',
                      border: '1px solid #d97706',
                      borderRadius: '0.375rem',
                      padding: '0.25rem 0.5rem',
                      cursor: 'pointer',
                      color: '#92400e',
                      fontSize: '0.8rem'
                    }}
                  >
                    ✕ Cerrar
                  </button>
                </header>

                {codeContextCitations.length > 0 && (
                  <ul style={{
                    listStyle: 'none',
                    margin: 0,
                    padding: 0,
                    maxHeight: '250px',
                    overflowY: 'auto'
                  }}>
                    {codeContextCitations.map((citation, idx) => (
                      <li
                        key={citation.fragmento_id + idx}
                        style={{
                          background: 'rgba(255,255,255,0.7)',
                          borderRadius: '0.5rem',
                          padding: '0.75rem',
                          marginBottom: '0.5rem',
                          fontSize: '0.9rem'
                        }}
                      >
                        <div style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                          marginBottom: '0.5rem'
                        }}>
                          <div>
                            <strong style={{ color: '#78350f' }}>{citation.fragmento_id}</strong>
                            {citation.fuente && (
                              <span style={{ marginLeft: '0.5rem', color: '#92400e', fontSize: '0.8rem' }}>
                                ({citation.fuente})
                              </span>
                            )}
                          </div>
                        </div>
                        <p style={{
                          margin: 0,
                          color: '#451a03',
                          lineHeight: 1.4,
                          fontStyle: 'italic'
                        }}>
                          "{(citation.cita || '').slice(0, 200)}{(citation.cita || '').length > 200 ? '...' : ''}"
                        </p>
                      </li>
                    ))}
                  </ul>
                )}

                {!codeContextLoading && codeContextCitations.length === 0 && (
                  <p style={{
                    margin: 0,
                    padding: '0.5rem',
                    background: 'rgba(255,255,255,0.5)',
                    borderRadius: '0.375rem',
                    color: '#92400e',
                    fontSize: '0.9rem'
                  }}>
                    Este código aún no tiene fragmentos asignados. ¡Serás el primer@ en usarlo!
                  </p>
                )}
              </div>
            )}

            <form className="coding__form" onSubmit={handleSuggest}>
              <div className="coding__field">
                <label htmlFor="suggest-fragment">fragmento semilla</label>
                <input
                  id="suggest-fragment"
                  ref={suggestFragmentInputRef}
                  value={suggestFragmentId}
                  onChange={(event) => setSuggestFragmentId(event.target.value)}
                  placeholder="entrevista/002#p8"
                  disabled={suggestBusy}
                  required
                />
              </div>
              <div className="coding__field">
                <label htmlFor="suggest-topk">Resultados</label>
                <input
                  id="suggest-topk"
                  type="number"
                  min={1}
                  max={20}
                  value={suggestTopK}
                  onChange={(event) => setSuggestTopK(Number(event.target.value))}
                  disabled={suggestBusy}
                />
              </div>
              <div className="coding__field">
                <label htmlFor="suggest-archivo">Archivo (filtro)</label>
                <input
                  id="suggest-archivo"
                  value={suggestArchivo}
                  onChange={(event) => setSuggestArchivo(event.target.value)}
                  placeholder="entrevista_prueba.docx"
                  disabled={suggestBusy}
                />
              </div>
              <div className="coding__field">
                <label htmlFor="suggest-area">Area temática</label>
                <input
                  id="suggest-area"
                  value={suggestArea}
                  onChange={(event) => setSuggestArea(event.target.value)}
                  placeholder="Salud mental"
                  disabled={suggestBusy}
                />
              </div>
              <div className="coding__field">
                <label htmlFor="suggest-actor">Actor principal</label>
                <input
                  id="suggest-actor"
                  value={suggestActor}
                  onChange={(event) => setSuggestActor(event.target.value)}
                  placeholder="Profesora"
                  disabled={suggestBusy}
                />
              </div>
              <div className="coding__field">
                <label htmlFor="suggest-lluvia">Requiere protocolo lluvia</label>
                <select
                  id="suggest-lluvia"
                  value={suggestLluvia}
                  onChange={(event) => setSuggestLluvia(event.target.value)}
                  disabled={suggestBusy}
                >
                  <option value="any">Todos</option>
                  <option value="true">Solo con bandera</option>
                  <option value="false">Solo sin bandera</option>
                </select>
              </div>
              <label className="coding__checkbox">
                <input
                  type="checkbox"
                  checked={suggestIncludeCoded}
                  onChange={(event) => setSuggestIncludeCoded(event.target.checked)}
                  disabled={suggestBusy || suggestRunnerLoading}
                />
                Incluir fragmentos ya codificados
              </label>

              <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
                <button type="submit" disabled={suggestBusy || suggestRunnerLoading}>
                  {suggestBusy ? "Buscando..." : "Buscar sugerencias"}
                </button>

                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <label htmlFor="suggest-runner-steps" style={{ fontSize: "0.85rem", opacity: 0.9 }}>
                    Pasos
                  </label>
                  <input
                    id="suggest-runner-steps"
                    type="number"
                    min={1}
                    max={50}
                    value={suggestRunnerSteps}
                    onChange={(event) => setSuggestRunnerSteps(Number(event.target.value))}
                    disabled={suggestBusy || suggestRunnerLoading}
                    style={{ width: "6rem" }}
                  />
                </div>

                <button
                  type="button"
                  onClick={handleRunSuggestRunner}
                  disabled={suggestBusy || suggestRunnerLoading}
                  title="Ejecuta un seed-loop automático: semilla → sugerencias → siguiente semilla"
                >
                  {suggestRunnerLoading ? "⏳ Runner..." : "🚀 Runner"}
                </button>
              </div>
            </form>

            {suggestRunnerError && (
              <div className="app__error">
                <strong>Runner</strong>
                <span>{suggestRunnerError}</span>
                {suggestRunnerTask?.status === "error" && (
                  <div style={{ marginTop: "0.5rem" }}>
                    <button
                      type="button"
                      onClick={handleResumeSuggestRunner}
                      disabled={suggestRunnerLoading}
                      title="Reanuda desde el último checkpoint guardado en disco"
                    >
                      {suggestRunnerLoading ? "⏳ Reanudando..." : "▶️ Reanudar"}
                    </button>
                  </div>
                )}
              </div>
            )}

            {suggestRunnerTask && (
              <div className="app__info" style={{
                background: "linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)",
                border: "1px solid #6366f1",
                borderRadius: "8px",
                padding: "12px 16px",
                marginTop: "12px",
                color: "#3730a3",
              }}>
                <div>
                  Estado: <strong>{suggestRunnerTask.status}</strong> | Paso {suggestRunnerTask.current_step}/{suggestRunnerTask.total_steps}
                  {" "}| Seeds: {suggestRunnerTask.visited_seeds} | Únicos (fragmentos): {suggestRunnerTask.unique_suggestions}
                  {typeof suggestRunnerTask.current_step_in_interview === "number" && typeof suggestRunnerTask.steps_per_interview === "number"
                    ? ` | Paso entrevista ${suggestRunnerTask.current_step_in_interview}/${suggestRunnerTask.steps_per_interview}`
                    : ""}
                </div>
                <div style={{ marginTop: "0.25rem", fontSize: "0.85rem", opacity: 0.9 }}>
                  {suggestRunnerTask.current_archivo ? `Entrevista: ${suggestRunnerTask.current_archivo}` : ""}
                  {typeof suggestRunnerTask.interview_index === "number" && typeof suggestRunnerTask.interviews_total === "number"
                    ? ` | ${suggestRunnerTask.interview_index}/${suggestRunnerTask.interviews_total}`
                    : ""}
                  {typeof suggestRunnerTask.memos_saved === "number" ? ` | Memos: ${suggestRunnerTask.memos_saved}` : ""}
                  {typeof suggestRunnerTask.candidates_submitted === "number" ? ` | Enviados (runner): ${suggestRunnerTask.candidates_submitted}` : ""}
                  {typeof suggestRunnerTask.llm_calls === "number" ? ` | IA: ${suggestRunnerTask.llm_calls}` : ""}
                  {typeof suggestRunnerTask.llm_failures === "number" ? ` (fallas: ${suggestRunnerTask.llm_failures})` : ""}
                  {suggestRunnerTask.last_suggested_code ? ` | Último código: ${suggestRunnerTask.last_suggested_code}` : ""}
                  {suggestRunnerTask.saturated ? " | Saturación" : ""}
                </div>
                {suggestRunnerTask.message && (
                  <div style={{ marginTop: "0.25rem", fontSize: "0.85rem", opacity: 0.9 }}>
                    {suggestRunnerTask.message}
                  </div>
                )}
                {suggestRunnerTask.errors && suggestRunnerTask.errors.length > 0 && (
                  <div style={{ marginTop: "0.25rem", fontSize: "0.8rem", color: "#991b1b" }}>
                    {suggestRunnerTask.errors.slice(0, 2).join(" | ")}
                  </div>
                )}

                {suggestRunnerTask.status === "completed" && suggestRunnerResult && (
                  <div style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                    <div>
                      <strong>Memos generados:</strong> {suggestRunnerResult.memos?.length ?? 0}
                      {suggestRunnerPendingCount !== null ? (
                        <>
                          {" "}| <strong>Pendientes (Bandeja, total):</strong> {suggestRunnerPendingCount}
                        </>
                      ) : null}
                      {typeof suggestRunnerTask.candidates_pending_before_db === "number" && typeof suggestRunnerTask.candidates_pending_after_db === "number" ? (
                        <>
                          {" "}| <strong>DB antes→después:</strong> {suggestRunnerTask.candidates_pending_before_db}→{suggestRunnerTask.candidates_pending_after_db}
                        </>
                      ) : null}
                    </div>

                    {suggestRunnerResult.memos && suggestRunnerResult.memos.length > 0 && (
                      <div style={{ marginTop: "0.25rem" }}>
                        <div style={{ fontSize: "0.8rem", opacity: 0.85 }}>
                          Últimos memos (clic para descargar):
                        </div>
                        <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.25rem" }}>
                          {suggestRunnerResult.memos
                            .slice(-10)
                            .reverse()
                            .map((memo, index) => {
                              const rawRel = memo.rel || memo.path || memo.filename || "";
                              const rel = rawRel
                                .replace(/\\/g, "/")
                                .replace(new RegExp(`^notes/${project.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&")}/`, "i"), "");
                              const href = `/api/notes/${encodeURIComponent(project)}/download?rel=${encodeURIComponent(rel)}`;
                              const label = memo.filename || memo.rel || rel || `memo_${index + 1}.md`;
                              return (
                                <li key={`${label}_${index}`}>
                                  <a href={href} target="_blank" rel="noreferrer">
                                    {label}
                                  </a>
                                </li>
                              );
                            })}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
            {selectedInterview && (
              <div className="coding__samples coding__samples--interview">
                <header className="coding__samples-header">
                  <div>
                    <h3>Fragmentos de {selectedInterview.archivo}</h3>
                    <p>
                      Copia y pega el identificador del fragmento para ejecutar la búsqueda semántica con filtros
                      específicos.
                    </p>
                    <div style={{ marginTop: "0.35rem", fontSize: "0.9rem" }}>
                      <strong>Memos Runner Semántico (persistidos):</strong>{" "}
                      {runnerSemanticMemosLoading
                        ? "Cargando..."
                        : runnerSemanticMemosError
                          ? `Error: ${runnerSemanticMemosError}`
                          : `${runnerSemanticMemos.length}`}
                    </div>
                    {!runnerSemanticMemosLoading && !runnerSemanticMemosError && runnerSemanticMemos.length > 0 && (
                      <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.25rem" }}>
                        {runnerSemanticMemos.slice(0, 5).map((memo, index) => {
                          const rawRel = memo.rel || memo.filename || "";
                          const rel = rawRel
                            .replace(/\\/g, "/")
                            .replace(new RegExp(`^notes/${project.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&")}/`, "i"), "");
                          const href = `/api/notes/${encodeURIComponent(project)}/download?rel=${encodeURIComponent(rel)}`;
                          const label = memo.filename || rel || `memo_${index + 1}.md`;
                          return (
                            <li key={`${label}_${index}`}>
                              <a href={href} target="_blank" rel="noreferrer">
                                {label}
                              </a>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleRefreshInterviewFragments}
                    disabled={interviewFragmentsLoading}
                  >
                    {interviewFragmentsLoading ? "Actualizando..." : "Refrescar lista"}
                  </button>
                </header>
                {interviewFragmentsError && (
                  <div className="app__error">
                    <strong>No fue posible cargar los fragmentos de la entrevista.</strong>
                    <span>{interviewFragmentsError}</span>
                  </div>
                )}
                {!interviewFragmentsError && (
                  <ul className="coding__samples-list">
                    {interviewFragmentsLoading && (
                      <li className="coding__samples-hint">Cargando fragmentos de la entrevista...</li>
                    )}
                    {!interviewFragmentsLoading && interviewFragments.length === 0 && (
                      <li className="coding__samples-hint">
                        No se encontraron fragmentos cargados para este archivo. Revisa la ingesta.
                      </li>
                    )}
                    {!interviewFragmentsLoading &&
                      interviewFragments.map((item) => (
                        <li key={item.fragmento_id}>
                          <header>
                            <div>
                              <strong>{item.fragmento_id}</strong>
                              <span>par_idx {item.par_idx}</span>
                              <span>len {item.char_len}</span>
                            </div>
                            <button type="button" onClick={() => handleSelectSample(item)}>
                              Usar fragmento
                            </button>
                          </header>
                          <p>{(item.fragmento || "").slice(0, 220)}...</p>
                        </li>
                      ))}
                  </ul>
                )}
              </div>
            )}
            <div className="coding__samples">
              <header className="coding__samples-header">
                <div>
                  <h3>
                    {suggestInterviewFilter
                      ? `📄 Fragmentos de: ${suggestInterviewFilter}`
                      : "📋 Fragmentos recientes (todas las entrevistas)"}
                  </h3>
                  <p>
                    {suggestInterviewFilter
                      ? "Selecciona un fragmento de esta entrevista para buscar similares."
                      : "Selecciona una entrevista arriba para filtrar, o usa estos fragmentos de muestra."}
                  </p>
                </div>
                <button type="button" onClick={handleRefreshSamples} disabled={samplesLoading}>
                  {samplesLoading ? "Actualizando..." : "Refrescar lista"}
                </button>
              </header>
              {samplesError && (
                <div className="app__error">
                  <strong>No fue posible cargar fragmentos.</strong>
                  <span>{samplesError}</span>
                </div>
              )}
              {!samplesError && (
                <ul className="coding__samples-list">
                  {samplesLoading && <li className="coding__samples-hint">Cargando fragmentos...</li>}
                  {!samplesLoading && samples.length === 0 && (
                    <li className="coding__samples-hint">
                      Ejecuta una ingesta o ajusta el límite para visualizar fragmentos disponibles.
                    </li>
                  )}
                  {!samplesLoading &&
                    samples.map((item) => (
                      <li key={item.fragmento_id}>
                        <header>
                          <div>
                            <strong>{item.fragmento_id}</strong>
                            <span>{item.archivo}</span>
                            <span>par_idx {item.par_idx}</span>
                          </div>
                          <button type="button" onClick={() => handleSelectSample(item)}>
                            Usar como semilla
                          </button>
                        </header>
                        <p>{(item.fragmento || "").slice(0, 220)}...</p>
                      </li>
                    ))}
                </ul>
              )}
            </div>
            {suggestError && (
              <div className="app__error">
                <strong>No se pudieron generar sugerencias.</strong>
                <span>{suggestError}</span>
              </div>
            )}
            {suggestions.length > 0 && (
              <div className="coding__feedback coding__feedback--list">
                <h3>Fragmentos similares</h3>
                <p className="coding__score-guide">
                  <strong>📊 Interpretación del Score</strong> (Similitud Coseno):
                  <span style={{ color: '#dc2626' }}>0.0-0.5 Baja</span> •
                  <span style={{ color: '#f59e0b' }}>0.5-0.7 Moderada</span> •
                  <span style={{ color: '#10b981' }}>0.7-0.85 Buena</span> •
                  <span style={{ color: '#059669', fontWeight: 'bold' }}>0.85+ Alta</span>
                </p>

                {/* Sprint 17: Controles de selección masiva */}
                <div style={{
                  display: 'flex',
                  gap: '0.75rem',
                  alignItems: 'center',
                  padding: '0.75rem',
                  background: 'linear-gradient(135deg, #f0f9ff, #e0f2fe)',
                  borderRadius: '0.5rem',
                  marginBottom: '0.75rem',
                  flexWrap: 'wrap',
                }}>
                  <button
                    type="button"
                    onClick={handleSelectAllSuggestions}
                    style={{
                      padding: '0.4rem 0.75rem',
                      background: 'white',
                      border: '1px solid #0ea5e9',
                      borderRadius: '0.375rem',
                      cursor: 'pointer',
                    }}
                  >
                    {selectedSuggestionIds.size === suggestions.length ? '☐ Deseleccionar todos' : '☑ Seleccionar todos'}
                  </button>
                  <span style={{ color: '#0369a1', fontWeight: 500 }}>
                    {selectedSuggestionIds.size} de {suggestions.length} seleccionados
                  </span>
                  <button
                    type="button"
                    onClick={handleGenerateActionSuggestion}
                    disabled={selectedSuggestionIds.size === 0 || actionSuggestionBusy}
                    style={{
                      padding: '0.5rem 1rem',
                      background: selectedSuggestionIds.size === 0
                        ? '#d1d5db'
                        : 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '0.375rem',
                      cursor: selectedSuggestionIds.size === 0 ? 'not-allowed' : 'pointer',
                      fontWeight: 600,
                      marginLeft: 'auto',
                    }}
                  >
                    {actionSuggestionBusy ? '⏳ Generando...' : '💡 Generar Sugerencia IA'}
                  </button>
                </div>

                {/* Sprint 17: ActionSuggestionCard */}
                {showActionSuggestion && (
                  <ActionSuggestionCard
                    suggestedCode={actionSuggestionCode}
                    memo={actionSuggestionMemo}
                    confidence={actionSuggestionConfidence}
                    selectedFragments={suggestions
                      .filter(s => selectedSuggestionIds.has(s.fragmento_id))
                      .map(s => ({
                        fragmento_id: s.fragmento_id,
                        archivo: s.archivo || '',
                        fragmento: s.fragmento || '',
                        score: s.score,
                      }))}
                    isSubmitting={batchSubmitBusy}
                    isSavingMemo={saveMemoLoading}
                    onCodeChange={setActionSuggestionCode}
                    onMemoChange={setActionSuggestionMemo}
                    onSubmit={handleSubmitToCandidates}
                    onRegenerate={handleGenerateActionSuggestion}
                    onCancel={handleCancelActionSuggestion}
                    onSaveMemo={handleSaveMemo}
                  />
                )}

                <table>
                  <thead>
                    <tr>
                      <th style={{ width: '3rem' }}>☑</th>
                      <th>Score</th>
                      <th>fragmento_id</th>
                      <th>Archivo</th>
                      <th>Vista preliminar</th>
                      <th>Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {suggestions.map((item) => {
                      const score = item.score;
                      const scoreColor = score >= 0.85 ? '#059669' : score >= 0.7 ? '#10b981' : score >= 0.5 ? '#f59e0b' : '#dc2626';
                      const isSelected = selectedSuggestionIds.has(item.fragmento_id);
                      return (
                        <tr key={item.fragmento_id} style={{ background: isSelected ? '#f0f9ff' : undefined }}>
                          <td>
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => handleToggleSuggestionSelection(item.fragmento_id)}
                              style={{ width: '1.2rem', height: '1.2rem', cursor: 'pointer' }}
                            />
                          </td>
                          <td style={{ color: scoreColor, fontWeight: 'bold' }}>{item.score.toFixed(4)}</td>
                          <td>{item.fragmento_id.slice(0, 12)}...</td>
                          <td>{item.archivo || "-"}</td>
                          <td>{(item.fragmento || "").slice(0, 120)}...</td>
                          <td style={{ display: 'flex', gap: '0.25rem' }}>
                            <button
                              type="button"
                              onClick={async () => {
                                const codigo = prompt(
                                  `💡 Proponer Código Candidato\n\nIngresa el nombre del código para este fragmento:\n\nArchivo: ${item.archivo}\nScore: ${item.score.toFixed(4)}\nTexto: ${(item.fragmento || "").slice(0, 80)}...`
                                );
                                if (!codigo || !codigo.trim()) return;
                                try {
                                  const res = await submitCandidate({
                                    project,
                                    codigo: codigo.trim(),
                                    cita: (item.fragmento || "").slice(0, 300),
                                    fragmento_id: item.fragmento_id,
                                    archivo: item.archivo || "",
                                    fuente_origen: "semantic_suggestion",
                                    score_confianza: item.score,
                                    memo: "Propuesto desde sugerencias semánticas",
                                  });
                                  if (res.success) {
                                    alert(`✅ Código "${codigo}" propuesto como candidato.`);
                                  }
                                } catch (err) {
                                  alert("Error: " + (err instanceof Error ? err.message : String(err)));
                                }
                              }}
                              title="Proponer como código candidato para validación"
                              style={{
                                background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
                                color: 'white',
                                border: 'none',
                                padding: '0.25rem 0.5rem',
                                borderRadius: '0.25rem',
                                cursor: 'pointer',
                                fontSize: '0.75rem'
                              }}
                            >
                              💡 Proponer
                            </button>
                            <button
                              type="button"
                              onClick={() => handleAddSuggestionToCode(item)}
                              title="Agregar este fragmento al código actual"
                              style={{
                                background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                                color: 'white',
                                border: 'none',
                                padding: '0.25rem 0.5rem',
                                borderRadius: '0.25rem',
                                cursor: 'pointer',
                                fontSize: '0.75rem'
                              }}
                            >
                              +📝 Codificar
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {suggestions.length === 0 && !suggestError && !suggestBusy && (
              <p className="coding__hint">
                Lanza una consulta para encontrar fragmentos afines y ampliar la codificacion con evidencia
                consistente.
              </p>
            )}
          </div>
        );
      case "insights":
        return (
          <div className="coding__panel">
            <div className="coding__insights-header">
              <div>
                <h3>Avance del proyecto</h3>
                <p>
                  Revisa cobertura, volumen de citas y apoyo axial para priorizar los siguientes lotes de
                  analisis cualitativo.
                </p>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button type="button" onClick={() => void loadStats()} disabled={statsLoading}>
                  {statsLoading ? "Actualizando..." : "Refrescar indicadores"}
                </button>
              </div>
            </div>
            {statsError && (
              <div className="app__error">
                <strong>No fue posible cargar los indicadores.</strong>
                <span>{statsError}</span>
              </div>
            )}
            {!statsError && (
              <div className="coding__metrics">
                {statsLoading && <p>Cargando indicadores...</p>}
                {!statsLoading && stats && (
                  <>
                    <div>
                      <span>Fragmentos codificados</span>
                      <strong>{stats.fragmentos_codificados ?? 0}</strong>
                    </div>
                    <div>
                      <span>Fragmentos sin codigo</span>
                      <strong>{stats.fragmentos_sin_codigo ?? 0}</strong>
                    </div>
                    <div>
                      <span>Cobertura</span>
                      <strong>{formatPercentage(stats.porcentaje_cobertura)}</strong>
                    </div>
                    <div>
                      <span>Codigos unicos</span>
                      <strong>{stats.codigos_unicos ?? 0}</strong>
                    </div>
                    <div>
                      <span>Total de citas</span>
                      <strong>{stats.total_citas ?? 0}</strong>
                    </div>
                    <div>
                      <span>Relaciones axiales</span>
                      <strong>{stats.relaciones_axiales ?? 0}</strong>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Exportar a herramientas CAQDAS */}
            <div style={{
              marginTop: "1.5rem",
              padding: "1rem",
              background: "linear-gradient(135deg, #e0f2fe, #bae6fd)",
              borderRadius: "0.5rem"
            }}>
              <h4 style={{ margin: "0 0 0.75rem 0", color: "#0369a1" }}>📤 Exportar códigos</h4>
              <p style={{ margin: "0 0 0.75rem 0", fontSize: "0.85rem", color: "#0c4a6e" }}>
                Descarga tus códigos para usar en herramientas de análisis cualitativo estándar.
              </p>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <a
                  href={`/api/export/refi-qda?project=${encodeURIComponent(project)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.25rem",
                    padding: "0.5rem 1rem",
                    background: "linear-gradient(135deg, #10b981, #059669)",
                    color: "white",
                    borderRadius: "0.375rem",
                    textDecoration: "none",
                    fontWeight: 500
                  }}
                >
                  📦 REFI-QDA (Atlas.ti)
                </a>
                <a
                  href={`/api/export/maxqda?project=${encodeURIComponent(project)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.25rem",
                    padding: "0.5rem 1rem",
                    background: "linear-gradient(135deg, #3b82f6, #1d4ed8)",
                    color: "white",
                    borderRadius: "0.375rem",
                    textDecoration: "none",
                    fontWeight: 500
                  }}
                >
                  📊 CSV (MAXQDA)
                </a>
              </div>
            </div>
          </div>
        );
      case "citations":
        return (
          <div className="coding__panel" ref={citationsSectionRef}>
            <form className="coding__form" onSubmit={handleCitations}>
              <div className="coding__field">
                <label htmlFor="coding-citation">Código</label>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <select
                    value={citationsCodigo}
                    onChange={(e) => setCitationsCodigo(e.target.value)}
                    disabled={citationsBusy || codes.length === 0}
                    style={{ flex: 1 }}
                  >
                    <option value="">Seleccionar código...</option>
                    {codes.map((code) => (
                      <option key={code.codigo} value={code.codigo}>
                        {code.codigo} ({code.citas} citas)
                      </option>
                    ))}
                  </select>
                  <input
                    id="coding-citation"
                    ref={citationsInputRef}
                    value={citationsCodigo}
                    onChange={(event) => setCitationsCodigo(event.target.value)}
                    placeholder="O escribe el nombre..."
                    disabled={citationsBusy}
                    style={{ flex: 1 }}
                  />
                </div>
              </div>
              <button type="submit" disabled={citationsBusy || !citationsCodigo.trim()}>
                {citationsBusy ? "Consultando..." : "Listar citas"}
              </button>
            </form>
            {citationsError && (
              <div className="app__error">
                <strong>Error al cargar citas.</strong>
                <span>{citationsError}</span>
              </div>
            )}
            {citations.length > 0 && (
              <div className="coding__feedback coding__feedback--list">
                <h3>Citas registradas ({citations.length})</h3>
                <p style={{ fontSize: "0.85rem", color: "#6b7280", marginBottom: "0.75rem" }}>
                  💡 Usa el botón "📋 Aplicar" para reutilizar estos datos en una nueva asignación.
                </p>
                <ul>
                  {citations.map((item, idx) => (
                    <li key={`${item.fragmento_id}-${idx}`}>
                      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <div>
                          <strong>{item.fragmento_id.slice(0, 20)}...</strong>
                          <span>{item.archivo}</span>
                          <span>{item.fuente || "(sin fuente)"}</span>
                          {item.created_at && <span style={{ fontSize: "0.75rem", color: "#9ca3af" }}>{new Date(item.created_at).toLocaleDateString()}</span>}
                        </div>
                        <div style={{ display: "flex", gap: "0.25rem" }}>
                          <button
                            type="button"
                            onClick={() => handleApplyCitation(item)}
                            title="Aplicar esta cita al formulario de asignación"
                            style={{
                              background: "linear-gradient(135deg, #10b981, #059669)",
                              color: "white",
                              border: "none",
                              padding: "0.25rem 0.5rem",
                              borderRadius: "0.25rem",
                              cursor: "pointer",
                              fontSize: "0.8rem",
                              whiteSpace: "nowrap"
                            }}
                          >
                            📋 Aplicar
                          </button>
                          <button
                            type="button"
                            onClick={() => setContextModalFragmentId(item.fragmento_id)}
                            title="Ver contexto completo del fragmento"
                            style={{
                              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                              color: "white",
                              border: "none",
                              padding: "0.25rem 0.5rem",
                              borderRadius: "0.25rem",
                              cursor: "pointer",
                              fontSize: "0.8rem",
                              whiteSpace: "nowrap"
                            }}
                          >
                            🔍 Contexto
                          </button>
                          <button
                            type="button"
                            onClick={() => handleUnassignCode(item)}
                            disabled={unassignBusy === item.fragmento_id}
                            title="Desvincular este código del fragmento (no elimina la cita)"
                            style={{
                              background: unassignBusy === item.fragmento_id
                                ? "#9ca3af"
                                : "linear-gradient(135deg, #ef4444, #dc2626)",
                              color: "white",
                              border: "none",
                              padding: "0.25rem 0.5rem",
                              borderRadius: "0.25rem",
                              cursor: unassignBusy === item.fragmento_id ? "wait" : "pointer",
                              fontSize: "0.8rem",
                              whiteSpace: "nowrap"
                            }}
                          >
                            {unassignBusy === item.fragmento_id ? "..." : "🗑️ Desvincular"}
                          </button>
                        </div>
                      </header>
                      {item.memo && <small className="coding__citation-memo">{item.memo}</small>}
                      <p>{item.cita}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {citations.length === 0 && !citationsError && !citationsBusy && (
              <p className="coding__hint">
                Consulta las citas asociadas a un codigo para validar consistencia y preparar insumos de
                reporte o sesiones de member checking.
              </p>
            )}
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <section className="coding">
      <header className="coding__header">
        <div>
          <h2>Etapa 3 – Codificación abierta</h2>
          <p>
            Descompone los fragmentos en unidades analíticas, asigna códigos con sus citas justificativas y
            sostiene la trazabilidad entre PostgreSQL, Neo4j y Qdrant sin salir del tablero.
          </p>
        </div>
        <div className="coding__project">
          <span>Proyecto en curso</span>
          <strong>{project}</strong>
        </div>
      </header>

      {/* Filtro global de entrevista - Metodologícamente importante para Etapa 3 */}
      {/* E3-1.1: Scope persistente + visible con badge de modo */}
      <div style={{
        background: scopeMode === 'case' 
          ? 'linear-gradient(135deg, #dcfce7, #bbf7d0)' 
          : 'linear-gradient(135deg, #fef3c7, #fde68a)',
        padding: '0.75rem 1rem',
        borderRadius: '0.5rem',
        marginBottom: '1rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '1rem',
        flexWrap: 'wrap',
        border: scopeMode === 'case' ? '2px solid #22c55e' : '2px solid #f59e0b'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Badge de modo scope */}
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.35rem',
            padding: '0.25rem 0.6rem',
            borderRadius: '9999px',
            fontSize: '0.75rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            background: scopeMode === 'case' ? '#22c55e' : '#f59e0b',
            color: 'white',
            boxShadow: '0 1px 2px rgba(0,0,0,0.1)'
          }}>
            {scopeMode === 'case' ? '📄 Modo Caso' : '📁 Modo Proyecto'}
          </span>
          <select
            value={activeInterviewFilter}
            onChange={(e) => {
              const nextArchivo = e.target.value;
              setActiveInterviewFilter(nextArchivo);
              setCodesArchivoFilter(nextArchivo); // Sincronizar con códigos

              // Etapa 3: al elegir una entrevista, debe quedar efectivamente seleccionada
              // para que se carguen fragmentos y se mantenga trazabilidad.
              if (nextArchivo) {
                setSuggestArchivo(nextArchivo); // Sincronizar con sugerencias
                setSuggestInterviewFilter(nextArchivo);
                const interview = interviews.find((int) => int.archivo === nextArchivo) ?? null;
                setSelectedInterview(interview);
                setInterviewFragments([]);
                setInterviewFragmentsError(null);
                void loadInterviewFragments(nextArchivo);
              } else {
                // "Todas las entrevistas" es para Etapa 4 (comparación): aquí limpiamos selección.
                setSuggestInterviewFilter("");
                setSelectedInterview(null);
                setInterviewFragments([]);
                setInterviewFragmentsError(null);
              }
            }}
            style={{
              padding: '0.4rem 0.75rem',
              border: scopeMode === 'case' ? '2px solid #22c55e' : '2px solid #f59e0b',
              borderRadius: '0.375rem',
              background: 'white',
              fontWeight: 500,
              minWidth: '280px'
            }}
          >
            <option value="">📁 Todas las entrevistas (Modo Proyecto)</option>
            {interviews.map((int) => (
              <option key={int.archivo} value={int.archivo}>
                📄 {int.archivo} ({int.fragmentos} fragmentos)
              </option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', maxWidth: '400px' }}>
          {scopeMode === 'case' ? (
            <p style={{ margin: 0, fontSize: '0.8rem', color: '#166534' }}>
              ✅ <strong>Etapa 3</strong>: Analizando "{activeInterviewFilter}" de forma aislada.
              El scope se guarda automáticamente.
            </p>
          ) : (
            <p style={{ margin: 0, fontSize: '0.8rem', color: '#78350f' }}>
              ⚠️ <strong>Modo Proyecto</strong>: Para comparación transversal (Etapa 4).
              Selecciona una entrevista para análisis individual.
            </p>
          )}
        </div>
      </div>
      <div className="coding__resources">
        <section className="coding__resource">
          <header className="coding__resource-header">
            <div>
              <h3>Entrevistas ingeridas</h3>
              <p>Elige el archivo para autocompletar filtros en las sugerencias semánticas.</p>
            </div>
            <button type="button" onClick={handleRefreshInterviews} disabled={interviewsLoading}>
              {interviewsLoading ? "Actualizando..." : "Refrescar"}
            </button>
          </header>
          {interviewsError && (
            <div className="app__error">
              <strong>No se pudieron cargar las entrevistas.</strong>
              <span>{interviewsError}</span>
            </div>
          )}
          {!interviewsError && (
            <ul className="coding__resource-list">
              {interviewsLoading && <li className="coding__resource-hint">Cargando entrevistas...</li>}
              {!interviewsLoading && interviews.length === 0 && (
                <li className="coding__resource-hint">
                  Ejecuta la ingesta inicial para visualizar los archivos disponibles.
                </li>
              )}
              {!interviewsLoading &&
                interviews.map((item) => {
                  const active = selectedInterview?.archivo === item.archivo;
                  return (
                    <li
                      key={item.archivo}
                      className={active ? "is-active" : undefined}
                    >
                      <div>
                        <strong>{item.archivo}</strong>
                        <span>{item.fragmentos} fragmentos</span>
                        <span>{item.actor_principal || "Actor sin especificar"}</span>
                        {item.area_tematica && <span>{item.area_tematica}</span>}
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                        <button type="button" onClick={() => handleUseInterview(item)}>
                          {active ? "Seleccionada" : "Usar"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleAnalyze(item.archivo)}
                          disabled={analyzeBusy !== null}
                        >
                          {analyzeBusy === item.archivo ? "..." : "Analizar"}
                        </button>
                      </div>
                    </li>
                  );
                })}
            </ul>
          )}
        </section>
        <section className="coding__resource coding__resource--codes">
          <header className="coding__resource-header">
            <div>
              <h3>Códigos iniciales (IA)</h3>
              <p>Explora los códigos abiertos propuestos en la revisión asistida y reutilízalos al codificar.</p>
            </div>
            <div className="coding__resource-controls">
              <select
                value={codesArchivoFilter}
                onChange={(e) => setCodesArchivoFilter(e.target.value)}
                disabled={codesLoading || interviews.length === 0}
                style={{ marginRight: "0.5rem" }}
              >
                <option value="">Todas las entrevistas</option>
                {interviews.map((int) => (
                  <option key={int.archivo} value={int.archivo}>
                    {int.archivo} ({int.fragmentos} frag.)
                  </option>
                ))}
              </select>
              <button type="button" onClick={handleRefreshCodes} disabled={codesLoading}>
                {codesLoading ? "Actualizando..." : "Refrescar"}
              </button>
            </div>
          </header>
          {codesError && (
            <div className="app__error">
              <strong>No se pudieron cargar los códigos.</strong>
              <span>{codesError}</span>
            </div>
          )}
          {!codesError && (
            <ul className="coding__codes-list">
              {codesLoading && <li className="coding__resource-hint">Cargando códigos...</li>}
              {!codesLoading && codes.length === 0 && (
                <li className="coding__resource-hint">
                  Genera el análisis asistido (Etapa LLM) para poblar la lista de códigos iniciales.
                </li>
              )}
              {!codesLoading &&
                codes.map((code) => (
                  <li key={code.codigo}>
                    <div className="coding__code-info">
                      <strong>{code.codigo}</strong>
                      <span>
                        {code.citas} citas • {code.fragmentos} fragmentos
                      </span>
                      <span>
                        Registrado: {code.primera_cita ? code.primera_cita : "-"} →{" "}
                        {code.ultima_cita ? code.ultima_cita : "-"}
                      </span>
                    </div>
                    <div className="coding__code-actions">
                      <button type="button" onClick={() => handleUseCode(code)}>
                        Usar en asignación
                      </button>
                      <button type="button" onClick={() => handleInspectCode(code)}>
                        Revisar citas
                      </button>
                    </div>
                  </li>
                ))}
            </ul>
          )}
        </section>
      </div>
      <header className="coding__panel-header">
        <h2>🧬 Etapa 3 — Codificación Abierta</h2>
        <p>Herramientas para asignar códigos a fragmentos siguiendo la metodología de Teoría Fundamentada.</p>
      </header>
      <nav className="coding__tabs" aria-label="Herramientas de codificacion abierta">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={tab.key === activeTab ? "is-active" : ""}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <p className="coding__hint" style={{ marginTop: 8 }}>
        {tabs.find((t) => t.key === activeTab)?.description}
      </p>
      {renderTabContent()}

      {/* Modal de contexto completo del fragmento */}
      <FragmentContextModal
        project={project}
        fragmentId={contextModalFragmentId || ""}
        currentCode={citationsCodigo}
        isOpen={!!contextModalFragmentId}
        onClose={() => setContextModalFragmentId(null)}
        onApplyToForm={(fragment) => {
          setAssignFragmentId(fragment.id);
          setActiveTab("assign");
          window.requestAnimationFrame(() => {
            assignSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          });
        }}
      />
    </section>
  );
}
