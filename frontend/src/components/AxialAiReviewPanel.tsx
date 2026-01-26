import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AxialAiAnalysisDetail,
  AxialAiAnalysisListItem,
  AxialAiSuggestionDecision,
  AxialAiSuggestionDecisionResponse,
  decideAxialAiSuggestion,
  EpistemicStatement,
  getAxialAiAnalysis,
  listAxialAiAnalyses,
  updateAxialAiAnalysis,
} from "../services/api";
import { EpistemicBadge } from "./common/Analysis";

interface AxialAiReviewPanelProps {
  project: string;
}

export const AxialAiReviewPanel: React.FC<AxialAiReviewPanelProps> = ({ project }) => {
  const [items, setItems] = useState<AxialAiAnalysisListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [estadoFilter, setEstadoFilter] = useState<string>("pendiente");
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string>("");
  const [algorithmFilter, setAlgorithmFilter] = useState<string>("");
  const [epistemicModeFilter, setEpistemicModeFilter] = useState<string>("");
  const [hasEvidenceFilter, setHasEvidenceFilter] = useState<string>("with"); // with|without|all
  const [minScoreFilter, setMinScoreFilter] = useState<string>("");
  const [createdFrom, setCreatedFrom] = useState<string>("");
  const [createdTo, setCreatedTo] = useState<string>("");

  // Pagination
  const [offset, setOffset] = useState(0);
  const limit = 25;

  // Detail selection
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AxialAiAnalysisDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Review editing
  const [reviewEstado, setReviewEstado] = useState<"pendiente" | "validado" | "rechazado">("pendiente");
  const [reviewMemo, setReviewMemo] = useState<string>("");
  const [savingReview, setSavingReview] = useState(false);
  const [reviewSavedMsg, setReviewSavedMsg] = useState<string | null>(null);

  type SuggestionDecisionState = {
    loading: boolean;
    result?: AxialAiSuggestionDecisionResponse;
    error?: string;
  };
  const [suggestionDecisions, setSuggestionDecisions] = useState<Record<number, SuggestionDecisionState>>({});

  const fmtDate = useCallback((value?: string | null) => {
    if (!value) return "-";
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return String(value);
      return d.toLocaleString();
    } catch {
      return String(value);
    }
  }, []);

  const toIsoOrUndefined = useCallback((value: string) => {
    const clean = (value || "").trim();
    if (!clean) return undefined;
    const d = new Date(clean);
    if (Number.isNaN(d.getTime())) return undefined;
    return d.toISOString();
  }, []);

  const safeNum = useCallback((value: any) => {
    const n = typeof value === "number" ? value : Number(value);
    return Number.isFinite(n) ? n : 0;
  }, []);

  const fetchList = useCallback(async () => {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const minScoreNum = minScoreFilter.trim() ? Number(minScoreFilter) : undefined;
      const hasEvidence =
        hasEvidenceFilter === "all"
          ? undefined
          : hasEvidenceFilter === "with"
            ? true
            : false;
      const result = await listAxialAiAnalyses(project, {
        estado: estadoFilter || undefined,
        source_type: sourceTypeFilter || undefined,
        algorithm: algorithmFilter || undefined,
        epistemic_mode: epistemicModeFilter || undefined,
        created_from: toIsoOrUndefined(createdFrom),
        created_to: toIsoOrUndefined(createdTo),
        min_score: typeof minScoreNum === "number" && Number.isFinite(minScoreNum) ? minScoreNum : undefined,
        has_evidence: hasEvidence,
        limit,
        offset,
      });
      setItems(result.items || []);
      setTotal(result.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar análisis IA");
    } finally {
      setLoading(false);
    }
  }, [
    project,
    estadoFilter,
    sourceTypeFilter,
    algorithmFilter,
    epistemicModeFilter,
    hasEvidenceFilter,
    minScoreFilter,
    createdFrom,
    createdTo,
    offset,
    toIsoOrUndefined,
  ]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const fetchDetail = useCallback(async () => {
    if (!project || selectedId === null) return;
    setDetailLoading(true);
    setDetailError(null);
    try {
      const d = await getAxialAiAnalysis(selectedId, project);
      setDetail(d);
      const estado = (d.estado || "pendiente") as "pendiente" | "validado" | "rechazado";
      setReviewEstado(estado);
      setReviewMemo((d.review_memo || "").toString());
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "Error cargando detalle");
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, [project, selectedId]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  useEffect(() => {
    setSuggestionDecisions({});
  }, [selectedId]);

  const memoStatements: EpistemicStatement[] = useMemo(() => {
    if (!detail) return [];
    const ms = (detail as any).memo_statements;
    return Array.isArray(ms) ? (ms as EpistemicStatement[]) : [];
  }, [detail]);

  const evidencePack: any = useMemo(() => {
    if (!detail) return null;
    return (detail as any).evidence_json || null;
  }, [detail]);

  const evidenceSuggestions: any[] = useMemo(() => {
    if (!evidencePack || !Array.isArray(evidencePack.suggestions)) return [];
    return evidencePack.suggestions;
  }, [evidencePack]);

  const handleSaveReview = useCallback(async () => {
    if (!project || selectedId === null) return;
    setSavingReview(true);
    setReviewSavedMsg(null);
    setDetailError(null);
    try {
      await updateAxialAiAnalysis(selectedId, project, reviewEstado, reviewMemo);
      setReviewSavedMsg("✅ Revisión guardada");
      setTimeout(() => setReviewSavedMsg(null), 4000);
      await fetchDetail();
      await fetchList();
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "Error guardando revisión");
    } finally {
      setSavingReview(false);
    }
  }, [project, selectedId, reviewEstado, reviewMemo, fetchDetail, fetchList]);

  const handleSuggestionDecision = useCallback(
    async (suggestionId: number, decision: AxialAiSuggestionDecision) => {
      if (!project || selectedId === null) return;
      const sid = Number(suggestionId);
      if (!Number.isFinite(sid) || sid <= 0) return;

      setSuggestionDecisions((prev) => ({ ...prev, [sid]: { loading: true } }));

      try {
        const res = await decideAxialAiSuggestion(selectedId, project, sid, decision);
        setSuggestionDecisions((prev) => ({ ...prev, [sid]: { loading: false, result: res } }));
      } catch (err) {
        setSuggestionDecisions((prev) => ({
          ...prev,
          [sid]: {
            loading: false,
            error: err instanceof Error ? err.message : "Error aplicando decisión",
          },
        }));
      }
    },
    [project, selectedId]
  );

  return (
    <div className="axial-ai-review">
      <div className="axial-ai-review__header">
        <h4>🧾 Axial IA - Bandeja de Revisión</h4>
        <span className="axial-ai-review__meta">
          Proyecto: <code>{project}</code>
        </span>
      </div>

      {/* Filters */}
      <div className="axial-ai-review__filters">
        <div className="axial-ai-review__field">
          <label>Estado</label>
          <select value={estadoFilter} onChange={(e) => { setOffset(0); setEstadoFilter(e.target.value); }}>
            <option value="">Todos</option>
            <option value="pendiente">Pendiente</option>
            <option value="validado">Validado</option>
            <option value="rechazado">Rechazado</option>
          </select>
        </div>

        <div className="axial-ai-review__field">
          <label>Origen</label>
          <input value={sourceTypeFilter} onChange={(e) => { setOffset(0); setSourceTypeFilter(e.target.value); }} placeholder="analyze_predictions" />
        </div>

        <div className="axial-ai-review__field">
          <label>Algoritmo</label>
          <input value={algorithmFilter} onChange={(e) => { setOffset(0); setAlgorithmFilter(e.target.value); }} placeholder="community_based / jaccard…" />
        </div>

        <div className="axial-ai-review__field">
          <label>Epistemic</label>
          <input value={epistemicModeFilter} onChange={(e) => { setOffset(0); setEpistemicModeFilter(e.target.value); }} placeholder="constructivist / post_positivist" />
        </div>

        <div className="axial-ai-review__field">
          <label>Evidencia</label>
          <select value={hasEvidenceFilter} onChange={(e) => { setOffset(0); setHasEvidenceFilter(e.target.value); }}>
            <option value="with">Con evidencia</option>
            <option value="without">Sin evidencia</option>
            <option value="all">Todas</option>
          </select>
        </div>

        <div className="axial-ai-review__field">
          <label>Min score</label>
          <input value={minScoreFilter} onChange={(e) => { setOffset(0); setMinScoreFilter(e.target.value); }} placeholder="0.25" />
        </div>

        <div className="axial-ai-review__field">
          <label>Desde</label>
          <input type="datetime-local" value={createdFrom} onChange={(e) => { setOffset(0); setCreatedFrom(e.target.value); }} />
        </div>

        <div className="axial-ai-review__field">
          <label>Hasta</label>
          <input type="datetime-local" value={createdTo} onChange={(e) => { setOffset(0); setCreatedTo(e.target.value); }} />
        </div>

        <div className="axial-ai-review__field axial-ai-review__field--actions">
          <button onClick={() => { setOffset(0); fetchList(); }} disabled={loading}>
            {loading ? "Cargando…" : "Refrescar"}
          </button>
        </div>
      </div>

      {error && <div className="axial-ai-review__error">{error}</div>}

      <div className="axial-ai-review__grid">
        <div className="axial-ai-review__list">
          <div className="axial-ai-review__list-header">
            <strong>Artefactos</strong>
            <span className="axial-ai-review__muted">
              {items.length} / {total}
            </span>
          </div>

          <div className="axial-ai-review__rows">
            {items.map((it) => {
              const isActive = selectedId === it.id;
              return (
                <button
                  key={it.id}
                  className={`axial-ai-review__row ${isActive ? "axial-ai-review__row--active" : ""}`}
                  onClick={() => setSelectedId(it.id)}
                  title="Abrir detalle"
                >
                  <div className="axial-ai-review__row-top">
                    <span className="axial-ai-review__row-id">#{it.id}</span>
                    <span className={`axial-ai-review__pill axial-ai-review__pill--${it.estado}`}>
                      {it.estado}
                    </span>
                    {typeof it.has_evidence === "boolean" && (
                      <span
                        className={`axial-ai-review__pill ${
                          it.has_evidence ? "axial-ai-review__pill--ok" : "axial-ai-review__pill--warn"
                        }`}
                      >
                        {it.has_evidence
                          ? `evid +${it.evidence_positive ?? 0}/-${it.evidence_negative ?? 0}`
                          : "sin evidencia"}
                      </span>
                    )}
                  </div>
                  <div className="axial-ai-review__row-mid">
                    <span className="axial-ai-review__row-main">
                      {(it.algorithm || "—").toString()}
                      {it.max_score !== undefined ? (
                        <span className="axial-ai-review__row-score">
                          {" "}
                          max {safeNum(it.max_score).toFixed(3)}
                        </span>
                      ) : null}
                    </span>
                    <span className="axial-ai-review__row-date">{fmtDate(it.created_at)}</span>
                  </div>
                  <div className="axial-ai-review__row-sub">
                    <span className="axial-ai-review__muted">{it.epistemic_mode || ""}</span>
                    <span className="axial-ai-review__muted">{it.source_type || ""}</span>
                  </div>
                </button>
              );
            })}
            {items.length === 0 && !loading && (
              <div className="axial-ai-review__empty">No hay artefactos con esos filtros.</div>
            )}
          </div>

          <div className="axial-ai-review__pager">
            <button onClick={() => setOffset((o) => Math.max(0, o - limit))} disabled={offset === 0 || loading}>
              ←
            </button>
            <span className="axial-ai-review__muted">
              {offset + 1}–{Math.min(offset + limit, total)} / {total}
            </span>
            <button
              onClick={() => setOffset((o) => o + limit)}
              disabled={offset + limit >= total || loading}
            >
              →
            </button>
          </div>
        </div>

        <div className="axial-ai-review__detail">
          <div className="axial-ai-review__detail-header">
            <strong>Detalle</strong>
            {selectedId !== null && <span className="axial-ai-review__muted">#{selectedId}</span>}
          </div>

          <div className="axial-ai-review__detail-body">
            {detailError && <div className="axial-ai-review__error">{detailError}</div>}

            {selectedId === null && (
              <div className="axial-ai-review__empty">Selecciona un artefacto para ver el detalle.</div>
            )}

            {detailLoading && selectedId !== null && (
              <div className="axial-ai-review__empty">Cargando detalle…</div>
            )}

            {detail && (
              <>
                <div className="axial-ai-review__cards">
                  <div className="axial-ai-review__card">
                    <div className="axial-ai-review__card-title">Metadatos</div>
                    <div className="axial-ai-review__kv">
                      <div>
                        <span>Estado</span>
                        <code>{detail.estado}</code>
                      </div>
                      <div>
                        <span>Algoritmo</span>
                        <code>{detail.algorithm || ""}</code>
                      </div>
                      <div>
                        <span>Epistemic</span>
                        <code>{detail.epistemic_mode || ""}</code>
                      </div>
                      <div>
                        <span>Prompt</span>
                        <code>{detail.prompt_version || ""}</code>
                      </div>
                      <div>
                        <span>LLM</span>
                        <code>{detail.llm_deployment || ""}</code>
                      </div>
                      <div>
                        <span>Creado</span>
                        <span>{fmtDate(detail.created_at)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="axial-ai-review__card">
                    <div className="axial-ai-review__card-title">Revisión humana</div>
                    <div className="axial-ai-review__review">
                      <div className="axial-ai-review__review-row">
                        <label>Estado</label>
                        <select
                          value={reviewEstado}
                          onChange={(e) => setReviewEstado(e.target.value as any)}
                          disabled={savingReview}
                        >
                          <option value="pendiente">Pendiente</option>
                          <option value="validado">Validado</option>
                          <option value="rechazado">Rechazado</option>
                        </select>
                      </div>
                      <div className="axial-ai-review__review-row">
                        <label>Memo</label>
                        <textarea
                          value={reviewMemo}
                          onChange={(e) => setReviewMemo(e.target.value)}
                          rows={5}
                          placeholder="Decisión humana + motivo + evidencia…"
                          disabled={savingReview}
                        />
                      </div>
                      <div className="axial-ai-review__review-actions">
                        <button onClick={handleSaveReview} disabled={savingReview}>
                          {savingReview ? "Guardando…" : "Guardar"}
                        </button>
                        {reviewSavedMsg && <span className="axial-ai-review__ok">{reviewSavedMsg}</span>}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="axial-ai-review__section">
                  <div className="axial-ai-review__section-title">Memo IA (estructurado)</div>
                  {memoStatements.length > 0 ? (
                    <div className="axial-ai-review__memo">
                      {memoStatements.map((s, idx) => {
                        const type = (s.type || "").toUpperCase();
                        const ids = Array.isArray(s.evidence_ids) ? s.evidence_ids : [];
                        const fragIds = Array.isArray((s as any).evidence_fragment_ids)
                          ? (s as any).evidence_fragment_ids
                          : [];
                        return (
                          <div key={`${type}-${idx}`} className="axial-ai-review__memo-row">
                            <EpistemicBadge type={type} />
                            <div className="axial-ai-review__memo-text">
                              <div>{s.text}</div>
                              {(ids.length > 0 || fragIds.length > 0) && (
                                <div className="axial-ai-review__memo-evidence">
                                  {ids.length > 0 ? (
                                    <>
                                      links: <code>{ids.join(", ")}</code>
                                    </>
                                  ) : null}
                                  {fragIds.length > 0 ? (
                                    <>
                                      {" "}
                                      frags:{" "}
                                      <code>
                                        {fragIds.slice(0, 12).join(", ")}
                                        {fragIds.length > 12 ? "…" : ""}
                                      </code>
                                    </>
                                  ) : null}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="axial-ai-review__muted">
                      Sin memo estructurado; mostrando texto plano.
                      <pre className="axial-ai-review__pre">{(detail.analysis_text || "").toString()}</pre>
                    </div>
                  )}
                </div>

                <div className="axial-ai-review__section">
                  <div className="axial-ai-review__section-title">Evidencia (positivo + tensión)</div>
                  {!evidencePack && <div className="axial-ai-review__muted">No hay evidence pack persistido.</div>}
                  {evidencePack && (
                    <div className="axial-ai-review__evidence">
                      <div className="axial-ai-review__evidence-summary">
                        <span>
                          Totales: <code>+{safeNum(evidencePack?.totals?.positive)}</code>{" "}
                          <code>-{safeNum(evidencePack?.totals?.negative)}</code> · sugerencias{" "}
                          {evidenceSuggestions.length}
                        </span>
                        <span className="axial-ai-review__muted">
                          schema v{safeNum(evidencePack.schema_version)} · {fmtDate(evidencePack.generated_at)}
                        </span>
                      </div>

                      {evidencePack?.totals?.by_method && (
                        <div className="axial-ai-review__method-grid">
                          {Object.entries(evidencePack.totals.by_method as Record<string, number>).map(([k, v]) => (
                            <span key={k} className="axial-ai-review__pill axial-ai-review__pill--method">
                              {k}:{v}
                            </span>
                          ))}
                        </div>
                      )}

                      {evidenceSuggestions.length === 0 && (
                        <div className="axial-ai-review__muted">Sin sugerencias dentro del evidence pack.</div>
                      )}

                      {evidenceSuggestions.map((sug: any) => {
                        const sid = safeNum(sug.id);
                        const state = suggestionDecisions[sid];
                        const disabled = Boolean(state?.loading);
                        const okMsg =
                          state?.result?.success
                            ? `OK: #${state.result.prediction_id} -> ${state.result.estado}${
                                state.result.neo4j_synced ? " (Neo4j)" : ""
                              }`
                            : null;

                        return (
                          <details key={sug.id} className="axial-ai-review__details">
                          <summary>
                            <strong>{sug.id}.</strong>{" "}
                            <span className="axial-ai-review__pair">
                              {sug.source} ↔ {sug.target}
                            </span>{" "}
                            <span className="axial-ai-review__muted">
                              score {safeNum(sug.score).toFixed(3)} · +{(sug.positive || []).length}/-
                              {(sug.negative || []).length}
                            </span>
                          </summary>

                          <div className="axial-ai-review__decision-bar">
                            <button
                              className="axial-ai-review__btn axial-ai-review__btn--apply"
                              disabled={disabled}
                              onClick={(e) => {
                                e.preventDefault();
                                handleSuggestionDecision(sid, "validate_apply");
                              }}
                              title="Valida la sugerencia y la aplica (link_predictions + Neo4j)."
                            >
                              Validar y aplicar
                            </button>
                            <button
                              className="axial-ai-review__btn axial-ai-review__btn--close"
                              disabled={disabled}
                              onClick={(e) => {
                                e.preventDefault();
                                handleSuggestionDecision(sid, "reject_close");
                              }}
                              title="Rechaza y cierra la sugerencia (para que no reaparezca)."
                            >
                              Rechazar y cerrar
                            </button>

                            {state?.loading && <span className="axial-ai-review__muted">Procesando...</span>}
                            {okMsg && <span className="axial-ai-review__ok">{okMsg}</span>}
                            {state?.error && <span className="axial-ai-review__err">{state.error}</span>}
                          </div>

                          {sug.coverage && (
                            <div className="axial-ai-review__method-grid">
                              {Object.entries(sug.coverage as Record<string, number>).map(([k, v]) => (
                                <span key={k} className="axial-ai-review__pill axial-ai-review__pill--method">
                                  {k}:{v}
                                </span>
                              ))}
                            </div>
                          )}

                          {sug.notes && <div className="axial-ai-review__muted">{JSON.stringify(sug.notes)}</div>}

                          <div className="axial-ai-review__evidence-cols">
                            <div>
                              <div className="axial-ai-review__subhead">Positiva</div>
                              {(sug.positive || []).map((e: any) => (
                                <div key={e.fragmento_id} className="axial-ai-review__frag">
                                  <div className="axial-ai-review__frag-top">
                                    <code className="axial-ai-review__fid">{e.fragmento_id}</code>
                                    <span className="axial-ai-review__muted">
                                      {e.archivo}:{e.par_idx} · {e.speaker}
                                    </span>
                                    <span className="axial-ai-review__pill axial-ai-review__pill--method">
                                      {e.method}
                                    </span>
                                  </div>
                                  <div className="axial-ai-review__frag-text">“{(e.fragmento || "").toString()}”</div>
                                </div>
                              ))}
                              {(sug.positive || []).length === 0 && (
                                <div className="axial-ai-review__muted">Sin evidencia positiva.</div>
                              )}
                            </div>

                            <div>
                              <div className="axial-ai-review__subhead">Negativa (tensión)</div>
                              {(sug.negative || []).map((e: any) => (
                                <div key={e.fragmento_id} className="axial-ai-review__frag axial-ai-review__frag--neg">
                                  <div className="axial-ai-review__frag-top">
                                    <code className="axial-ai-review__fid">{e.fragmento_id}</code>
                                    <span className="axial-ai-review__muted">
                                      {e.archivo}:{e.par_idx} · {e.speaker}
                                    </span>
                                    <span className="axial-ai-review__pill axial-ai-review__pill--method">
                                      {e.method}
                                    </span>
                                  </div>
                                  {(e.present_source !== undefined || e.present_target !== undefined) && (
                                    <div className="axial-ai-review__muted">
                                      present(source={String(Boolean(e.present_source))}, target=
                                      {String(Boolean(e.present_target))})
                                    </div>
                                  )}
                                  <div className="axial-ai-review__frag-text">“{(e.fragmento || "").toString()}”</div>
                                </div>
                              ))}
                              {(sug.negative || []).length === 0 && (
                                <div className="axial-ai-review__muted">Sin casos en tensión.</div>
                              )}
                            </div>
                          </div>
                        </details>
                        );
                      })}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .axial-ai-review {
          margin-top: 1rem;
          padding: 1rem;
          background: #fff7ed;
          border: 1px solid #fed7aa;
          border-radius: 0.75rem;
        }
        .axial-ai-review__header {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: 0.75rem;
          margin-bottom: 0.75rem;
        }
        .axial-ai-review__header h4 {
          margin: 0;
          color: #9a3412;
          font-size: 1rem;
        }
        .axial-ai-review__meta {
          font-size: 0.85rem;
          color: #7c2d12;
        }
        .axial-ai-review__filters {
          display: flex;
          gap: 0.75rem;
          flex-wrap: wrap;
          align-items: flex-end;
          margin-bottom: 0.75rem;
        }
        .axial-ai-review__field {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
          min-width: 180px;
        }
        .axial-ai-review__field label {
          font-size: 0.78rem;
          color: #7c2d12;
          font-weight: 700;
        }
        .axial-ai-review__field input,
        .axial-ai-review__field select {
          padding: 0.45rem 0.55rem;
          border: 1px solid #fed7aa;
          border-radius: 0.5rem;
          font-size: 0.85rem;
          background: white;
          outline: none;
        }
        .axial-ai-review__field--actions {
          min-width: auto;
        }
        .axial-ai-review__field--actions button {
          padding: 0.55rem 0.75rem;
          border-radius: 0.5rem;
          border: 1px solid #fdba74;
          background: linear-gradient(135deg, #fb923c, #f97316);
          color: white;
          font-weight: 800;
          cursor: pointer;
        }
        .axial-ai-review__field--actions button:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        .axial-ai-review__error {
          padding: 0.6rem;
          background: #fee2e2;
          color: #991b1b;
          border-radius: 0.5rem;
          border: 1px solid #fecaca;
          margin-bottom: 0.75rem;
          font-size: 0.85rem;
        }
        .axial-ai-review__muted {
          color: #92400e;
          opacity: 0.95;
          font-size: 0.85rem;
        }
        .axial-ai-review__grid {
          display: grid;
          grid-template-columns: 360px 1fr;
          gap: 0.75rem;
          align-items: start;
        }
        .axial-ai-review__list,
        .axial-ai-review__detail {
          background: rgba(255, 255, 255, 0.85);
          border: 1px solid #fed7aa;
          border-radius: 0.75rem;
          overflow: hidden;
        }
        .axial-ai-review__list-header,
        .axial-ai-review__detail-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.65rem 0.75rem;
          background: #ffedd5;
          border-bottom: 1px solid #fed7aa;
        }
        .axial-ai-review__rows {
          display: flex;
          flex-direction: column;
          max-height: 540px;
          overflow: auto;
        }
        .axial-ai-review__row {
          text-align: left;
          padding: 0.65rem 0.75rem;
          border: none;
          border-bottom: 1px solid rgba(253, 186, 116, 0.35);
          background: transparent;
          cursor: pointer;
        }
        .axial-ai-review__row:hover {
          background: rgba(255, 237, 213, 0.65);
        }
        .axial-ai-review__row--active {
          background: rgba(251, 146, 60, 0.12);
        }
        .axial-ai-review__row-top {
          display: flex;
          gap: 0.4rem;
          align-items: center;
          flex-wrap: wrap;
          margin-bottom: 0.25rem;
        }
        .axial-ai-review__row-mid {
          display: flex;
          justify-content: space-between;
          gap: 0.5rem;
        }
        .axial-ai-review__row-sub {
          display: flex;
          justify-content: space-between;
          gap: 0.5rem;
          margin-top: 0.2rem;
        }
        .axial-ai-review__row-id {
          font-weight: 900;
          color: #9a3412;
        }
        .axial-ai-review__row-main {
          font-weight: 800;
          color: #7c2d12;
        }
        .axial-ai-review__row-score {
          margin-left: 0.25rem;
          font-size: 0.82rem;
          color: #9a3412;
        }
        .axial-ai-review__row-date {
          font-size: 0.78rem;
          color: #92400e;
        }
        .axial-ai-review__pill {
          padding: 0.15rem 0.45rem;
          border-radius: 999px;
          font-size: 0.74rem;
          border: 1px solid rgba(0, 0, 0, 0.08);
          background: white;
          color: #7c2d12;
        }
        .axial-ai-review__pill--pendiente {
          background: #fff7ed;
          border-color: #fed7aa;
        }
        .axial-ai-review__pill--validado {
          background: #dcfce7;
          border-color: #86efac;
          color: #065f46;
        }
        .axial-ai-review__pill--rechazado {
          background: #fee2e2;
          border-color: #fecaca;
          color: #991b1b;
        }
        .axial-ai-review__pill--ok {
          background: #dcfce7;
          border-color: #bbf7d0;
          color: #065f46;
        }
        .axial-ai-review__pill--warn {
          background: #ffedd5;
          border-color: #fdba74;
        }
        .axial-ai-review__pill--method {
          background: #fff;
          border-color: #fed7aa;
        }
        .axial-ai-review__pager {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 0.5rem;
          padding: 0.6rem 0.75rem;
          border-top: 1px solid rgba(253, 186, 116, 0.35);
        }
        .axial-ai-review__pager button {
          border: 1px solid #fed7aa;
          background: white;
          border-radius: 0.5rem;
          padding: 0.25rem 0.55rem;
          cursor: pointer;
          font-weight: 900;
          color: #7c2d12;
        }
        .axial-ai-review__pager button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .axial-ai-review__detail-body {
          padding: 0.75rem;
          max-height: 660px;
          overflow: auto;
        }
        .axial-ai-review__cards {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.75rem;
          margin-bottom: 0.75rem;
        }
        .axial-ai-review__card {
          border: 1px solid rgba(253, 186, 116, 0.55);
          border-radius: 0.75rem;
          background: white;
          padding: 0.75rem;
        }
        .axial-ai-review__card-title {
          font-weight: 900;
          color: #7c2d12;
          margin-bottom: 0.5rem;
        }
        .axial-ai-review__kv {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.35rem 0.75rem;
          font-size: 0.85rem;
          color: #7c2d12;
        }
        .axial-ai-review__kv div {
          display: flex;
          justify-content: space-between;
          gap: 0.5rem;
        }
        .axial-ai-review__review-row {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
          margin-bottom: 0.5rem;
        }
        .axial-ai-review__review-actions {
          display: flex;
          gap: 0.75rem;
          align-items: center;
        }
        .axial-ai-review__review-actions button {
          border: 1px solid #fdba74;
          background: #fff7ed;
          border-radius: 0.5rem;
          padding: 0.45rem 0.75rem;
          cursor: pointer;
          font-weight: 900;
          color: #7c2d12;
        }
        .axial-ai-review__ok {
          color: #047857;
          font-weight: 900;
          font-size: 0.85rem;
        }
        .axial-ai-review__section {
          margin-top: 0.75rem;
          padding-top: 0.75rem;
          border-top: 1px dashed rgba(253, 186, 116, 0.6);
        }
        .axial-ai-review__section-title {
          font-weight: 950;
          color: #7c2d12;
          margin-bottom: 0.5rem;
        }
        .axial-ai-review__memo {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .axial-ai-review__memo-row {
          display: flex;
          gap: 0.6rem;
          align-items: flex-start;
          background: white;
          border: 1px solid rgba(0, 0, 0, 0.06);
          border-radius: 0.75rem;
          padding: 0.55rem 0.6rem;
        }
        .axial-ai-review__memo-text {
          flex: 1;
          font-size: 0.92rem;
          color: #111827;
        }
        .axial-ai-review__memo-evidence {
          margin-top: 0.25rem;
          font-size: 0.78rem;
          color: #6b7280;
        }
        .axial-ai-review__pre {
          background: #111827;
          color: #f9fafb;
          padding: 0.75rem;
          border-radius: 0.75rem;
          overflow: auto;
          font-size: 0.82rem;
          line-height: 1.35;
          margin-top: 0.5rem;
        }
        .axial-ai-review__empty {
          padding: 0.75rem;
          color: #92400e;
          font-size: 0.85rem;
        }
        .axial-ai-review__evidence-summary {
          display: flex;
          justify-content: space-between;
          gap: 0.75rem;
          flex-wrap: wrap;
          margin-bottom: 0.5rem;
        }
        .axial-ai-review__method-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 0.35rem;
          margin: 0.5rem 0;
        }
        .axial-ai-review__details {
          background: rgba(255, 255, 255, 0.8);
          border: 1px solid rgba(253, 186, 116, 0.55);
          border-radius: 0.75rem;
          padding: 0.55rem 0.6rem;
          margin-top: 0.5rem;
        }
        .axial-ai-review__details summary {
          cursor: pointer;
        }
        .axial-ai-review__decision-bar {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
          align-items: center;
          margin: 0.5rem 0 0.65rem 0;
        }
        .axial-ai-review__btn {
          padding: 0.35rem 0.6rem;
          border-radius: 0.55rem;
          border: 1px solid rgba(253, 186, 116, 0.55);
          background: white;
          cursor: pointer;
          font-size: 0.85rem;
          font-weight: 800;
          color: #7c2d12;
        }
        .axial-ai-review__btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        .axial-ai-review__btn--apply {
          border-color: rgba(34, 197, 94, 0.55);
          background: rgba(240, 253, 244, 0.95);
          color: #14532d;
        }
        .axial-ai-review__btn--close {
          border-color: rgba(248, 113, 113, 0.55);
          background: rgba(254, 242, 242, 0.95);
          color: #7f1d1d;
        }
        .axial-ai-review__ok {
          font-size: 0.85rem;
          font-weight: 800;
          color: #14532d;
        }
        .axial-ai-review__err {
          font-size: 0.85rem;
          font-weight: 800;
          color: #7f1d1d;
        }
        .axial-ai-review__pair {
          font-weight: 950;
          color: #7c2d12;
        }
        .axial-ai-review__evidence-cols {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.75rem;
          margin-top: 0.5rem;
        }
        .axial-ai-review__subhead {
          font-weight: 900;
          color: #7c2d12;
          margin-bottom: 0.25rem;
        }
        .axial-ai-review__frag {
          border: 1px solid rgba(0, 0, 0, 0.06);
          border-radius: 0.75rem;
          padding: 0.55rem 0.6rem;
          background: white;
          margin-bottom: 0.5rem;
        }
        .axial-ai-review__frag--neg {
          background: #fff7ed;
          border-color: rgba(253, 186, 116, 0.55);
        }
        .axial-ai-review__frag-top {
          display: flex;
          gap: 0.5rem;
          align-items: center;
          flex-wrap: wrap;
          margin-bottom: 0.25rem;
        }
        .axial-ai-review__fid {
          font-weight: 950;
          color: #7c2d12;
        }
        .axial-ai-review__frag-text {
          font-size: 0.9rem;
          color: #111827;
          line-height: 1.35;
        }
        @media (max-width: 980px) {
          .axial-ai-review__grid {
            grid-template-columns: 1fr;
          }
          .axial-ai-review__cards {
            grid-template-columns: 1fr;
          }
          .axial-ai-review__evidence-cols {
            grid-template-columns: 1fr;
          }
          .axial-ai-review__field {
            min-width: 150px;
          }
        }
      `}</style>
    </div>
  );
};

export default AxialAiReviewPanel;
