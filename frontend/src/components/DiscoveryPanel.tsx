/**
 * @fileoverview Panel de Discovery - Busqueda Exploratoria.
 *
 * Este componente permite busquedas con triplete positivo/negativo/target
 * para encontrar fragmentos conceptualmente relacionados.
 *
 * @module components/DiscoveryPanel
 */

import React, { useEffect, useState, useCallback, useRef } from "react";
import { apiFetchJson, discoverSearch, saveDiscoveryMemo, analyzeDiscovery, submitCandidate, checkBatchCodes, logDiscoveryNavigation, BatchCheckResult, DiscoverResponse, EpistemicStatement } from "../services/api";

interface AgentExecuteResponse {
  task_id: string;
  status?: string;
  message?: string;
}

interface AgentStatusResponse {
  task_id: string;
  status: "pending" | "running" | "completed" | "error";
  current_stage: number;
  iteration: number;
  memos_count: number;
  codes_count: number;
  errors?: string[];
  final_landing_rate?: {
    landing_rate: number;
    matched_count: number;
    total_count: number;
    matched_codes?: string[];
    project_open_code_rows?: number;
    reason?: "no_fragments" | "no_definitive_codes" | "no_overlap_with_definitive_codes" | "ok" | string;
  };
  post_run?: {
    report_path?: string;
    structured?: boolean;
    analysis?: string;
    codes_suggested?: string[];
    codes_inserted?: number;
    sample_fragments_count?: number;
  };
  message?: string;
}

interface DiscoveryPanelProps {
  project: string;
  onSelectFragment?: (fragmentId: string, fragmentText: string) => void;
}

export function DiscoveryPanel({ project, onSelectFragment }: DiscoveryPanelProps) {
  const [positiveText, setPositiveText] = useState("");
  const [negativeText, setNegativeText] = useState("");
  const [targetText, setTargetText] = useState("");
  const [topK, setTopK] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<DiscoverResponse | null>(null);

  // AI Analysis state
  const [aiAnalysis, setAiAnalysis] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  // Memo save state (explicit UX so it doesn't look like "nothing happens")
  const [memoSaving, setMemoSaving] = useState(false);
  const [memoSavedPath, setMemoSavedPath] = useState<string | null>(null);
  const [memoSaveError, setMemoSaveError] = useState<string | null>(null);

  // Sprint 22: Structured AI response
  const [aiStructured, setAiStructured] = useState(false);
  const [aiCodigos, setAiCodigos] = useState<string[]>([]);
  const [aiMemoStatements, setAiMemoStatements] = useState<EpistemicStatement[]>([]);
  const [showTaggedMemo, setShowTaggedMemo] = useState(true);
  const [memoTypeFilters, setMemoTypeFilters] = useState<Record<string, boolean>>({
    OBSERVATION: true,
    INTERPRETATION: true,
    HYPOTHESIS: true,
    NORMATIVE_INFERENCE: true,
  });
  const [aiRefinamientos, setAiRefinamientos] = useState<{
    positivos: string[];
    negativos: string[];
    target: string;
  } | null>(null);
  const [sendingCodes, setSendingCodes] = useState(false);

  // Sprint 23: Pre-hoc deduplication modal
  const [showDedupModal, setShowDedupModal] = useState(false);
  const [dedupResults, setDedupResults] = useState<BatchCheckResult[]>([]);
  const [codesToSend, setCodesToSend] = useState<string[]>([]);

  // Sprint 24: Navigation tracking
  const [currentBusquedaId, setCurrentBusquedaId] = useState<string | null>(null);

  // Sprint 25: UX improvements for refinements
  const formRef = useRef<HTMLDivElement>(null);
  const [showRefinementToast, setShowRefinementToast] = useState(false);
  const [highlightForm, setHighlightForm] = useState(false);

  // Sprint 29: Runner (automated Discovery) from UI
  const [runnerTask, setRunnerTask] = useState<AgentStatusResponse | null>(null);
  const [runnerLoading, setRunnerLoading] = useState(false);
  const [runnerError, setRunnerError] = useState<string | null>(null);
  const runnerIntervalRef = useRef<number | null>(null);
  const pollFailCountRef = useRef<number>(0); // Sprint 30: Track consecutive poll failures

  const clearRunnerInterval = useCallback(() => {
    if (runnerIntervalRef.current) {
      window.clearInterval(runnerIntervalRef.current);
      runnerIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearRunnerInterval();
    };
  }, [clearRunnerInterval]);

  const handleSearch = useCallback(async () => {
    const positives = positiveText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (positives.length === 0) {
      setError("Ingresa al menos un concepto positivo");
      return;
    }

    const negatives = negativeText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);

    setLoading(true);
    setError(null);
    setAiAnalysis(null); // Clear previous analysis

    try {
      const result = await discoverSearch({
        positive_texts: positives,
        negative_texts: negatives.length > 0 ? negatives : undefined,
        target_text: targetText.trim() || undefined,
        top_k: topK,
        project,
      });
      setResponse(result);

      // Sprint 24: Log search navigation
      try {
        const navResult = await logDiscoveryNavigation({
          project,
          positivos: positives,
          negativos: negatives,
          target_text: targetText.trim() || null,
          fragments_count: result.count,
          action_taken: "search",
          busqueda_origen_id: currentBusquedaId || undefined,
        });
        setCurrentBusquedaId(navResult.busqueda_id);
      } catch (navErr) {
        console.warn("Navigation log failed:", navErr);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }, [positiveText, negativeText, targetText, topK, project, currentBusquedaId]);

  const pollRunnerStatus = useCallback(async (taskId: string) => {
    try {
      const status = await apiFetchJson<AgentStatusResponse>(`/api/agent/status/${taskId}`);
      pollFailCountRef.current = 0; // Reset on success
      setRunnerTask(status);

      if (status.status === "completed" || status.status === "error") {
        clearRunnerInterval();
        setRunnerLoading(false);
        if (status.status === "error") {
          setRunnerError(status.message || "Error durante ejecución del runner");
        }
      }
    } catch (err) {
      pollFailCountRef.current += 1;
      console.warn(`Runner poll failed (${pollFailCountRef.current}/3):`, err);

      // Sprint 30: After 3 consecutive failures, stop polling and show error
      if (pollFailCountRef.current >= 3) {
        clearRunnerInterval();
        setRunnerLoading(false);
        setRunnerError(
          "⚠️ Conexión perdida con el servidor. " +
          (err instanceof Error ? err.message : "Verifica que el backend esté activo.")
        );
      }
    }
  }, [clearRunnerInterval]);

  const handleRunDiscoveryRunner = useCallback(async () => {
    if (!project) {
      setRunnerError("Selecciona un proyecto primero");
      return;
    }

    const positives = positiveText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (positives.length === 0) {
      setRunnerError("Ingresa al menos un concepto positivo");
      return;
    }

    setRunnerLoading(true);
    setRunnerError(null);
    setRunnerTask(null);
    clearRunnerInterval();

    try {
      const data = await apiFetchJson<AgentExecuteResponse>("/api/agent/execute", {
        method: "POST",
        body: JSON.stringify({
          project_id: project,
          concepts: positives,
          max_iterations: 50,
          discovery_only: true,
          // Defaults in backend: max_interviews=10, iterations_per_interview=4
        }),
      });

      // Start polling
      await pollRunnerStatus(data.task_id);
      runnerIntervalRef.current = window.setInterval(() => pollRunnerStatus(data.task_id), 2000);
    } catch (err) {
      setRunnerError(err instanceof Error ? err.message : "Error iniciando runner");
      setRunnerLoading(false);
    }
  }, [project, positiveText, clearRunnerInterval, pollRunnerStatus]);

  const handleAIAnalysis = useCallback(async () => {
    if (!response || response.fragments.length === 0) return;

    const positives = positiveText.split("\n").map(s => s.trim()).filter(Boolean);
    const negatives = negativeText.split("\n").map(s => s.trim()).filter(Boolean);

    setAiLoading(true);
    setAiError(null);
    setMemoSavedPath(null);
    setMemoSaveError(null);

    try {
      const result = await analyzeDiscovery(
        positives,
        negatives,
        targetText.trim() || null,
        response.fragments,
        project
      );
      const analysisText = (result.analysis ?? "").trim();
      if (!analysisText) {
        setAiError("La IA devolvió una respuesta vacía. Reintenta o revisa la configuración del modelo.");
        setAiAnalysis("(Respuesta vacía del modelo)");
      } else {
        setAiAnalysis(result.analysis);
      }

      // Sprint 22: Guardar respuesta estructurada
      setAiStructured(Boolean(result.structured));
      setAiMemoStatements(Array.isArray((result as any).memo_statements) ? ((result as any).memo_statements as EpistemicStatement[]) : []);
      setAiCodigos(result.codigos_sugeridos || []);
      const refinamientos = result.refinamiento_busqueda || null;
      const hasAnyRefinement = Boolean(
        refinamientos &&
        ((Array.isArray((refinamientos as any).positivos) && (refinamientos as any).positivos.length > 0) ||
          (Array.isArray((refinamientos as any).negativos) && (refinamientos as any).negativos.length > 0) ||
          (typeof (refinamientos as any).target === "string" && (refinamientos as any).target.trim().length > 0))
      );
      setAiRefinamientos(hasAnyRefinement ? (refinamientos as any) : null);

      // Auto-guardar memo con síntesis
      try {
        await saveDiscoveryMemo({
          positive_texts: positives,
          negative_texts: negatives.length > 0 ? negatives : undefined,
          target_text: targetText.trim() || undefined,
          fragments: response.fragments,
          project,
          ai_synthesis: result.analysis || undefined,
        });
      } catch (saveErr) {
        console.warn("Auto-save failed:", saveErr);
      }
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Error en análisis IA");
    } finally {
      setAiLoading(false);
    }
  }, [response, positiveText, negativeText, targetText, project]);

  const memoBadgeStyle = (t: string): React.CSSProperties => {
    const type = (t || "").toUpperCase();
    const base: React.CSSProperties = {
      display: "inline-flex",
      alignItems: "center",
      padding: "0.15rem 0.5rem",
      borderRadius: "999px",
      fontSize: "0.72rem",
      fontWeight: 700,
      letterSpacing: "0.02em",
      border: "1px solid rgba(0,0,0,0.08)",
      whiteSpace: "nowrap",
    };
    if (type === "OBSERVATION") return { ...base, background: "#e0f2fe", color: "#075985" };
    if (type === "INTERPRETATION") return { ...base, background: "#ecfdf5", color: "#065f46" };
    if (type === "HYPOTHESIS") return { ...base, background: "#ede9fe", color: "#5b21b6" };
    if (type === "NORMATIVE_INFERENCE") return { ...base, background: "#fff7ed", color: "#9a3412" };
    return { ...base, background: "#f3f4f6", color: "#374151" };
  };

  // Sprint 22 + Sprint 23: Enviar códigos a bandeja con pre-check
  const handleSendCodesToTray = useCallback(async () => {
    if (aiCodigos.length === 0 || !response) return;

    setSendingCodes(true);

    try {
      // Sprint 23: Pre-check for similar codes
      const checkResult = await checkBatchCodes(project, aiCodigos, 0.85);

      if (checkResult.has_any_similar) {
        // Show modal for user to decide
        setDedupResults(checkResult.results);
        setCodesToSend(aiCodigos);
        setShowDedupModal(true);
        setSendingCodes(false);
        return;
      }

      // No similar codes, proceed directly
      await sendCodesDirectly(aiCodigos);
    } catch (err) {
      alert(`Error verificando códigos: ${err instanceof Error ? err.message : String(err)}`);
      setSendingCodes(false);
    }
  }, [aiCodigos, response, project]);

  // Sprint 23: Send codes directly (after check or from modal)
  const sendCodesDirectly = useCallback(async (codigos: string[]) => {
    if (!response) return;

    setSendingCodes(true);
    let successCount = 0;

    try {
      for (const codigo of codigos) {
        const firstFrag = response.fragments[0];
        await submitCandidate({
          project,
          codigo: codigo.trim(),
          cita: firstFrag?.fragmento?.substring(0, 300) || "",
          fragmento_id: firstFrag?.fragmento_id || "",
          archivo: firstFrag?.archivo || "discovery_ai",
          fuente_origen: "discovery_ai",
          score_confianza: 0.8,
          memo: `Código sugerido por IA desde Discovery: ${positiveText.split("\n").slice(0, 2).join(", ")}`,
        });
        successCount++;
      }
      alert(`✅ ${successCount} códigos enviados a la Bandeja de Candidatos.\n\nRevísalos en el Panel de Validación.`);
      setShowDedupModal(false);
    } catch (err) {
      alert(`Error enviando códigos: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSendingCodes(false);
    }
  }, [aiCodigos, response, project, positiveText]);

  // Sprint 22 + Sprint 24 + Sprint 25: Aplicar refinamientos con mejoras UX
  const handleApplyRefinements = useCallback(async (autoSearch: boolean = false) => {
    if (!aiRefinamientos) return;

    // Aplicar los nuevos valores al formulario
    if (aiRefinamientos.positivos?.length > 0) {
      setPositiveText(aiRefinamientos.positivos.join("\n"));
    }
    if (aiRefinamientos.negativos?.length > 0) {
      setNegativeText(aiRefinamientos.negativos.join("\n"));
    }
    if (aiRefinamientos.target) {
      setTargetText(aiRefinamientos.target);
    }

    // Sprint 24: Log refinement action
    if (currentBusquedaId && response) {
      try {
        await logDiscoveryNavigation({
          project,
          positivos: aiRefinamientos.positivos || [],
          negativos: aiRefinamientos.negativos || [],
          target_text: aiRefinamientos.target || null,
          fragments_count: response.count,
          codigos_sugeridos: aiCodigos,
          refinamientos_aplicados: aiRefinamientos,
          ai_synthesis: aiAnalysis || undefined,
          action_taken: "refine",
          busqueda_origen_id: currentBusquedaId,
        });
      } catch (navErr) {
        console.warn("Refinement log failed:", navErr);
      }
    }

    // Sprint 25: Scroll preciso al formulario usando offset calculado
    if (formRef.current) {
      const formRect = formRef.current.getBoundingClientRect();
      const offsetTop = window.scrollY + formRect.top - 100; // 100px de margen superior
      window.scrollTo({ top: offsetTop, behavior: 'smooth' });
    }

    // Mostrar toast de guía (solo si no auto-ejecuta)
    if (!autoSearch) {
      setShowRefinementToast(true);
      setTimeout(() => setShowRefinementToast(false), 5000);
    }

    // Activar highlight animation
    setHighlightForm(true);
    setTimeout(() => setHighlightForm(false), 3000);

    // Si el usuario eligió auto-ejecutar, esperamos un momento y ejecutamos búsqueda
    if (autoSearch) {
      // Pequeño delay para que el scroll y los estados se actualicen
      setTimeout(() => {
        handleSearch();
      }, 600);
    }
  }, [aiRefinamientos, currentBusquedaId, response, project, aiCodigos, aiAnalysis, handleSearch]);

  const handleSaveMemo = useCallback(async () => {
    if (!response) return;
    const positives = positiveText.split("\n").map(s => s.trim()).filter(Boolean);
    const negatives = negativeText.split("\n").map(s => s.trim()).filter(Boolean);

    setMemoSaving(true);
    setMemoSavedPath(null);
    setMemoSaveError(null);
    try {
      const res = await saveDiscoveryMemo({
        positive_texts: positives,
        negative_texts: negatives.length > 0 ? negatives : undefined,
        target_text: targetText.trim() || undefined,
        fragments: response.fragments,
        project,
        ai_synthesis: aiAnalysis || undefined,  // Incluir síntesis si existe
      });
      setMemoSavedPath(res.path);
    } catch (err) {
      setMemoSaveError(err instanceof Error ? err.message : String(err));
    }
    finally {
      setMemoSaving(false);
    }
  }, [response, positiveText, negativeText, targetText, project, aiAnalysis]);

  // Handler para proponer fragmento como código candidato
  const handleProposeAsCode = useCallback(async (frag: any) => {
    const codigo = prompt(
      "💡 Proponer Código Candidato\n\n" +
      "Ingresa el nombre del código para este fragmento:\n\n" +
      `Archivo: ${frag.archivo}\n` +
      `Texto: ${frag.fragmento?.substring(0, 100)}...`
    );

    if (!codigo || !codigo.trim()) return;

    try {
      const result = await submitCandidate({
        project,
        codigo: codigo.trim(),
        cita: frag.fragmento?.substring(0, 300),
        fragmento_id: frag.fragmento_id,
        archivo: frag.archivo,
        fuente_origen: "discovery",
        score_confianza: frag.score,
        memo: `Propuesto desde Discovery con conceptos: ${positiveText.split("\n").slice(0, 2).join(", ")}`,
      });

      if (result.success) {
        alert(`✅ Código "${codigo}" propuesto como candidato.\n\nRevísalo en el Panel de Validación.`);
      } else {
        alert("No se pudo guardar el código candidato.");
      }
    } catch (err) {
      alert("Error al proponer código: " + (err instanceof Error ? err.message : String(err)));
    }
  }, [project, positiveText]);

  const handleSendToCoding = useCallback((frag: any) => {
    // Si hay callback de padre, usarlo
    if (onSelectFragment) {
      onSelectFragment(frag.fragmento_id, frag.fragmento);
      return;
    }

    // Si no hay callback, copiar al portapapeles y mostrar instrucciones
    const textToCopy = `[ID: ${frag.fragmento_id}]\n[Archivo: ${frag.archivo}]\n\n${frag.fragmento}`;

    navigator.clipboard.writeText(textToCopy).then(() => {
      alert(
        `✅ Fragmento copiado al portapapeles!\n\n` +
        `Para codificar este fragmento:\n` +
        `1. Ve a la sección "Etapa 3 - Codificación abierta"\n` +
        `2. Pega el texto en el campo "Cita"\n` +
        `3. Asigna un código y guarda\n\n` +
        `ID del fragmento: ${frag.fragmento_id}`
      );
    }).catch(() => {
      // Fallback si clipboard no funciona
      alert(
        `📋 Para usar este fragmento:\n\n` +
        `ID: ${frag.fragmento_id}\n` +
        `Archivo: ${frag.archivo}\n\n` +
        `Copia el texto manualmente y pégalo en la sección de Codificación.`
      );
    });
  }, [onSelectFragment]);

  return (
    <div className="discovery-panel">
      <h3 className="discovery-panel__title">
        🔍 Discovery - Busqueda Exploratoria
      </h3>
      <p className="discovery-panel__description">
        Busca fragmentos similares a conceptos positivos y diferentes de los negativos.
      </p>

      <div
        ref={formRef}
        className={`discovery-panel__form ${highlightForm ? 'discovery-panel__form--highlight' : ''}`}
      >
        <div className="discovery-panel__field">
          <label>Conceptos Positivos (uno por linea) *</label>
          <textarea
            value={positiveText}
            onChange={(e) => setPositiveText(e.target.value)}
            placeholder="participacion ciudadana\norganizacion comunitaria"
            rows={3}
            disabled={loading}
          />
        </div>

        <div className="discovery-panel__field">
          <label>Conceptos Negativos (opcional)</label>
          <textarea
            value={negativeText}
            onChange={(e) => setNegativeText(e.target.value)}
            placeholder="conflicto violento\nprotesta"
            rows={2}
            disabled={loading}
          />
        </div>

        <div className="discovery-panel__field">
          <label>Texto Objetivo (opcional)</label>
          <input
            type="text"
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            placeholder="Ej: seguridad barrial"
            disabled={loading}
          />
        </div>

        <div className="discovery-panel__row">
          <label>
            Resultados:
            <input
              type="number"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              min={1}
              max={50}
              disabled={loading}
            />
          </label>

          <button
            onClick={handleSearch}
            disabled={loading || !positiveText.trim()}
            className="discovery-panel__submit"
          >
            {loading ? "Buscando..." : "Buscar"}
          </button>

          <button
            onClick={handleRunDiscoveryRunner}
            disabled={runnerLoading || loading || !positiveText.trim() || !project}
            className="discovery-panel__submit"
            title="Ejecuta el runner automatizado usando Conceptos Positivos como concepts (ignora Negativos/Target)"
          >
            {runnerLoading ? "⏳ Runner..." : "🚀 Runner"}
          </button>
        </div>
      </div>

      {error && <div className="discovery-panel__error">{error}</div>}

      {runnerError && (
        <div className="discovery-panel__error">
          ⚠️ Runner: {runnerError}
        </div>
      )}

      {runnerTask && (
        <div className="discovery-panel__results">
          <h4>Runner Discovery</h4>
          <p>
            Estado: <strong>{runnerTask.status}</strong> | Stage: {runnerTask.current_stage} | Iteraciones: {runnerTask.iteration}
          </p>
          {runnerTask.errors && runnerTask.errors.length > 0 && (
            <div>
              <strong>Errores:</strong> {runnerTask.errors.length}
              <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.25rem" }}>
                {runnerTask.errors.slice(0, 3).map((e, idx) => (
                  <li key={idx}>{e}</li>
                ))}
                {runnerTask.errors.length > 3 && <li>... y {runnerTask.errors.length - 3} más</li>}
              </ul>
            </div>
          )}
          {runnerTask.final_landing_rate && (
            <div>
              <strong>Landing rate final:</strong> {runnerTask.final_landing_rate.landing_rate.toFixed(1)}% ({runnerTask.final_landing_rate.matched_count} de {runnerTask.final_landing_rate.total_count})
            </div>
          )}

          {runnerTask.final_landing_rate?.reason && (
            <p style={{ marginTop: "0.25rem" }}>
              <strong>Nota:</strong>{" "}
              {runnerTask.final_landing_rate.reason === "no_definitive_codes"
                ? "No hay códigos definitivos en analisis_codigos_abiertos para este proyecto (promueve los validados a la lista definitiva para que el landing rate sea significativo)."
                : runnerTask.final_landing_rate.reason === "no_overlap_with_definitive_codes"
                  ? "Los fragmentos encontrados no coinciden con fragmentos ya codificados (esto puede ser esperado si Discovery está explorando material nuevo)."
                  : "OK"}
            </p>
          )}

          {runnerTask.post_run && (
            <div style={{ marginTop: "0.75rem" }}>
              <div>
                <strong>Post-run:</strong>{" "}
                {typeof runnerTask.post_run.codes_inserted === "number"
                  ? `${runnerTask.post_run.codes_inserted} códigos enviados a bandeja`
                  : "(sin conteo)"}
                {typeof runnerTask.post_run.sample_fragments_count === "number" && (
                  <span> | Muestra: {runnerTask.post_run.sample_fragments_count} fragmentos</span>
                )}
              </div>
              {runnerTask.post_run.report_path && (
                <div style={{ marginTop: "0.25rem" }}>
                  <strong>Informe:</strong> {runnerTask.post_run.report_path}
                </div>
              )}
              {runnerTask.post_run.analysis && (
                <div style={{ marginTop: "0.25rem" }}>
                  <strong>Síntesis:</strong> {runnerTask.post_run.analysis}
                </div>
              )}
              {Array.isArray(runnerTask.post_run.codes_suggested) && runnerTask.post_run.codes_suggested.length > 0 && (
                <div style={{ marginTop: "0.25rem" }}>
                  <strong>Códigos sugeridos:</strong> {runnerTask.post_run.codes_suggested.slice(0, 12).join(", ")}
                  {runnerTask.post_run.codes_suggested.length > 12 && (
                    <span> ... (+{runnerTask.post_run.codes_suggested.length - 12})</span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {response && (
        <div className="discovery-panel__results">
          <h4>Resultados ({response.count})</h4>
          {response.fragments.length === 0 ? (
            <p>No se encontraron fragmentos.</p>
          ) : (
            <ul className="discovery-panel__list">
              {response.fragments.map((frag, idx) => {
                // Phase 0.5: Smart action indicator based on score thresholds
                const scorePercent = (frag.score ?? 0) * 100;
                const getRecommendedAction = () => {
                  if (scorePercent >= 80) return { action: 'codificar', label: '✅ Alta confianza - Codificar directamente', color: '#059669' };
                  if (scorePercent >= 60) return { action: 'proponer', label: '💡 Media confianza - Proponer como candidato', color: '#7c3aed' };
                  return { action: 'explorar', label: '🔍 Baja confianza - Explorar más', color: '#6b7280' };
                };
                const recommendation = getRecommendedAction();

                return (
                  <li key={frag.fragmento_id || idx} className="discovery-panel__item">
                    <div className="discovery-panel__item-header">
                      <span className="discovery-panel__score" title={`Score de similitud semántica: ${scorePercent.toFixed(1)}%`}>
                        {scorePercent.toFixed(1)}%
                      </span>
                      <span className="discovery-panel__archivo">{frag.archivo}</span>
                      {/* Phase 0.5: Action recommendation badge */}
                      <span style={{
                        marginLeft: 'auto',
                        padding: '0.2rem 0.5rem',
                        fontSize: '0.7rem',
                        background: recommendation.color,
                        color: 'white',
                        borderRadius: '1rem',
                        fontWeight: 500,
                      }} title={recommendation.label}>
                        {recommendation.action === 'codificar' ? '✅ Codificar' :
                          recommendation.action === 'proponer' ? '💡 Proponer' : '🔍 Explorar'}
                      </span>
                    </div>
                    <div className="discovery-panel__text">
                      {frag.fragmento?.substring(0, 250)}...
                    </div>
                    <div style={{ marginTop: "0.5rem", display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ fontSize: "0.7rem", color: "#6b7280" }}>
                        ID: {frag.fragmento_id?.substring(0, 12)}...
                      </span>
                      <button
                        onClick={() => handleProposeAsCode(frag)}
                        title="Proponer este fragmento como código candidato para validación"
                        style={{
                          padding: "0.35rem 0.75rem",
                          fontSize: "0.8rem",
                          background: "linear-gradient(135deg, #8b5cf6, #7c3aed)",
                          color: "white",
                          border: "none",
                          borderRadius: "0.375rem",
                          cursor: "pointer",
                          fontWeight: 500,
                          display: "flex",
                          alignItems: "center",
                          gap: "0.25rem",
                        }}
                      >
                        💡 Proponer Código
                      </button>
                      <button
                        onClick={() => handleSendToCoding(frag)}
                        title="Copia este fragmento al portapapeles para usarlo en la sección de Codificación Abierta"
                        style={{
                          padding: "0.35rem 0.75rem",
                          fontSize: "0.8rem",
                          background: "linear-gradient(135deg, #3b82f6, #2563eb)",
                          color: "white",
                          border: "none",
                          borderRadius: "0.375rem",
                          cursor: "pointer",
                          fontWeight: 500,
                          display: "flex",
                          alignItems: "center",
                          gap: "0.25rem",
                        }}
                      >
                        📋 Copiar
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
          {response.fragments.length > 0 && (
            <div style={{ marginTop: "1rem", display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
              <button
                onClick={handleSaveMemo}
                disabled={memoSaving}
                style={{
                  padding: "0.5rem 1.5rem",
                  background: "#0f766e",
                  color: "white",
                  border: "none",
                  borderRadius: "0.375rem",
                  cursor: memoSaving ? "wait" : "pointer",
                  fontSize: "0.9rem"
                }}
              >
                {memoSaving ? "💾 Guardando..." : "💾 Guardar Memo"}
              </button>
              <button
                onClick={handleAIAnalysis}
                disabled={aiLoading}
                style={{
                  padding: "0.5rem 1.5rem",
                  background: "linear-gradient(135deg, #059669, #10b981)",
                  color: "white",
                  border: "none",
                  borderRadius: "0.375rem",
                  cursor: aiLoading ? "wait" : "pointer",
                  fontSize: "0.9rem",
                  fontWeight: 600,
                  opacity: aiLoading ? 0.7 : 1,
                }}
              >
                {aiLoading ? "🤖 Analizando..." : "🤖 Sintetizar con IA"}
              </button>
            </div>
          )}

          {memoSavedPath && (
            <p style={{ marginTop: "0.75rem", textAlign: "center" }}>
              ✅ Memo guardado en: {memoSavedPath}
            </p>
          )}

          {memoSaveError && (
            <div className="discovery-panel__error" style={{ marginTop: "0.75rem" }}>
              Error al guardar memo: {memoSaveError}
            </div>
          )}

          {/* AI Error */}
          {aiError && (
            <div className="discovery-panel__error" style={{ marginTop: "1rem" }}>
              {aiError}
            </div>
          )}

          {/* AI Analysis Result */}
          {aiAnalysis && (
            <div className="discovery-panel__ai-result">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <h4 style={{ margin: 0 }}>🧠 Síntesis y Sugerencias (IA)</h4>
                <button
                  onClick={handleSaveMemo}
                  style={{
                    padding: '0.4rem 0.8rem',
                    background: 'linear-gradient(135deg, #059669, #10b981)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '0.375rem',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  💾 Guardar Síntesis
                </button>
              </div>

              {/* Sprint 29+: Epistemic-tagged memo rendering (compatible with legacy text) */}
              {aiMemoStatements.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.75rem",
                    padding: "0.75rem",
                    border: "1px solid #d1fae5",
                    borderRadius: "0.75rem",
                    background: "#f0fdf4",
                  }}
                >
                  <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
                    <strong style={{ fontSize: "0.9rem" }}>Estatus epistemológico</strong>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem" }}>
                      <input
                        type="checkbox"
                        checked={showTaggedMemo}
                        onChange={(e) => setShowTaggedMemo(e.target.checked)}
                      />
                      Mostrar etiquetado
                    </label>
                    <span style={{ fontSize: "0.8rem", color: "#065f46" }}>
                      (OBSERVATION requiere evidencia)
                    </span>
                  </div>

                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    {[
                      "OBSERVATION",
                      "INTERPRETATION",
                      "HYPOTHESIS",
                      "NORMATIVE_INFERENCE",
                    ].map((t) => (
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
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
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

              {/* Legacy text rendering (kept for compatibility and copy/paste) */}
              {(!aiMemoStatements.length || !showTaggedMemo) && (
                <div className="discovery-panel__ai-content">
                  {aiAnalysis.split("\n").map((line, idx) => (
                    <p key={idx}>{line}</p>
                  ))}
                </div>
              )}

              {/* Sprint 22: Action Buttons */}
              {aiStructured && (
                <div style={{
                  display: 'flex',
                  gap: '0.75rem',
                  marginTop: '1rem',
                  paddingTop: '1rem',
                  borderTop: '1px solid #d1fae5',
                  flexWrap: 'wrap',
                }}>
                  {aiCodigos.length > 0 && (
                    <button
                      onClick={handleSendCodesToTray}
                      disabled={sendingCodes}
                      style={{
                        padding: '0.5rem 1rem',
                        background: sendingCodes ? '#9ca3af' : 'linear-gradient(135deg, #7c3aed, #8b5cf6)',
                        color: 'white',
                        border: 'none',
                        borderRadius: '0.5rem',
                        cursor: sendingCodes ? 'wait' : 'pointer',
                        fontWeight: 600,
                        fontSize: '0.9rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                      }}
                    >
                      <span>📋</span>
                      {sendingCodes ? 'Enviando...' : `Enviar ${aiCodigos.length} Códigos a Bandeja`}
                    </button>
                  )}

                  {aiRefinamientos && (
                    <div style={{
                      display: 'flex',
                      gap: '0.5rem',
                      flexWrap: 'wrap',
                    }}>
                      <button
                        onClick={() => handleApplyRefinements(false)}
                        title="Actualiza los campos del formulario con las sugerencias. Deberás hacer click en Buscar manualmente."
                        style={{
                          padding: '0.5rem 1rem',
                          background: 'linear-gradient(135deg, #0891b2, #06b6d4)',
                          color: 'white',
                          border: 'none',
                          borderRadius: '0.5rem',
                          cursor: 'pointer',
                          fontWeight: 600,
                          fontSize: '0.9rem',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.5rem',
                        }}
                      >
                        <span>🔄</span>
                        Aplicar Refinamientos
                      </button>
                      <button
                        onClick={() => handleApplyRefinements(true)}
                        title="Actualiza los campos y ejecuta la búsqueda automáticamente"
                        style={{
                          padding: '0.5rem 1rem',
                          background: 'linear-gradient(135deg, #059669, #10b981)',
                          color: 'white',
                          border: 'none',
                          borderRadius: '0.5rem',
                          cursor: 'pointer',
                          fontWeight: 600,
                          fontSize: '0.9rem',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.5rem',
                        }}
                      >
                        <span>🚀</span>
                        Aplicar y Buscar
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Sprint 23: Deduplication Modal */}
      {showDedupModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            background: 'white',
            borderRadius: '0.75rem',
            padding: '1.5rem',
            maxWidth: '500px',
            maxHeight: '80vh',
            overflow: 'auto',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
          }}>
            <h3 style={{ margin: '0 0 1rem', color: '#7c3aed' }}>
              ⚠️ Códigos Similares Detectados
            </h3>
            <p style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: '1rem' }}>
              Algunos códigos sugeridos son similares a códigos existentes.
              Revisa antes de enviar a la bandeja.
            </p>

            <div style={{ marginBottom: '1rem' }}>
              {dedupResults.map((result, idx) => (
                <div key={idx} style={{
                  padding: '0.75rem',
                  marginBottom: '0.5rem',
                  background: result.has_similar ? '#fef3c7' : '#d1fae5',
                  borderRadius: '0.5rem',
                  borderLeft: `4px solid ${result.has_similar ? '#f59e0b' : '#10b981'}`,
                }}>
                  <strong>{result.codigo}</strong>
                  {result.has_similar && (
                    <div style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>
                      Similar a:{' '}
                      {result.similar.map((s, i) => (
                        <span key={i}>
                          <code>{s.existing}</code> ({Math.round(s.similarity * 100)}%)
                          {i < result.similar.length - 1 && ', '}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowDedupModal(false)}
                style={{
                  padding: '0.5rem 1rem',
                  background: '#e5e7eb',
                  border: 'none',
                  borderRadius: '0.375rem',
                  cursor: 'pointer',
                }}
              >
                Cancelar
              </button>
              <button
                onClick={() => {
                  const newCodes = dedupResults.filter(r => !r.has_similar).map(r => r.codigo);
                  if (newCodes.length > 0) {
                    sendCodesDirectly(newCodes);
                  } else {
                    alert('No hay códigos nuevos para enviar.');
                    setShowDedupModal(false);
                  }
                }}
                style={{
                  padding: '0.5rem 1rem',
                  background: 'linear-gradient(135deg, #10b981, #059669)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '0.375rem',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                ✅ Enviar Solo Nuevos ({dedupResults.filter(r => !r.has_similar).length})
              </button>
              <button
                onClick={() => sendCodesDirectly(codesToSend)}
                disabled={sendingCodes}
                style={{
                  padding: '0.5rem 1rem',
                  background: sendingCodes ? '#9ca3af' : 'linear-gradient(135deg, #7c3aed, #8b5cf6)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '0.375rem',
                  cursor: sendingCodes ? 'wait' : 'pointer',
                  fontWeight: 600,
                }}
              >
                {sendingCodes ? 'Enviando...' : `Enviar Todos (${codesToSend.length})`}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .discovery-panel {
          padding: 1rem;
          background: #f0fdf4;
          border-radius: 0.5rem;
          margin-bottom: 1rem;
        }
        .discovery-panel__title {
          margin: 0 0 0.5rem 0;
          font-size: 1.1rem;
          color: #166534;
        }
        .discovery-panel__description {
          margin: 0 0 1rem 0;
          font-size: 0.875rem;
          color: #64748b;
        }
        .discovery-panel__form {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .discovery-panel__field {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }
        .discovery-panel__field label {
          font-size: 0.875rem;
          font-weight: 500;
          color: #374151;
        }
        .discovery-panel__field textarea,
        .discovery-panel__field input {
          padding: 0.5rem;
          border: 1px solid #d1d5db;
          border-radius: 0.25rem;
          font-size: 0.875rem;
        }
        .discovery-panel__row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 1rem;
        }
        .discovery-panel__row input[type="number"] {
          width: 60px;
          margin-left: 0.5rem;
          padding: 0.25rem;
        }
        .discovery-panel__submit {
          padding: 0.5rem 1.5rem;
          background: #16a34a;
          color: white;
          border: none;
          border-radius: 0.375rem;
          cursor: pointer;
        }
        .discovery-panel__submit:disabled {
          opacity: 0.6;
        }
        .discovery-panel__error {
          margin-top: 0.75rem;
          padding: 0.5rem;
          background: #fef2f2;
          color: #dc2626;
          border-radius: 0.25rem;
        }
        .discovery-panel__results {
          margin-top: 1rem;
        }
        .discovery-panel__results h4 {
          margin: 0 0 0.5rem 0;
          font-size: 0.95rem;
        }
        .discovery-panel__list {
          margin: 0;
          padding: 0;
          list-style: none;
        }
        .discovery-panel__item {
          padding: 0.75rem;
          background: white;
          border: 1px solid #d1fae5;
          border-radius: 0.25rem;
          margin-bottom: 0.5rem;
        }
        .discovery-panel__item-header {
          display: flex;
          justify-content: space-between;
          font-size: 0.8rem;
          margin-bottom: 0.25rem;
        }
        .discovery-panel__score {
          font-weight: 600;
          color: #16a34a;
        }
        .discovery-panel__archivo {
          color: #6b7280;
        }
        .discovery-panel__text {
          font-size: 0.875rem;
          color: #374151;
        }
        .discovery-panel__ai-result {
          margin-top: 1.25rem;
          background: linear-gradient(135deg, #ecfdf5, #d1fae5);
          border: 1px solid #6ee7b7;
          border-radius: 0.75rem;
          padding: 1rem;
        }
        .discovery-panel__ai-result h4 {
          margin: 0 0 0.75rem 0;
          color: #065f46;
          font-size: 1rem;
        }
        .discovery-panel__ai-content {
          font-size: 0.9rem;
          line-height: 1.6;
          color: #1f2937;
        }
        .discovery-panel__ai-content p {
          margin: 0.5rem 0;
        }
        .discovery-panel__ai-content p:empty {
          display: none;
        }
        
        /* Sprint 25: Highlight animation for form */
        .discovery-panel__form--highlight {
          animation: highlight-pulse 1s ease-in-out 2;
          box-shadow: 0 0 20px rgba(14, 165, 233, 0.5);
          border-radius: 0.5rem;
        }
        
        @keyframes highlight-pulse {
          0%, 100% { box-shadow: 0 0 0 rgba(14, 165, 233, 0); }
          50% { box-shadow: 0 0 25px rgba(14, 165, 233, 0.7); }
        }
        
        /* Sprint 25: Toast notification */
        .discovery-toast {
          position: fixed;
          bottom: 2rem;
          right: 2rem;
          background: linear-gradient(135deg, #0f766e, #14b8a6);
          color: white;
          padding: 1rem 1.5rem;
          border-radius: 0.75rem;
          box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
          z-index: 1000;
          animation: toast-slide-in 0.3s ease-out;
          font-size: 0.95rem;
          max-width: 350px;
        }
        
        @keyframes toast-slide-in {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>

      {/* Sprint 25: Toast de guía para refinamientos */}
      {showRefinementToast && (
        <div className="discovery-toast">
          ✨ Refinamientos aplicados. <strong>Click en "Buscar"</strong> para ejecutar una nueva búsqueda.
        </div>
      )}
    </div>
  );
}

export default DiscoveryPanel;
