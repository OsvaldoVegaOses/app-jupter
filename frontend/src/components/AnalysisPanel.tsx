import { useState, useEffect } from "react";
import { apiFetchJson, deleteFileData, EpistemicStatement } from "../services/api";

function memoBadgeStyle(type: string): React.CSSProperties {
  const t = (type || "").toUpperCase();
  if (t === "OBSERVATION") return { background: "#dcfce7", color: "#166534", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
  if (t === "INTERPRETATION") return { background: "#dbeafe", color: "#1e40af", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
  if (t === "HYPOTHESIS") return { background: "#fde68a", color: "#92400e", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
  if (t === "NORMATIVE_INFERENCE") return { background: "#fbcfe8", color: "#9d174d", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
  return { background: "#e5e7eb", color: "#374151", borderRadius: "999px", padding: "0.15rem 0.5rem", fontSize: "0.75rem", fontWeight: 700 };
}

type AnonymizationLevel = "basic" | "contextual" | "total";

interface ReplacementRule {
  from: string;
  to: string;
}

interface BriefingHypothesis {
  id: string;
  text: string;
  support_refs: string[]; // 2 required for validation
  counter_ref: string;    // 1 required for validation
  notes: string;
}

interface AnalysisResponse {
  raw_json: {
    etapa0_observaciones?: string;
    etapa1_resumen?: string;
    etapa2_descriptivo?: {
      impresiones: string;
      lista_codigos_iniciales: string[];
    };
    briefing?: {
      title?: string;
      participants?: string;
      context?: string;
      anonymization_confirmed?: boolean;
      anonymization_level?: AnonymizationLevel;
      replacements?: Record<string, string>;
      hypotheses?: Array<{
        text: string;
        support_refs: string[];
        counter_ref: string;
        notes?: string;
      }>;
      created_at?: string;
      draft?: boolean;
      validated?: boolean;
    };
    etapa3_matriz_abierta?: Array<{ codigo: string; cita: string; fuente: string; tags?: string[] }>;
    etapa4_axial?: Array<{
      categoria: string;
      codigos: string[];
      relaciones: string[];
      memo: string;
    }>;
    etapa5_selectiva?: { nucleo: string; narrativa: string };
    etapa6_transversal?: { convergencias: string; divergencias: string; variaciones: string };
    etapa7_modelo_ascii?: string;
    etapa8_validacion?: {
      saturacion: string;
      triangulacion: string[];
      member_checking: string;
    };
    etapa9_borrador_informe?: string;

    // Sprint 29+: Epistemic-tagged synthesis (additive / backward compatible)
    structured?: boolean;
    memo_statements?: EpistemicStatement[];
  };
  ascii_model: string;
  etapa3_matriz_abierta: Array<{ codigo: string; cita: string; fuente: string; tags?: string[] }>;
  etapa4_axial: Array<any>;
}

interface InterviewOption {
  key: string;
  filename: string;
  statusLabel: string;
}

type InterviewsApiPayload = InterviewOption[] | { interviews: InterviewOption[] } | any;

function normalizeInterviews(payload: InterviewsApiPayload): InterviewOption[] {
  const list = Array.isArray(payload) ? payload : Array.isArray(payload?.interviews) ? payload.interviews : [];
  return list
    .map((item: any, index: number) => {
      if (!item || typeof item !== "object") return null;
      const filename = item.filename || item.archivo;
      if (!filename) return null;
      const key = String(item.id ?? item.filename ?? item.archivo ?? index);
      const status = item.status
        || (typeof item.fragmentos === "number" ? `${item.fragmentos} fragmentos` : "sin estado");
      return { key, filename, statusLabel: status };
    })
    .filter((item: InterviewOption | null): item is InterviewOption => Boolean(item));
}

interface AnalysisPanelProps {
  project: string;
  refreshKey?: number;
}

export function AnalysisPanel({ project, refreshKey }: AnalysisPanelProps) {
  const [interviews, setInterviews] = useState<InterviewOption[]>([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [loadingInterviews, setLoadingInterviews] = useState(false);

  const [briefingTitle, setBriefingTitle] = useState("");
  const [briefingParticipants, setBriefingParticipants] = useState("");
  const [briefingContext, setBriefingContext] = useState("");
  const [briefingAnonymized, setBriefingAnonymized] = useState(false);
  const [showProvisionalCodes, setShowProvisionalCodes] = useState(true);

  const [anonymizationLevel, setAnonymizationLevel] = useState<AnonymizationLevel>("basic");
  const [replacementRules, setReplacementRules] = useState<ReplacementRule[]>([
    { from: "La Florida", to: "Comuna_X" },
    { from: "UV 20", to: "Unidad_Vecinal_XX" },
    { from: "Puente Alto", to: "Comuna_colindante_Y" },
  ]);
  const [anonymizationAppliedAt, setAnonymizationAppliedAt] = useState<string | null>(null);

  const [briefingChecklist, setBriefingChecklist] = useState({
    contextual_anonymization_applied: false,
    non_focal_segments_tagged: false,
    minimal_temporality_present: false,
    actors_generic: false,
    anti_confirmation_check_done: false,
  });

  const [briefingHypotheses, setBriefingHypotheses] = useState<BriefingHypothesis[]>([]);

  const [showNonFocalRows, setShowNonFocalRows] = useState(true);

  const normalizeRef = (value: string): string => (value || "").trim();

  const isHypothesisValid = (h: BriefingHypothesis): boolean => {
    const supports = (h.support_refs || []).map(normalizeRef).filter(Boolean);
    return normalizeRef(h.text).length > 0 && supports.length >= 2 && normalizeRef(h.counter_ref).length > 0;
  };

  const hasHypotheses = briefingHypotheses.length > 0;
  const hypothesesAllValid = briefingHypotheses.every(isHypothesisValid);

  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"summary" | "matrix" | "axial" | "validation">("summary");

  // Sprint 29+: Epistemic-tagged memo rendering (compatible with legacy text)
  const [aiMemoStatements, setAiMemoStatements] = useState<EpistemicStatement[]>([]);
  const [showTaggedMemo, setShowTaggedMemo] = useState(true);
  const [memoTypeFilters, setMemoTypeFilters] = useState<Record<string, boolean>>({
    OBSERVATION: true,
    INTERPRETATION: true,
    HYPOTHESIS: true,
    NORMATIVE_INFERENCE: true,
  });

  const detectPii = (text: string): string[] => {
    const issues: string[] = [];
    const value = (text || "").trim();
    if (!value) return issues;

    // Email
    if (/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i.test(value)) {
      issues.push("email");
    }
    // Phone-ish sequences (very permissive)
    if (/\b\+?\d[\d\s\-().]{7,}\d\b/.test(value)) {
      issues.push("teléfono");
    }
    // Chilean RUT (basic)
    if (/\b\d{1,2}\.\d{3}\.\d{3}-[0-9kK]\b/.test(value) || /\b\d{7,8}-[0-9kK]\b/.test(value)) {
      issues.push("RUT");
    }
    return Array.from(new Set(issues));
  };

  const piiIssues = (() => {
    const issues = new Set<string>();
    const add = (t?: string) => detectPii(t || "").forEach(i => issues.add(i));
    add(briefingTitle);
    add(briefingParticipants);
    add(briefingContext);
    add(result?.raw_json?.etapa0_observaciones);
    add(result?.raw_json?.etapa1_resumen);
    add(result?.raw_json?.etapa2_descriptivo?.impresiones);
    return Array.from(issues);
  })();

  const applyReplacementRules = (text: string, rules: ReplacementRule[]): string => {
    let out = text || "";
    const active = rules
      .map(r => ({ from: (r.from || "").trim(), to: (r.to || "").trim() }))
      .filter(r => r.from.length > 0);
    for (const rule of active) {
      // Replace all occurrences (case-sensitive on purpose: user-provided dictionary)
      out = out.split(rule.from).join(rule.to);
    }
    return out;
  };

  const activeReplacementPairs = (() => {
    const pairs: Array<[string, string]> = [];
    for (const r of replacementRules) {
      const from = (r.from || "").trim();
      if (!from) continue;
      pairs.push([from, (r.to || "").trim()]);
    }
    return pairs;
  })();

  const contextualMatches = (() => {
    if (anonymizationLevel === "basic") return [] as string[];
    const haystack = `${briefingTitle}\n${briefingParticipants}\n${briefingContext}`;
    const matches = new Set<string>();
    for (const [from] of activeReplacementPairs) {
      if (from && haystack.includes(from)) matches.add(from);
    }
    return Array.from(matches);
  })();

  const loadInterviews = async () => {
    setLoadingInterviews(true);
    try {
      // API now returns List[InterviewFileDTO] directly
      const data = await apiFetchJson<any>(
        `/api/interviews?project=${encodeURIComponent(project)}`
      );
      const normalized = normalizeInterviews(data);
      setInterviews(normalized);
      if (normalized.length > 0) {
        setSelectedFile(normalized[0].filename);
      }
    } catch (err) {
      console.error(err);
      setInterviews([]);
    } finally {
      setLoadingInterviews(false);
    }
  };

  useEffect(() => {
    loadInterviews();
  }, [project]);

  // Reload interviews when refreshKey changes (triggered by external events like ingestion)
  useEffect(() => {
    if (refreshKey !== undefined && refreshKey > 0) {
      loadInterviews();
    }
  }, [refreshKey]);

  // Reset briefing fields when interview changes
  useEffect(() => {
    setBriefingTitle(selectedFile ? `Descripción de entrevista: ${selectedFile}` : "");
    setBriefingParticipants("");
    setBriefingContext("");
    setBriefingAnonymized(false);
    setShowProvisionalCodes(true);
    setAnonymizationLevel("basic");
    setAnonymizationAppliedAt(null);
    setBriefingChecklist({
      contextual_anonymization_applied: false,
      non_focal_segments_tagged: false,
      minimal_temporality_present: false,
      actors_generic: false,
      anti_confirmation_check_done: false,
    });
    setBriefingHypotheses([]);
    setShowNonFocalRows(true);
  }, [selectedFile]);

  // Auto-sync checklist flag: if at least one Matriz Abierta row is marked non-focal
  useEffect(() => {
    const rows = result?.etapa3_matriz_abierta || [];
    const hasNonFocal = rows.some(r => (r.tags || []).includes("contexto_organizacional"));
    setBriefingChecklist(prev => {
      if (prev.non_focal_segments_tagged === hasNonFocal) return prev;
      return { ...prev, non_focal_segments_tagged: hasNonFocal };
    });
  }, [result?.etapa3_matriz_abierta]);

  const handleApplyAnonymization = () => {
    if (anonymizationLevel === "basic") {
      setAnonymizationAppliedAt(new Date().toISOString());
      return;
    }

    const nextTitle = applyReplacementRules(briefingTitle, replacementRules);
    const nextParticipants = applyReplacementRules(briefingParticipants, replacementRules);
    const nextContext = applyReplacementRules(briefingContext, replacementRules);

    setBriefingTitle(nextTitle);
    setBriefingParticipants(nextParticipants);
    setBriefingContext(nextContext);
    setAnonymizationAppliedAt(new Date().toISOString());

    setBriefingChecklist(prev => ({
      ...prev,
      contextual_anonymization_applied: true,
    }));
  };

  const handleDeleteFile = async () => {
    if (!selectedFile) return;
    if (!confirm(`¿Estás seguro de que quieres eliminar TODOS los datos de "${selectedFile}"?\n\nEsta acción borrará fragmentos, códigos y nodos en todas las bases de datos.\n\nNo se puede deshacer.`)) {
      return;
    }

    setAnalyzing(true); // Reuse analyzing state to block UI
    try {
      await deleteFileData(project, selectedFile);
      alert(`Datos de "${selectedFile}" eliminados correctamente.`);
      setResult(null);
      // Reload interviews to refresh the list if needed, though file might still be in the list if not deleted from disk
      // Ideally we should remove it from the list if it has 0 fragments now, but the API returns files with fragments.
      // Let's trigger a reload.
      const data = await apiFetchJson<any>(
        `/api/interviews?project=${encodeURIComponent(project)}`
      );
      const normalized = normalizeInterviews(data);
      setInterviews(normalized);
      if (normalized.length > 0) {
        setSelectedFile(normalized[0].filename);
      } else {
        setSelectedFile("");
      }

    } catch (err: any) {
      alert(`Error al eliminar: ${err.message}`);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleAnalyze = async () => {
    if (!selectedFile) return;
    setAnalyzing(true);
    setError(null);
    setResult(null);
    setAiMemoStatements([]);

    try {
      // Call analyze endpoint with sync=true (default)
      const startResponse = await apiFetchJson<{ task_id?: string; status: string; result?: any }>("/api/analyze", {
        method: "POST",
        body: JSON.stringify({
          project,
          docx_path: `data/interviews/${selectedFile}`,
          persist: false,
          sync: true  // Execute synchronously
        })
      });

      // Handle synchronous response (sync=true)
      if (startResponse.status === "success" && startResponse.result) {
        const flatResult = startResponse.result;
        const structuredResult: AnalysisResponse = {
          raw_json: flatResult,
          ascii_model: flatResult.etapa7_modelo_ascii || "",
          etapa3_matriz_abierta: flatResult.etapa3_matriz_abierta || [],
          etapa4_axial: flatResult.etapa4_axial || []
        };
        setAiMemoStatements(Array.isArray((flatResult as any).memo_statements) ? ((flatResult as any).memo_statements as EpistemicStatement[]) : []);
        setResult(structuredResult);
        setAnalyzing(false);
        return;
      }

      // Handle async response (sync=false) - polling fallback
      const { task_id } = startResponse;
      if (!task_id) {
        setError("No se recibió un ID de tarea válido");
        setAnalyzing(false);
        return;
      }

      // 2. Poll for results
      let attempts = 0;
      const MAX_ATTEMPTS = 120; // 2 minutes (assuming 1s interval)

      const poll = async () => {
        if (attempts >= MAX_ATTEMPTS) {
          setError("Tiempo de espera agotado. El análisis sigue en segundo plano.");
          setAnalyzing(false);
          return;
        }

        try {
          const statusDetails = await apiFetchJson<{ status: string; result: any }>(`/api/tasks/${task_id}`);

          if (statusDetails.status === 'SUCCESS') {
            const flatResult = statusDetails.result;
            // Wrap flat JSON into the structure expected by this component
            const structuredResult: AnalysisResponse = {
              raw_json: flatResult,
              ascii_model: flatResult.etapa7_modelo_ascii || "",
              etapa3_matriz_abierta: flatResult.etapa3_matriz_abierta || [],
              etapa4_axial: flatResult.etapa4_axial || []
            };
            setAiMemoStatements(Array.isArray((flatResult as any).memo_statements) ? ((flatResult as any).memo_statements as EpistemicStatement[]) : []);
            setResult(structuredResult);
            setAnalyzing(false);
          } else if (statusDetails.status === 'FAILURE' || statusDetails.status === 'REVOKED') {
            setError(`Falló la tarea de análisis: ${statusDetails.status}`);
            setAnalyzing(false);
          } else {
            // PENDING, STARTED, RETRY... keep waiting
            attempts++;
            setTimeout(poll, 1000);
          }
        } catch (pollError) {
          console.error(pollError);
          setError("Error consultando el estado de la tarea.");
          setAnalyzing(false);
        }
      };

      // Start polling
      setTimeout(poll, 1000);

    } catch (err: any) {
      setError(err.message || "Error al iniciar el análisis");
      setAnalyzing(false);
    }
  };

  const handleSave = async (mode: "draft" | "validated") => {
    if (!result || !selectedFile) return;
    if (piiIssues.length > 0 && !briefingAnonymized) {
      setError(
        `Antes de guardar: anonimiza datos sensibles. Posibles PII detectados: ${piiIssues.join(", ")}. ` +
        `Marca “Anonimización confirmada” para continuar.`
      );
      return;
    }

    if (anonymizationLevel !== "basic" && contextualMatches.length > 0) {
      setError(
        `Anonimización contextual pendiente. Aún hay coincidencias sin reemplazar: ${contextualMatches.join(", ")}. ` +
        `Aplica el diccionario o ajusta los campos antes de guardar.`
      );
      return;
    }

    if (mode === "validated") {
      const missing = Object.entries(briefingChecklist)
        .filter(([, v]) => !v)
        .map(([k]) => k);
      if (missing.length > 0) {
        setError(
          `No se puede guardar como validado. Checklist incompleto: ${missing.join(", ")}.`
        );
        return;
      }

      if (hasHypotheses && !hypothesesAllValid) {
        setError(
          "No se puede guardar como validado. Cada hipótesis requiere texto + 2 evidencias de apoyo + 1 contra-evidencia."
        );
        return;
      }
    }

    setSaving(true);
    setError(null);
    try {
      const replacements: Record<string, string> = {};
      for (const r of replacementRules) {
        const from = (r.from || "").trim();
        if (!from) continue;
        replacements[from] = (r.to || "").trim();
      }

      await apiFetchJson("/api/analyze/persist", {
        method: "POST",
        body: JSON.stringify({
          project,
          archivo: selectedFile,
          analysis_result: {
            ...result.raw_json,
            briefing: {
              title: briefingTitle,
              participants: briefingParticipants,
              context: briefingContext,
              anonymization_confirmed: briefingAnonymized,
              anonymization_level: anonymizationLevel,
              replacements,
              anonymization_applied_at: anonymizationAppliedAt,
              created_at: new Date().toISOString(),
              draft: mode === "draft",
              validated: mode === "validated",
              checklist: briefingChecklist,
              hypotheses: briefingHypotheses.map(h => ({
                text: normalizeRef(h.text),
                support_refs: (h.support_refs || []).map(normalizeRef).filter(Boolean).slice(0, 3),
                counter_ref: normalizeRef(h.counter_ref),
                notes: normalizeRef(h.notes) || undefined,
              }))
            }
          }
        })
      });
      alert(
        mode === "validated"
          ? "Briefing guardado como VALIDADO."
          : "Briefing guardado como borrador."
      );
    } catch (err: any) {
      setError(err.message || "Error al guardar el análisis");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRow = (index: number) => {
    if (!result) return;
    const newMatrix = [...(result.etapa3_matriz_abierta || [])];
    newMatrix.splice(index, 1);

    // Update both the top-level property and the raw_json to keep them in sync
    const newRawJson = { ...result.raw_json };
    newRawJson.etapa3_matriz_abierta = newMatrix;

    setResult({
      ...result,
      etapa3_matriz_abierta: newMatrix,
      raw_json: newRawJson
    });
  };

  const toggleMatrixRowTag = (index: number, tag: string) => {
    if (!result) return;
    const newMatrix = [...(result.etapa3_matriz_abierta || [])];
    const row = { ...newMatrix[index] };
    const tags = Array.from(new Set([...(row.tags || [])]));
    const nextTags = tags.includes(tag) ? tags.filter(t => t !== tag) : [...tags, tag];
    row.tags = nextTags;
    newMatrix[index] = row;

    const newRawJson = { ...result.raw_json };
    newRawJson.etapa3_matriz_abierta = newMatrix;

    setResult({
      ...result,
      etapa3_matriz_abierta: newMatrix,
      raw_json: newRawJson
    });
  };

  if (loadingInterviews && interviews.length === 0) return <div className="p-4 text-gray-500">Cargando entrevistas...</div>;

  return (
    <div className="my-8 border rounded-lg bg-white shadow-sm overflow-hidden">
      <div className="bg-indigo-50 px-6 py-4 border-b border-indigo-100">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="text-xl font-semibold text-indigo-900">Descripción de Entrevista (Briefing IA)</h2>
          <span className="text-xs font-medium px-2 py-1 rounded bg-amber-100 text-amber-900 border border-amber-200">
            Borrador IA — no validado
          </span>
        </div>
        <p className="text-sm text-indigo-700 mt-1">
          Prepara contexto para informe: resumen, diagnóstico y conceptos provisorios. Revisa y anonimiza antes de guardar.
        </p>
      </div>

      <div className="p-6">
        <div className="mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Título/etiqueta</label>
            <input
              className="border rounded px-3 py-2 w-full"
              value={briefingTitle}
              onChange={(e) => setBriefingTitle(e.target.value)}
              placeholder="Ej: Entrevista con dirigenta vecinal (UV 20)"
            />
          </div>
          <div className="md:col-span-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Entrevistados/actores (para anonimizar)</label>
            <input
              className="border rounded px-3 py-2 w-full"
              value={briefingParticipants}
              onChange={(e) => setBriefingParticipants(e.target.value)}
              placeholder="Ej: [DIRIGENTA_1], [VECINO_2] (no escribir nombres reales)"
            />
          </div>
          <div className="md:col-span-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">Contexto breve (para informe)</label>
            <input
              className="border rounded px-3 py-2 w-full"
              value={briefingContext}
              onChange={(e) => setBriefingContext(e.target.value)}
              placeholder="Lugar/fecha/tipo entrevista, condiciones, observaciones"
            />
          </div>
        </div>

        <div className="mb-6 p-4 rounded border bg-white">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <div className="text-sm font-semibold text-gray-900">Anonimización</div>
              <div className="text-xs text-gray-500">
                Recomendación: usar anonimización contextual para informes.
              </div>
            </div>
            {anonymizationAppliedAt && (
              <div className="text-xs text-gray-500">Aplicada: {new Date(anonymizationAppliedAt).toLocaleString()}</div>
            )}
          </div>

          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nivel</label>
              <select
                className="border rounded px-3 py-2 w-full"
                value={anonymizationLevel}
                onChange={(e) => setAnonymizationLevel(e.target.value as AnonymizationLevel)}
              >
                <option value="basic">Básica (PII explícita)</option>
                <option value="contextual">Contextual (lugares/organizaciones/roles)</option>
                <option value="total">Total (publicación)</option>
              </select>
            </div>

            <div className="md:col-span-2">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <label className="block text-sm font-medium text-gray-700">Diccionario de reemplazos</label>
                <button
                  type="button"
                  onClick={() => setReplacementRules([...replacementRules, { from: "", to: "" }])}
                  className="text-sm text-indigo-700 hover:text-indigo-900 underline"
                >
                  + Agregar
                </button>
              </div>

              <div className="mt-2 space-y-2">
                {replacementRules.map((r, idx) => (
                  <div key={idx} className="grid grid-cols-1 md:grid-cols-7 gap-2 items-center">
                    <input
                      className="border rounded px-2 py-1 md:col-span-3"
                      value={r.from}
                      onChange={(e) => {
                        const next = [...replacementRules];
                        next[idx] = { ...next[idx], from: e.target.value };
                        setReplacementRules(next);
                      }}
                      placeholder="Buscar (ej: La Florida)"
                    />
                    <div className="text-center text-gray-400 md:col-span-1">→</div>
                    <input
                      className="border rounded px-2 py-1 md:col-span-3"
                      value={r.to}
                      onChange={(e) => {
                        const next = [...replacementRules];
                        next[idx] = { ...next[idx], to: e.target.value };
                        setReplacementRules(next);
                      }}
                      placeholder="Reemplazar por (ej: Comuna_X)"
                    />
                    <button
                      type="button"
                      onClick={() => setReplacementRules(replacementRules.filter((_, i) => i !== idx))}
                      className="text-xs text-red-700 hover:text-red-900 underline"
                      title="Eliminar regla"
                    >
                      Eliminar
                    </button>
                  </div>
                ))}
              </div>

              <div className="mt-3 flex items-center gap-3 flex-wrap">
                <button
                  type="button"
                  onClick={handleApplyAnonymization}
                  className="px-3 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                  disabled={anonymizationLevel === "basic"}
                >
                  Aplicar anonimización
                </button>
                {anonymizationLevel !== "basic" && contextualMatches.length > 0 && (
                  <span className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                    Coincidencias sin anonimizar: {contextualMatches.join(", ")}
                  </span>
                )}
                {anonymizationLevel !== "basic" && contextualMatches.length === 0 && (
                  <span className="text-xs text-gray-500">No se detectan coincidencias del diccionario en el briefing.</span>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 border-t pt-4">
            <div className="text-sm font-semibold text-gray-900 mb-2">Checklist pre-guardado</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={briefingChecklist.contextual_anonymization_applied}
                  onChange={(e) => setBriefingChecklist(prev => ({ ...prev, contextual_anonymization_applied: e.target.checked }))}
                  disabled={anonymizationLevel === "basic"}
                />
                Anonimización contextual aplicada
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={briefingChecklist.non_focal_segments_tagged}
                  onChange={() => { /* auto-driven by Matriz Abierta tags */ }}
                  disabled
                />
                Segmentos no focales etiquetados
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={briefingChecklist.minimal_temporality_present}
                  onChange={(e) => setBriefingChecklist(prev => ({ ...prev, minimal_temporality_present: e.target.checked }))}
                />
                Temporalidad mínima establecida
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={briefingChecklist.actors_generic}
                  onChange={(e) => setBriefingChecklist(prev => ({ ...prev, actors_generic: e.target.checked }))}
                />
                Actores institucionales genéricos
              </label>
              <label className="flex items-center gap-2 text-sm md:col-span-2">
                <input
                  type="checkbox"
                  checked={briefingChecklist.anti_confirmation_check_done}
                  onChange={(e) => setBriefingChecklist(prev => ({ ...prev, anti_confirmation_check_done: e.target.checked }))}
                />
                Búsqueda explícita de matices/contra-evidencia (anti-sesgo)
              </label>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              “Guardar como validado” exige checklist completo. “Guardar borrador” solo exige anonimización confirmada si hay PII y que no queden coincidencias del diccionario.
            </p>
          </div>

          <div className="mt-4 border-t pt-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <div className="text-sm font-semibold text-gray-900">Hipótesis (borrador) con evidencia</div>
                <div className="text-xs text-gray-500">
                  Para validar: cada hipótesis requiere 2 apoyos + 1 contra.
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  const id = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
                  setBriefingHypotheses([
                    ...briefingHypotheses,
                    { id, text: "", support_refs: ["", ""], counter_ref: "", notes: "" }
                  ]);
                }}
                className="text-sm text-indigo-700 hover:text-indigo-900 underline"
              >
                + Agregar hipótesis
              </button>
            </div>

            {briefingHypotheses.length === 0 ? (
              <div className="mt-2 text-sm text-gray-600">
                (Opcional) Útil si quieres que “validado” sea más riguroso.
              </div>
            ) : (
              <div className="mt-3 space-y-3">
                {briefingHypotheses.map((h, idx) => {
                  const ok = isHypothesisValid(h);
                  return (
                    <div key={h.id} className={`p-3 rounded border ${ok ? "bg-white" : "bg-amber-50 border-amber-200"}`}>
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="text-sm font-semibold text-gray-800">Hipótesis {idx + 1}</div>
                        <button
                          type="button"
                          onClick={() => setBriefingHypotheses(briefingHypotheses.filter(x => x.id !== h.id))}
                          className="text-xs text-red-700 hover:text-red-900 underline"
                        >
                          Eliminar
                        </button>
                      </div>

                      <div className="mt-2">
                        <label className="block text-sm font-medium text-gray-700 mb-1">Texto</label>
                        <input
                          className="border rounded px-3 py-2 w-full"
                          value={h.text}
                          onChange={(e) => {
                            const next = [...briefingHypotheses];
                            next[idx] = { ...next[idx], text: e.target.value };
                            setBriefingHypotheses(next);
                          }}
                          placeholder="Ej: La desconfianza institucional se construye sobre obras mal ejecutadas"
                        />
                      </div>

                      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Apoyo 1</label>
                          <input
                            list="matrixRefs"
                            className="border rounded px-3 py-2 w-full"
                            value={h.support_refs[0] || ""}
                            onChange={(e) => {
                              const next = [...briefingHypotheses];
                              const supports = [...(next[idx].support_refs || [])];
                              supports[0] = e.target.value;
                              next[idx] = { ...next[idx], support_refs: supports };
                              setBriefingHypotheses(next);
                            }}
                            placeholder="Elegir evidencia (fuente/cita)"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Apoyo 2</label>
                          <input
                            list="matrixRefs"
                            className="border rounded px-3 py-2 w-full"
                            value={h.support_refs[1] || ""}
                            onChange={(e) => {
                              const next = [...briefingHypotheses];
                              const supports = [...(next[idx].support_refs || [])];
                              supports[1] = e.target.value;
                              next[idx] = { ...next[idx], support_refs: supports };
                              setBriefingHypotheses(next);
                            }}
                            placeholder="Elegir evidencia (fuente/cita)"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Contra-evidencia</label>
                          <input
                            list="matrixRefs"
                            className="border rounded px-3 py-2 w-full"
                            value={h.counter_ref}
                            onChange={(e) => {
                              const next = [...briefingHypotheses];
                              next[idx] = { ...next[idx], counter_ref: e.target.value };
                              setBriefingHypotheses(next);
                            }}
                            placeholder="Elegir evidencia que matice/contradiga"
                          />
                        </div>
                      </div>

                      <div className="mt-3">
                        <label className="block text-sm font-medium text-gray-700 mb-1">Notas</label>
                        <input
                          className="border rounded px-3 py-2 w-full"
                          value={h.notes}
                          onChange={(e) => {
                            const next = [...briefingHypotheses];
                            next[idx] = { ...next[idx], notes: e.target.value };
                            setBriefingHypotheses(next);
                          }}
                          placeholder="Qué buscar en codificación / matices / preguntas"
                        />
                      </div>

                      {!ok && (
                        <div className="mt-2 text-xs text-amber-900">
                          Para validar: completa texto + 2 apoyos + 1 contra.
                        </div>
                      )}
                    </div>
                  );
                })}

                <datalist id="matrixRefs">
                  {(result?.etapa3_matriz_abierta || []).slice(0, 200).map((row, i) => {
                    const ref = `${row.fuente} — ${row.codigo}`;
                    return <option key={i} value={ref} />;
                  })}
                </datalist>
              </div>
            )}
          </div>
        </div>

        {piiIssues.length > 0 && (
          <div className="p-4 mb-6 bg-amber-50 text-amber-900 rounded border border-amber-200">
            <div className="font-semibold mb-1">Posibles datos sensibles detectados</div>
            <div className="text-sm">Se detectó: {piiIssues.join(", ")}. Anonimiza antes de guardar.</div>
            <label className="mt-3 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={briefingAnonymized}
                onChange={(e) => setBriefingAnonymized(e.target.checked)}
              />
              Anonimización confirmada
            </label>
          </div>
        )}

        <div className="flex flex-wrap gap-4 items-end mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Entrevista</label>
            <select
              className="border rounded px-3 py-2 min-w-[300px]"
              value={selectedFile}
              onChange={(e) => setSelectedFile(e.target.value)}
            >
              {interviews.map((i) => (
                <option key={i.key} value={i.filename}>
                  {i.filename} ({i.statusLabel})
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={handleAnalyze}
            disabled={analyzing || !selectedFile}
            className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {analyzing ? "Analizando..." : "Ejecutar Análisis (Etapas 0-4)"}
          </button>

          <button
            onClick={handleDeleteFile}
            disabled={analyzing || !selectedFile}
            className="px-4 py-2 bg-red-100 text-red-700 border border-red-200 rounded hover:bg-red-200 disabled:opacity-50 transition-colors ml-2"
            title="Eliminar todos los datos de este archivo (Postgres, Neo4j, Qdrant)"
          >
            Eliminar Datos
          </button>

          {result && (
            <div className="ml-auto flex items-center gap-2 flex-wrap">
              <button
                onClick={() => handleSave("draft")}
                disabled={
                  saving ||
                  (piiIssues.length > 0 && !briefingAnonymized) ||
                  (anonymizationLevel !== "basic" && contextualMatches.length > 0)
                }
                className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 transition-colors"
              >
                {saving ? "Guardando..." : "Guardar borrador"}
              </button>
              <button
                onClick={() => handleSave("validated")}
                disabled={
                  saving ||
                  (piiIssues.length > 0 && !briefingAnonymized) ||
                  (anonymizationLevel !== "basic" && contextualMatches.length > 0) ||
                  Object.values(briefingChecklist).some(v => !v) ||
                  (hasHypotheses && !hypothesesAllValid)
                }
                className="px-4 py-2 bg-emerald-700 text-white rounded hover:bg-emerald-800 disabled:opacity-50 transition-colors"
                title="Requiere checklist completo"
              >
                {saving ? "Guardando..." : "Guardar validado"}
              </button>
            </div>
          )}
        </div>

        {error && (
          <div className="p-4 mb-6 bg-red-50 text-red-700 rounded border border-red-200">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-6">
            <div className="flex border-b mb-4">
              {[
                { id: "summary", label: "Resumen y Diagnóstico" },
                { id: "matrix", label: "Matriz Abierta" },
                { id: "axial", label: "Modelo Axial" },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`px-4 py-2 border-b-2 font-medium text-sm ${activeTab === tab.id
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                    }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="bg-gray-50 p-4 rounded border min-h-[400px]">
              {activeTab === "summary" && (
                <div className="space-y-6">
                  {aiMemoStatements.length > 0 && (
                    <section>
                      <div className="bg-white p-3 rounded border border-purple-200">
                        <div className="flex items-center gap-3 flex-wrap">
                          <h3 className="font-bold text-purple-900">Estatus epistemológico</h3>
                          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                            <input
                              type="checkbox"
                              checked={showTaggedMemo}
                              onChange={(e) => setShowTaggedMemo(e.target.checked)}
                            />
                            Mostrar etiquetado
                          </label>
                          <span className="text-xs text-purple-800">
                            (OBSERVATION requiere evidencia: IDs de fragmento)
                          </span>
                        </div>

                        <div className="flex gap-2 flex-wrap mt-3">
                          {["OBSERVATION", "INTERPRETATION", "HYPOTHESIS", "NORMATIVE_INFERENCE"].map((t) => (
                            <label
                              key={t}
                              className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-purple-100 bg-white text-sm"
                            >
                              <input
                                type="checkbox"
                                checked={Boolean(memoTypeFilters[t])}
                                onChange={(e) =>
                                  setMemoTypeFilters((prev) => ({
                                    ...prev,
                                    [t]: e.target.checked,
                                  }))
                                }
                              />
                              <span style={memoBadgeStyle(t)}>{t}</span>
                            </label>
                          ))}
                        </div>

                        {showTaggedMemo && (
                          <div className="flex flex-col gap-2 mt-3">
                            {aiMemoStatements
                              .filter((s) => memoTypeFilters[(s.type || "").toUpperCase()] !== false)
                              .map((s, idx) => {
                                const type = (s.type || "").toUpperCase();
                                const evid = Array.isArray(s.evidence_ids)
                                  ? s.evidence_ids.filter((n) => typeof n === "number" && Number.isFinite(n))
                                  : [];
                                return (
                                  <div
                                    key={`${type}-${idx}`}
                                    className="flex gap-3 items-start p-3 bg-gray-50 rounded border"
                                  >
                                    <div className="pt-0.5">
                                      <span style={memoBadgeStyle(type)}>{type}</span>
                                    </div>
                                    <div className="flex-1">
                                      <div className="text-sm text-gray-900 whitespace-pre-wrap">{s.text}</div>
                                      {evid.length > 0 && (
                                        <div className="mt-1 text-xs text-gray-500">
                                          Evidencia (IDs fragmento): {evid.join(", ")}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                          </div>
                        )}
                      </div>
                    </section>
                  )}
                  <section>
                    <h3 className="font-bold text-gray-900 mb-2">Etapa 0: Observaciones</h3>
                    <p className="text-gray-700 whitespace-pre-wrap">{result.raw_json.etapa0_observaciones || "Sin observaciones."}</p>
                  </section>
                  <section>
                    <h3 className="font-bold text-gray-900 mb-2">Etapa 1: Resumen</h3>
                    <p className="text-gray-700 whitespace-pre-wrap">{result.raw_json.etapa1_resumen || "Sin resumen."}</p>
                  </section>
                  <section>
                    <h3 className="font-bold text-gray-900 mb-2">Etapa 2: Descriptivo Inicial</h3>
                    <div className="bg-white p-3 rounded border">
                      <p className="mb-2"><strong>Impresiones:</strong> {result.raw_json.etapa2_descriptivo?.impresiones}</p>
                      <div className="mt-3">
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                          <strong>Conceptos provisorios (IA)</strong>
                          <button
                            type="button"
                            onClick={() => setShowProvisionalCodes(!showProvisionalCodes)}
                            className="text-sm text-indigo-700 hover:text-indigo-900 underline"
                          >
                            {showProvisionalCodes ? "Ocultar" : "Mostrar"}
                          </button>
                        </div>
                        {showProvisionalCodes && (
                          <div className="flex flex-wrap gap-2 mt-1">
                            {result.raw_json.etapa2_descriptivo?.lista_codigos_iniciales?.map((c, i) => (
                              <span key={i} className="px-2 py-1 bg-gray-200 rounded text-xs">{c}</span>
                            ))}
                          </div>
                        )}
                        <p className="text-xs text-gray-500 mt-2">
                          Sugerencias de IA para orientar muestreo/lectura. No equivalen a códigos validados.
                        </p>
                      </div>
                    </div>
                  </section>
                </div>
              )}

              {activeTab === "matrix" && (
                <div className="overflow-x-auto">
                  {(() => {
                    const rows = result.etapa3_matriz_abierta || [];
                    const nonFocal = rows.filter(r => (r.tags || []).includes("contexto_organizacional")).length;
                    const nucleus = rows.length - nonFocal;
                    return (
                      <div className="mb-3 flex items-center justify-between gap-3 flex-wrap">
                        <div className="text-sm text-gray-700">
                          <span className="font-semibold">Núcleo:</span> {nucleus} &nbsp;|&nbsp; <span className="font-semibold">No focal:</span> {nonFocal}
                        </div>
                        <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                          <input
                            type="checkbox"
                            checked={showNonFocalRows}
                            onChange={(e) => setShowNonFocalRows(e.target.checked)}
                          />
                          Mostrar no focal (contexto_organizacional)
                        </label>
                      </div>
                    );
                  })()}
                  <table className="min-w-full bg-white border text-sm">
                    <thead className="bg-gray-100">
                      <tr>
                        <th className="px-4 py-2 text-left">Código</th>
                        <th className="px-4 py-2 text-left">Cita</th>
                        <th className="px-4 py-2 text-left">Fuente</th>
                        <th className="px-4 py-2 text-left">Etiqueta</th>
                        <th className="px-4 py-2 text-center w-20">Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(result.etapa3_matriz_abierta || [])
                        .map((row, idx) => ({ row, idx }))
                        .filter(({ row }) => {
                          const isNonFocal = (row.tags || []).includes("contexto_organizacional");
                          return showNonFocalRows ? true : !isNonFocal;
                        })
                        .map(({ row, idx }) => (
                          <tr key={idx} className={`border-t hover:bg-gray-50 ${(row.tags || []).includes("contexto_organizacional") ? "bg-amber-50/40" : ""}`}>
                            <td className="px-4 py-2 font-medium text-indigo-700">{row.codigo}</td>
                            <td className="px-4 py-2 text-gray-600 italic">"{row.cita}"</td>
                            <td className="px-4 py-2">{row.fuente}</td>
                            <td className="px-4 py-2">
                              <label className="inline-flex items-center gap-2 text-xs text-gray-700">
                                <input
                                  type="checkbox"
                                  checked={(row.tags || []).includes("contexto_organizacional")}
                                  onChange={() => toggleMatrixRowTag(idx, "contexto_organizacional")}
                                />
                                contexto_organizacional (no focal)
                              </label>
                            </td>
                            <td className="px-4 py-2 text-center">
                              <button
                                onClick={() => handleDeleteRow(idx)}
                                className="text-red-500 hover:text-red-700 p-1 rounded hover:bg-red-50"
                                title="Eliminar código"
                              >
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                              </svg>
                              </button>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}

              {activeTab === "axial" && (
                <div className="space-y-6">
                  <section>
                    <h3 className="font-bold text-gray-900 mb-2">Modelo ASCII</h3>
                    <pre className="bg-gray-900 text-green-400 p-4 rounded overflow-x-auto font-mono text-xs leading-relaxed">
                      {result.ascii_model}
                    </pre>
                  </section>
                  <section>
                    <h3 className="font-bold text-gray-900 mb-2">Categorías Axiales</h3>
                    <div className="grid gap-4 md:grid-cols-2">
                      {result.raw_json.etapa4_axial?.map((cat, idx) => (
                        <div key={idx} className="bg-white p-3 rounded border shadow-sm">
                          <h4 className="font-bold text-indigo-800">{cat.categoria}</h4>
                          <p className="text-xs text-gray-500 mt-1 mb-2">{cat.memo}</p>
                          <div className="mb-2">
                            <span className="text-xs font-semibold text-gray-600">Códigos:</span>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {cat.codigos?.map((c, i) => (
                                <span key={i} className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 rounded text-xs border border-indigo-100">{c}</span>
                              ))}
                            </div>
                          </div>
                          {cat.relaciones && cat.relaciones.length > 0 && (
                            <div>
                              <span className="text-xs font-semibold text-gray-600">Relaciones:</span>
                              <ul className="list-disc list-inside text-xs text-gray-700 mt-1">
                                {cat.relaciones.map((r, i) => <li key={i}>{r}</li>)}
                              </ul>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </section>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
