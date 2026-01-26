/**
 * @fileoverview Panel de Link Prediction - Sugerencias de Relaciones.
 *
 * Este componente muestra sugerencias de relaciones axiales faltantes
 * basandose en algoritmos de prediccion de enlaces.
 *
 * @module components/LinkPredictionPanel
 */

import React, { useState, useCallback, useMemo, useEffect } from "react";
import { predictLinks, getCommunityLinks, analyzePredictions, LinkSuggestion, saveLinkPredictions, saveAnalysisReport, submitCandidate, checkBatchCodes, BatchCheckResult, EpistemicStatement, listAnalysisReports, AnalysisReport } from "../services/api";
import { EpistemicBadge } from "./common/Analysis";
import { LinkPredictionValidationPanel } from "./LinkPredictionValidationPanel";
import { AxialAiReviewPanel } from "./AxialAiReviewPanel";

interface LinkPredictionPanelProps {
  project: string;
  onApplySuggestion?: (suggestion: LinkSuggestion) => void;
}

const ALGORITHMS = [
  {
    value: "common_neighbors",
    label: "Vecinos Comunes",
    description: "Cuenta cuántos nodos conectan dos códigos. Más vecinos compartidos = mayor probabilidad de relación directa."
  },
  {
    value: "jaccard",
    label: "Coeficiente Jaccard",
    description: "Mide la similitud entre conjuntos de vecinos. Ideal para detectar códigos que comparten contextos similares."
  },
  {
    value: "adamic_adar",
    label: "Adamic-Adar",
    description: "Pondera vecinos comunes por su rareza. Prioriza conexiones a través de nodos exclusivos (no hubs)."
  },
  {
    value: "preferential_attachment",
    label: "Preferential Attachment",
    description: "Los códigos populares tienden a conectarse más. Detecta relaciones en categorías emergentes."
  },
];

export function LinkPredictionPanel({
  project,
  onApplySuggestion,
}: LinkPredictionPanelProps) {
  const [algorithm, setAlgorithm] = useState("common_neighbors");
  const [topK, setTopK] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<LinkSuggestion[]>([]);
  const [usedAlgorithm, setUsedAlgorithm] = useState("");

  // AI Analysis state
  const [aiAnalysis, setAiAnalysis] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiAnalysisId, setAiAnalysisId] = useState<number | null>(null);
  const [aiPersisted, setAiPersisted] = useState(false);

  // Sprint 29+: Epistemic-tagged memo rendering (compatible with legacy text)
  const [aiMemoStatements, setAiMemoStatements] = useState<EpistemicStatement[]>([]);
  const [showTaggedMemo, setShowTaggedMemo] = useState(true);
  const [memoTypeFilters, setMemoTypeFilters] = useState<Record<string, boolean>>({
    OBSERVATION: true,
    INTERPRETATION: true,
    HYPOTHESIS: true,
    NORMATIVE_INFERENCE: true,
  });

  // State for saving to candidates
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // State for saving AI report to database
  const [reportSaving, setReportSaving] = useState(false);
  const [reportSaved, setReportSaved] = useState<string | null>(null);

  // State for listing saved AI reports
  const [reportList, setReportList] = useState<AnalysisReport[]>([]);
  const [reportListLoading, setReportListLoading] = useState(false);
  const [reportListError, setReportListError] = useState<string | null>(null);

  // State for codes to candidates (Sprint: uniform flow)
  const [sendingCodes, setSendingCodes] = useState(false);
  const [showDedupModal, setShowDedupModal] = useState(false);
  const [dedupResults, setDedupResults] = useState<BatchCheckResult[]>([]);
  const [codesToSend, setCodesToSend] = useState<string[]>([]);

  // Extract unique codes from predictions
  const extractedCodes = useMemo(() => {
    if (!suggestions || suggestions.length === 0) return [];
    const codes = new Set<string>();
    suggestions.forEach(s => {
      if (s.source) codes.add(s.source);
      if (s.target) codes.add(s.target);
    });
    return Array.from(codes);
  }, [suggestions]);

  const selectedAlgorithm = ALGORITHMS.find(a => a.value === algorithm);

  const handlePredict = useCallback(async () => {
    setLoading(true);
    setError(null);
    setAiAnalysis(null); // Clear previous analysis
    setAiMemoStatements([]);
    setAiAnalysisId(null);
    setAiPersisted(false);

    try {
      const result = await predictLinks(algorithm, topK, project);
      setSuggestions(result.suggestions);
      setUsedAlgorithm(result.algorithm);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }, [algorithm, topK, project]);

  const handleCommunityLinks = useCallback(async () => {
    setLoading(true);
    setError(null);
    setAiAnalysis(null);
    setAiMemoStatements([]);

    try {
      const result = await getCommunityLinks(project);
      setSuggestions(result.suggestions);
      setUsedAlgorithm("community_based");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }, [project]);

  const handleAIAnalysis = useCallback(async () => {
    if (suggestions.length === 0) return;

    setAiLoading(true);
    setAiError(null);

    try {
      const result = await analyzePredictions(usedAlgorithm || algorithm, suggestions, project);
      setAiAnalysis(result.analysis);
      setAiMemoStatements(Array.isArray((result as any).memo_statements) ? ((result as any).memo_statements as EpistemicStatement[]) : []);
      setAiAnalysisId(typeof result.analysis_id === "number" ? result.analysis_id : null);
      setAiPersisted(Boolean(result.persisted));
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Error en análisis IA");
    } finally {
      setAiLoading(false);
    }
  }, [suggestions, usedAlgorithm, algorithm, project]);

  const handleSaveToCandidates = useCallback(async () => {
    if (suggestions.length === 0) return;

    setSaveLoading(true);
    setSaveError(null);
    setSaveSuccess(null);

    try {
      const suggestionsWithMeta = suggestions.map(s => ({
        source: s.source,
        target: s.target,
        score: s.score,
        algorithm: usedAlgorithm || algorithm,
        reason: `Score: ${s.score.toFixed(3)}`,
      }));
      const result = await saveLinkPredictions(project, suggestionsWithMeta);
      setSaveSuccess(`✅ ${result.saved_count} sugerencias guardadas en Bandeja de Candidatos`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error al guardar");
    } finally {
      setSaveLoading(false);
    }
  }, [suggestions, usedAlgorithm, algorithm, project]);

  // Send extracted codes to candidates tray
  const handleSendCodesToTray = useCallback(async () => {
    if (extractedCodes.length === 0) return;

    setSendingCodes(true);

    try {
      const checkResult = await checkBatchCodes(project, extractedCodes, 0.85);

      if (checkResult.has_any_similar) {
        setDedupResults(checkResult.results);
        setCodesToSend(extractedCodes);
        setShowDedupModal(true);
        setSendingCodes(false);
        return;
      }

      await sendCodesDirectly(extractedCodes);
    } catch (err) {
      alert(`Error verificando códigos: ${err instanceof Error ? err.message : String(err)}`);
      setSendingCodes(false);
    }
  }, [extractedCodes, project]);

  const sendCodesDirectly = useCallback(async (codigos: string[]) => {
    setSendingCodes(true);
    let successCount = 0;

    try {
      for (const codigo of codigos) {
        await submitCandidate({
          project,
          codigo: codigo.trim(),
          cita: `Código identificado en predicción de enlaces (${usedAlgorithm || algorithm})`,
          fragmento_id: "",
          archivo: "link_prediction",
          fuente_origen: "discovery_ai",
          score_confianza: 0.7,
          memo: `Código extraído de predicción de enlaces con algoritmo: ${usedAlgorithm || algorithm}`,
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
  }, [project, usedAlgorithm, algorithm]);

  const formatReportDate = useCallback((value?: string | null) => {
    if (!value) return "-";
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return String(value);
      return d.toLocaleString();
    } catch {
      return String(value);
    }
  }, []);

  const loadReports = useCallback(async () => {
    if (!project) return;
    setReportListLoading(true);
    setReportListError(null);
    try {
      const res = await listAnalysisReports(project, "link_prediction", 50);
      setReportList(Array.isArray(res.reports) ? res.reports : []);
    } catch (err) {
      setReportListError(err instanceof Error ? err.message : "Error cargando informes");
    } finally {
      setReportListLoading(false);
    }
  }, [project]);

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  return (
    <div className="link-prediction-panel">
      <h3 className="link-prediction-panel__title">
        🔮 Link Prediction - Sugerencias de Relaciones
      </h3>
      <p className="link-prediction-panel__desc">
        Detecta relaciones axiales que podrian estar faltando en el grafo.
      </p>

      <div className="link-prediction-panel__controls">
        <div className="link-prediction-panel__field">
          <label>Algoritmo</label>
          <select
            value={algorithm}
            onChange={(e) => setAlgorithm(e.target.value)}
            disabled={loading}
          >
            {ALGORITHMS.map((alg) => (
              <option key={alg.value} value={alg.value}>
                {alg.label}
              </option>
            ))}
          </select>
          {selectedAlgorithm && (
            <span className="link-prediction-panel__algo-desc">
              💡 {selectedAlgorithm.description}
            </span>
          )}
        </div>

        <div className="link-prediction-panel__field">
          <label>Top K</label>
          <input
            type="number"
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            min={1}
            max={50}
            disabled={loading}
          />
        </div>

        <div className="link-prediction-panel__buttons">
          <button
            onClick={handlePredict}
            disabled={loading}
            className="link-prediction-panel__btn link-prediction-panel__btn--primary"
          >
            {loading ? "Calculando..." : "Predecir"}
          </button>
          <button
            onClick={handleCommunityLinks}
            disabled={loading}
            className="link-prediction-panel__btn link-prediction-panel__btn--secondary"
          >
            Por Comunidades
          </button>
        </div>
      </div>

      {error && <div className="link-prediction-panel__error">{error}</div>}

      {suggestions.length > 0 && (
        <div className="link-prediction-panel__results">
          <h4>
            Sugerencias ({suggestions.length})
            {usedAlgorithm && <span className="link-prediction-panel__algo"> - {usedAlgorithm}</span>}
          </h4>
          <table className="link-prediction-panel__table">
            <thead>
              <tr>
                <th>Fuente</th>
                <th>Destino</th>
                <th>Score</th>
                {onApplySuggestion && <th>Accion</th>}
              </tr>
            </thead>
            <tbody>
              {suggestions.map((sug, idx) => (
                <tr key={idx}>
                  <td>
                    <span className="link-prediction-panel__node link-prediction-panel__node--source">
                      {sug.source}
                    </span>
                  </td>
                  <td>
                    <span className="link-prediction-panel__node link-prediction-panel__node--target">
                      {sug.target}
                    </span>
                  </td>
                  <td>{typeof sug.score === "number" ? sug.score.toFixed(3) : "-"}</td>
                  {onApplySuggestion && (
                    <td>
                      <button
                        onClick={() => onApplySuggestion(sug)}
                        className="link-prediction-panel__apply"
                      >
                        Aplicar
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>

          {/* AI Analysis Button + Save to Candidates */}
          <div className="link-prediction-panel__ai-actions">
            <button
              onClick={handleSaveToCandidates}
              disabled={saveLoading || suggestions.length === 0}
              className="link-prediction-panel__btn link-prediction-panel__btn--candidates"
            >
              {saveLoading ? "💾 Guardando..." : "💾 Guardar Predicciones"}
            </button>
            <button
              onClick={handleAIAnalysis}
              disabled={aiLoading || suggestions.length === 0}
              className="link-prediction-panel__btn link-prediction-panel__btn--ai"
            >
              {aiLoading ? "🤖 Analizando..." : "🤖 Analizar con IA"}
            </button>
            {extractedCodes.length > 0 && (
              <button
                onClick={handleSendCodesToTray}
                disabled={sendingCodes}
                style={{
                  padding: "0.5rem 1rem",
                  fontSize: "0.85rem",
                  background: sendingCodes ? "#9ca3af" : "linear-gradient(135deg, #7c3aed, #8b5cf6)",
                  color: "white",
                  border: "none",
                  borderRadius: "0.375rem",
                  cursor: sendingCodes ? "wait" : "pointer",
                  fontWeight: 600,
                }}
              >
                {sendingCodes ? "Enviando..." : `📋 Enviar ${extractedCodes.length} Códigos a Bandeja`}
              </button>
            )}
          </div>

          {/* Save Success/Error Messages */}
          {saveSuccess && (
            <div className="link-prediction-panel__success">{saveSuccess}</div>
          )}
          {saveError && (
            <div className="link-prediction-panel__error">{saveError}</div>
          )}

          {/* AI Analysis Error */}
          {aiError && (
            <div className="link-prediction-panel__error">
              {aiError}
            </div>
          )}

          {/* AI Analysis Result */}
          {aiAnalysis && (
            <div className="link-prediction-panel__ai-result">
              <div className="link-prediction-panel__ai-header">
                <h4>🧠 Análisis Cualitativo (IA)</h4>
                {aiPersisted && aiAnalysisId !== null && (
                  <span style={{ fontSize: "0.8rem", color: "#6b21a8" }}>
                    Artefacto guardado: #{aiAnalysisId}
                  </span>
                )}
                <button
                  className="link-prediction-panel__btn link-prediction-panel__btn--save"
                  disabled={reportSaving}
                  onClick={async () => {
                    const content = `# Análisis Link Prediction - ${new Date().toLocaleString()}\n\n**Algoritmo:** ${usedAlgorithm}\n**Sugerencias analizadas:** ${suggestions.length}\n\n## Sugerencias de Relaciones\n\n${suggestions.map((s, i) => `${i + 1}. ${s.source} → ${s.target} (score: ${s.score.toFixed(3)})`).join('\n')}\n\n## Análisis IA\n\n${aiAnalysis}`;

                    // 1. Descargar archivo local
                    const blob = new Blob([content], { type: 'text/markdown' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `link-prediction-report-${Date.now()}.md`;
                    a.click();
                    URL.revokeObjectURL(url);

                    // 2. Guardar en base de datos
                    setReportSaving(true);
                    try {
                      await saveAnalysisReport(
                        project,
                        'link_prediction',
                        `Análisis Link Prediction - ${usedAlgorithm}`,
                        content,
                        { algorithm: usedAlgorithm, suggestions_count: suggestions.length }
                      );
                      setReportSaved('✅ Informe guardado en BD');
                      await loadReports();
                      setTimeout(() => setReportSaved(null), 5000);
                    } catch (err) {
                      console.error('Error guardando informe:', err);
                    } finally {
                      setReportSaving(false);
                    }
                  }}
                >
                  {reportSaving ? '💾 Guardando...' : (reportSaved || '💾 Guardar Informe')}
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
                    border: "1px solid #c4b5fd",
                    borderRadius: "0.75rem",
                    background: "rgba(255,255,255,0.7)",
                    marginBottom: "0.75rem",
                  }}
                >
                  <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
                    <strong style={{ fontSize: "0.9rem", color: "#5b21b6" }}>Estatus epistemológico</strong>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem" }}>
                      <input
                        type="checkbox"
                        checked={showTaggedMemo}
                        onChange={(e) => setShowTaggedMemo(e.target.checked)}
                      />
                      Mostrar etiquetado
                    </label>
                    <span style={{ fontSize: "0.8rem", color: "#6b21a8" }}>
                      (OBSERVATION requiere evidencia: fragmento_id)
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
                          checked={Boolean(memoTypeFilters[t])}
                          onChange={(e) =>
                            setMemoTypeFilters((prev) => ({
                              ...prev,
                              [t]: e.target.checked,
                            }))
                          }
                        />
                        <EpistemicBadge type={t} />
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
                          const fragIds = Array.isArray((s as any).evidence_fragment_ids)
                            ? ((s as any).evidence_fragment_ids as any[]).map((v) => String(v || "").trim()).filter(Boolean)
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
                                <EpistemicBadge type={type} />
                              </div>
                              <div style={{ flex: 1 }}>
                                <div style={{ fontSize: "0.92rem", lineHeight: 1.35 }}>{s.text}</div>
                                {(fragIds.length > 0 || evid.length > 0) && (
                                  <div style={{ marginTop: "0.2rem", fontSize: "0.78rem", color: "#6b7280" }}>
                                    {fragIds.length > 0 ? (
                                      <>
                                        Evidencia (fragmentos): {fragIds.slice(0, 12).join(", ")}
                                        {fragIds.length > 12 ? "…" : ""}
                                      </>
                                    ) : null}
                                    {fragIds.length > 0 && evid.length > 0 ? " · " : null}
                                    {evid.length > 0 ? <>Links: {evid.join(", ")}</> : null}
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
                <div className="link-prediction-panel__ai-content">
                  {aiAnalysis.split("\n").map((line, idx) => (
                    <p key={idx}>{line}</p>
                  ))}
                </div>
              )}

              {/* Fragmentos de Evidencia */}
              <div className="link-prediction-panel__evidence">
                <h5>📋 Fragmentos de Evidencia (3)</h5>
                <p className="link-prediction-panel__evidence-note">
                  Las relaciones sugeridas se basan en el análisis estructural del grafo.
                  Para validarlas, revisa los fragmentos asociados a cada código en la pestaña "Citas por código" del Panel de Codificación.
                </p>
                <div className="link-prediction-panel__evidence-tips">
                  <div className="link-prediction-panel__evidence-tip">
                    <strong>1.</strong> Selecciona un código fuente/destino de la tabla
                  </div>
                  <div className="link-prediction-panel__evidence-tip">
                    <strong>2.</strong> Busca citas que mencionen ambos conceptos
                  </div>
                  <div className="link-prediction-panel__evidence-tip">
                    <strong>3.</strong> Usa "Aplicar" para crear la relación axial
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Reportes IA guardados */}
      <div className="link-prediction-panel__reports">
        <div className="link-prediction-panel__reports-header">
          <h4>Informes IA guardados (Link Prediction)</h4>
          <button
            onClick={() => void loadReports()}
            disabled={reportListLoading}
            className="link-prediction-panel__btn link-prediction-panel__btn--secondary"
          >
            {reportListLoading ? "Cargando..." : "Refrescar"}
          </button>
        </div>

        {reportListError && (
          <div className="link-prediction-panel__error">{reportListError}</div>
        )}

        {!reportListLoading && reportList.length === 0 && (
          <div className="link-prediction-panel__reports-empty">
            No hay informes guardados. Usa "Analizar con IA" y luego "Guardar Informe".
          </div>
        )}

        {reportList.map((report) => {
          const meta = report?.metadata && typeof report.metadata === "object" ? report.metadata : null;
          const algorithmLabel = meta && "algorithm" in meta ? String((meta as any).algorithm || "") : "";
          const suggestionsCount = meta && "suggestions_count" in meta ? Number((meta as any).suggestions_count) : null;
          return (
            <details key={report.id} className="link-prediction-panel__report">
              <summary className="link-prediction-panel__report-summary">
                <span className="link-prediction-panel__report-title">
                  #{report.id} {report.title}
                </span>
                <span className="link-prediction-panel__report-meta">
                  {formatReportDate(report.created_at)}
                  {algorithmLabel ? ` · ${algorithmLabel}` : ""}
                  {typeof suggestionsCount === "number" && Number.isFinite(suggestionsCount)
                    ? ` · ${suggestionsCount} sugerencias`
                    : ""}
                </span>
              </summary>

              <div className="link-prediction-panel__report-body">
                <div className="link-prediction-panel__report-actions">
                  <button
                    className="link-prediction-panel__btn link-prediction-panel__btn--save"
                    onClick={(e) => {
                      e.preventDefault();
                      const content = report.content || "";
                      const blob = new Blob([content], { type: "text/markdown" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `link-prediction-report-${report.id}.md`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    Descargar .md
                  </button>
                </div>

                <div className="link-prediction-panel__report-content">
                  {report.content}
                </div>

                {meta && (
                  <div className="link-prediction-panel__report-meta-box">
                    <strong>Metadata</strong>
                    <pre>{JSON.stringify(meta, null, 2)}</pre>
                  </div>
                )}
              </div>
            </details>
          );
        })}
      </div>

      {/* Deduplication Modal */}
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
              Algunos códigos de las predicciones son similares a códigos existentes.
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
        .link-prediction-panel {
          padding: 1rem;
          background: #faf5ff;
          border-radius: 0.5rem;
          margin-bottom: 1rem;
        }
        .link-prediction-panel__title {
          margin: 0 0 0.5rem 0;
          font-size: 1.1rem;
          color: #7c3aed;
        }
        .link-prediction-panel__desc {
          margin: 0 0 1rem 0;
          font-size: 0.875rem;
          color: #64748b;
        }
        .link-prediction-panel__controls {
          display: flex;
          align-items: flex-end;
          gap: 1rem;
          flex-wrap: wrap;
        }
        .link-prediction-panel__field {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }
        .link-prediction-panel__field label {
          font-size: 0.8rem;
          color: #6b7280;
        }
        .link-prediction-panel__field select,
        .link-prediction-panel__field input {
          padding: 0.5rem;
          border: 1px solid #d1d5db;
          border-radius: 0.25rem;
        }
        .link-prediction-panel__field input[type="number"] {
          width: 70px;
        }
        .link-prediction-panel__algo-desc {
          display: block;
          margin-top: 0.5rem;
          padding: 0.5rem 0.75rem;
          background: linear-gradient(135deg, #f3e8ff, #ede9fe);
          border-radius: 0.5rem;
          font-size: 0.8rem;
          color: #5b21b6;
          line-height: 1.4;
          border-left: 3px solid #8b5cf6;
        }
        .link-prediction-panel__buttons {
          display: flex;
          gap: 0.5rem;
        }
        .link-prediction-panel__btn {
          padding: 0.5rem 1rem;
          border: none;
          border-radius: 0.375rem;
          cursor: pointer;
          font-size: 0.875rem;
        }
        .link-prediction-panel__btn--primary {
          background: #7c3aed;
          color: white;
        }
        .link-prediction-panel__btn--secondary {
          background: #e9d5ff;
          color: #7c3aed;
        }
        .link-prediction-panel__btn:disabled {
          opacity: 0.6;
        }
        .link-prediction-panel__error {
          margin-top: 0.75rem;
          padding: 0.5rem;
          background: #fef2f2;
          color: #dc2626;
          border-radius: 0.25rem;
        }
        .link-prediction-panel__results {
          margin-top: 1rem;
        }
        .link-prediction-panel__results h4 {
          margin: 0 0 0.5rem 0;
          font-size: 0.95rem;
        }
        .link-prediction-panel__algo {
          font-weight: normal;
          color: #6b7280;
          font-size: 0.8rem;
        }
        .link-prediction-panel__table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.875rem;
        }
        .link-prediction-panel__table th,
        .link-prediction-panel__table td {
          padding: 0.5rem;
          text-align: left;
          border-bottom: 1px solid #e5e7eb;
        }
        .link-prediction-panel__table th {
          background: #f3f4f6;
          font-weight: 600;
        }
        .link-prediction-panel__node {
          padding: 0.125rem 0.5rem;
          border-radius: 0.25rem;
          font-size: 0.8rem;
        }
        .link-prediction-panel__node--source {
          background: #fef3c7;
          color: #92400e;
        }
        .link-prediction-panel__node--target {
          background: #dbeafe;
          color: #1e40af;
        }
        .link-prediction-panel__apply {
          padding: 0.25rem 0.5rem;
          background: #10b981;
          color: white;
          border: none;
          border-radius: 0.25rem;
          cursor: pointer;
          font-size: 0.75rem;
        }
        .link-prediction-panel__ai-actions {
          margin-top: 1rem;
          display: flex;
          justify-content: flex-end;
        }
        .link-prediction-panel__btn--ai {
          background: linear-gradient(135deg, #8b5cf6, #6366f1);
          color: white;
          font-weight: 600;
          padding: 0.6rem 1.2rem;
        }
        .link-prediction-panel__btn--ai:hover:not(:disabled) {
          background: linear-gradient(135deg, #7c3aed, #4f46e5);
        }
        .link-prediction-panel__btn--ai:disabled {
          opacity: 0.7;
          cursor: wait;
        }
        .link-prediction-panel__ai-result {
          margin-top: 1rem;
          background: linear-gradient(135deg, #f3e8ff, #ede9fe);
          border: 1px solid #c4b5fd;
          border-radius: 0.75rem;
          padding: 1rem;
        }
        .link-prediction-panel__ai-result h4 {
          margin: 0 0 0.75rem 0;
          color: #5b21b6;
          font-size: 1rem;
        }
        .link-prediction-panel__ai-content {
          font-size: 0.9rem;
          line-height: 1.6;
          color: #374151;
        }
        .link-prediction-panel__ai-content p {
          margin: 0.5rem 0;
        }
        .link-prediction-panel__ai-content p:empty {
          display: none;
        }
        .link-prediction-panel__ai-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.75rem;
        }
        .link-prediction-panel__ai-header h4 {
          margin: 0;
          color: #5b21b6;
          font-size: 1rem;
        }
        .link-prediction-panel__btn--save {
          background: linear-gradient(135deg, #059669, #10b981);
          color: white;
          font-weight: 600;
          padding: 0.5rem 1rem;
          border-radius: 0.5rem;
          font-size: 0.85rem;
        }
        .link-prediction-panel__btn--save:hover {
          background: linear-gradient(135deg, #047857, #059669);
        }
        .link-prediction-panel__btn--candidates {
          background: linear-gradient(135deg, #f59e0b, #fbbf24);
          color: #1f2937;
          font-weight: 600;
          padding: 0.6rem 1.2rem;
        }
        .link-prediction-panel__btn--candidates:hover:not(:disabled) {
          background: linear-gradient(135deg, #d97706, #f59e0b);
        }
        .link-prediction-panel__success {
          margin-top: 0.75rem;
          padding: 0.5rem;
          background: #d1fae5;
          color: #047857;
          border-radius: 0.25rem;
          font-weight: 500;
        }
        .link-prediction-panel__evidence {
          margin-top: 1.25rem;
          padding-top: 1rem;
          border-top: 1px dashed #c4b5fd;
        }
        .link-prediction-panel__evidence h5 {
          margin: 0 0 0.75rem 0;
          color: #5b21b6;
          font-size: 0.95rem;
        }
        .link-prediction-panel__evidence-note {
          font-size: 0.85rem;
          color: #64748b;
          margin: 0 0 0.75rem 0;
          line-height: 1.5;
        }
        .link-prediction-panel__evidence-tips {
          display: flex;
          gap: 1rem;
          flex-wrap: wrap;
        }
        .link-prediction-panel__evidence-tip {
          background: white;
          padding: 0.5rem 0.75rem;
          border-radius: 0.5rem;
          font-size: 0.85rem;
          flex: 1;
          min-width: 180px;
          border: 1px solid #e5e7eb;
        }
        .link-prediction-panel__evidence-tip strong {
          color: #7c3aed;
        }
        .link-prediction-panel__reports {
          margin-top: 1.25rem;
          padding: 0.75rem;
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          border-radius: 0.75rem;
        }
        .link-prediction-panel__reports-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 0.5rem;
          margin-bottom: 0.75rem;
        }
        .link-prediction-panel__reports-header h4 {
          margin: 0;
          font-size: 0.95rem;
          color: #334155;
        }
        .link-prediction-panel__reports-empty {
          font-size: 0.85rem;
          color: #64748b;
        }
        .link-prediction-panel__report {
          background: white;
          border: 1px solid #e2e8f0;
          border-radius: 0.75rem;
          padding: 0.5rem 0.75rem;
          margin-bottom: 0.75rem;
        }
        .link-prediction-panel__report-summary {
          cursor: pointer;
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }
        .link-prediction-panel__report-title {
          font-weight: 700;
          color: #0f172a;
        }
        .link-prediction-panel__report-meta {
          font-size: 0.8rem;
          color: #64748b;
        }
        .link-prediction-panel__report-body {
          margin-top: 0.75rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .link-prediction-panel__report-actions {
          display: flex;
          gap: 0.5rem;
          justify-content: flex-end;
        }
        .link-prediction-panel__report-content {
          white-space: pre-wrap;
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          border-radius: 0.5rem;
          padding: 0.75rem;
          font-size: 0.85rem;
          color: #1f2937;
        }
        .link-prediction-panel__report-meta-box {
          background: #fff;
          border: 1px dashed #cbd5f5;
          border-radius: 0.5rem;
          padding: 0.5rem 0.75rem;
          font-size: 0.8rem;
          color: #475569;
        }
        .link-prediction-panel__report-meta-box pre {
          white-space: pre-wrap;
          margin: 0.35rem 0 0;
          font-size: 0.75rem;
        }
      `}</style>
      
      {/* Bandeja de validación de predicciones guardadas */}
      <LinkPredictionValidationPanel 
        project={project} 
        onRelationValidated={() => {
          // Las relaciones validadas se sincronizan a Neo4j automáticamente
        }} 
      />

      <AxialAiReviewPanel project={project} />
    </div>
  );
}

export default LinkPredictionPanel;
