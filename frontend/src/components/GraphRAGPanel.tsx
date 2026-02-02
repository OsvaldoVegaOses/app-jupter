/**
 * @fileoverview Panel de GraphRAG - Chat con Contexto de Grafo.
 *
 * Este componente permite al usuario hacer preguntas que son
 * respondidas usando tanto busqueda semantica como el contexto
 * del grafo Neo4j.
 *
 * Funcionalidades:
 * - Input de pregunta con autocompletado
 * - Toggle para Chain of Thought
 * - Visualizacion de respuesta
 * - Contexto del grafo (nodos/relaciones)
 * - Fragmentos de evidencia
 *
 * @module components/GraphRAGPanel
 */

import React, { useState, useCallback, useMemo } from "react";
import { graphragQuery, saveGraphRAGReport, submitCandidate, checkBatchCodes, GraphRAGResponse, BatchCheckResult } from "../services/api";

interface GraphRAGPanelProps {
  project: string;
}

export function GraphRAGPanel({ project }: GraphRAGPanelProps) {
  const [query, setQuery] = useState("");
  const [chainOfThought, setChainOfThought] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<GraphRAGResponse | null>(null);

  // Sprint: CÃ³digos a bandeja de candidatos
  const [sendingCodes, setSendingCodes] = useState(false);
  const [showDedupModal, setShowDedupModal] = useState(false);
  const [dedupResults, setDedupResults] = useState<BatchCheckResult[]>([]);
  const [codesToSend, setCodesToSend] = useState<string[]>([]);

  // Extraer cÃ³digos de los nodos del grafo
  const extractedCodes = useMemo(() => {
    if (!response || !response.nodes) return [];
    return response.nodes
      .filter(n => n.type === 'Codigo' || n.type === 'Code')
      .map(n => n.id)
      .filter(Boolean);
  }, [response]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!query.trim()) return;

      setLoading(true);
      setError(null);

      try {
        const result = await graphragQuery({
          query: query.trim(),
          project,
          include_fragments: true,
          chain_of_thought: chainOfThought,
        });
        setResponse(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error desconocido");
      } finally {
        setLoading(false);
      }
    },
    [query, project, chainOfThought]
  );

  const handleSave = useCallback(async () => {
    if (!response) return;
    try {
      const res = await saveGraphRAGReport({
        query: response.query,
        answer: response.answer || '',
        context: response.context,
        nodes: response.nodes || [],
        relationships: response.relationships || [],
        fragments: response.fragments || [],
        project,
      });
      alert(`Reporte guardado en: ${res.path}`);
    } catch (err) {
      alert("Error al guardar reporte: " + (err instanceof Error ? err.message : String(err)));
    }
  }, [response, project]);

  // Enviar cÃ³digos extraÃ­dos a bandeja de candidatos
  const handleSendCodesToTray = useCallback(async () => {
    if (extractedCodes.length === 0 || !response) return;

    setSendingCodes(true);

    try {
      // Pre-check for similar codes
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
      alert(`Error verificando cÃ³digos: ${err instanceof Error ? err.message : String(err)}`);
      setSendingCodes(false);
    }
  }, [extractedCodes, response, project]);

  const sendCodesDirectly = useCallback(async (codigos: string[]) => {
    if (!response) return;

    setSendingCodes(true);
    let successCount = 0;

    try {
      for (const codigo of codigos) {
        const firstFrag = response.fragments?.[0];
        await submitCandidate({
          project,
          codigo: codigo.trim(),
          cita: firstFrag?.fragmento?.substring(0, 300) || response.answer?.substring(0, 300) || '',
          fragmento_id: firstFrag?.fragmento_id || "",
          archivo: firstFrag?.archivo || "graphrag_query",
          fuente_origen: "discovery_ai",  // Same source type for consistency
          score_confianza: 0.75,
          memo: `CÃ³digo del grafo relacionado con: ${query.substring(0, 100)}`,
        });
        successCount++;
      }
      alert(`âœ… ${successCount} cÃ³digos enviados a la Bandeja de Candidatos.\n\nRevÃ­salos en el Panel de ValidaciÃ³n.`);
      setShowDedupModal(false);
    } catch (err) {
      alert(`Error enviando cÃ³digos: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSendingCodes(false);
    }
  }, [response, project, query]);

  return (
    <div className="graphrag-panel">
      <h3 className="graphrag-panel__title">
        ðŸ§  GraphRAG - Chat con Contexto de Grafo
      </h3>

      <form onSubmit={handleSubmit} className="graphrag-panel__form">
        <div className="graphrag-panel__input-group">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Haz una pregunta sobre tu investigacion... (ej: Que factores causan la inseguridad?)"
            className="graphrag-panel__textarea"
            rows={3}
            disabled={loading}
          />
        </div>

        <div className="graphrag-panel__options">
          <label className="graphrag-panel__checkbox">
            <input
              type="checkbox"
              checked={chainOfThought}
              onChange={(e) => setChainOfThought(e.target.checked)}
              disabled={loading}
            />
            <span>Razonamiento paso a paso (Chain of Thought)</span>
          </label>

          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="graphrag-panel__submit"
          >
            {loading ? "Consultando..." : "Preguntar"}
          </button>
        </div>
      </form>

      {error && (
        <div className="graphrag-panel__error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {response && (
        <div className="graphrag-panel__response">

          {/* Header de Estado y Modo */}
          <div className="graphrag-panel__status-header" style={{ marginBottom: "0.75rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              {/* Mode Badge */}
              {response.mode && (
                <span className={`graphrag-panel__badge graphrag-panel__badge--${response.mode}`}>
                  {response.mode === 'deep' ? 'âš¡ DEEP SCAN' : response.mode === 'exploratory' ? 'ðŸ§­ EXPLORATORY' : 'âš ï¸ SIGNAL LOW'}
                </span>
              )}
              {/* Score Indicator */}
              {typeof response.relevance_score === 'number' && (
                <span className="graphrag-panel__score-indicator" title={`Relevancia de la evidencia: ${(response.relevance_score * 100).toFixed(0)}%`}>
                  Score: <strong>{response.relevance_score.toFixed(2)}</strong>
                  <span style={{
                    display: "inline-block",
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    backgroundColor: response.relevance_score >= 0.5 ? "#10b981" : response.relevance_score >= 0.25 ? "#f59e0b" : "#ef4444",
                    marginLeft: "0.25rem"
                  }}></span>
                </span>
              )}
            </div>
          </div>

          {/* Alerta de Fallback / Insufficient */}
          {response.fallback_reason && (
            <div className={`graphrag-panel__alert graphrag-panel__alert--${response.mode === 'insufficient' ? 'error' : 'warning'}`} style={{ marginBottom: '1rem' }}>
              <strong>{response.mode === 'insufficient' ? 'Analisis Detenido' : 'Cambio de Modo'}</strong>: {response.fallback_reason}
              <div className="graphrag-panel__alert-tooltip">
                â„¹ï¸ {response.mode === 'deep'
                  ? 'Se cumplen los criterios de rigor (Score > 0.5).'
                  : 'La IA cambiÃ³ de modo para priorizar la honestidad sobre la alucinaciÃ³n.'}
              </div>
            </div>
          )}

          <div className="graphrag-panel__answer">
            <h4>Respuesta</h4>

            {/* Graph Summary Destacado */}
            {response.graph_summary && (
              <div className="graphrag-panel__summary-box">
                <em>Resumen:</em> {response.graph_summary}
              </div>
            )}

            <div className="graphrag-panel__answer-text">{response.answer}</div>

            {/* Preguntas Sugeridas */}
            {response.questions && response.questions.length > 0 && (
              <div style={{ marginTop: "1rem", padding: "0.75rem", background: "#f0f9ff", borderRadius: "0.5rem", borderLeft: "3px solid #0ea5e9" }}>
                <h5 style={{ margin: "0 0 0.5rem", color: "#0284c7" }}>ðŸ” Preguntas para Profundizar</h5>
                <ul style={{ margin: 0, paddingLeft: "1.2rem", color: "#0c4a6e", fontSize: "0.9rem" }}>
                  {response.questions.map((q, i) => <li key={i}>{q}</li>)}
                </ul>
              </div>
            )}

            {/* Recomendaciones */}
            {response.recommendations && response.recommendations.length > 0 && (
              <div style={{ marginTop: "1rem", padding: "0.75rem", background: "#fefce8", borderRadius: "0.5rem", borderLeft: "3px solid #eab308" }}>
                <h5 style={{ margin: "0 0 0.5rem", color: "#ca8a04" }}>ðŸ’¡ Recomendaciones</h5>
                <ul style={{ margin: 0, paddingLeft: "1.2rem", color: "#713f12", fontSize: "0.9rem" }}>
                  {response.recommendations.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            )}

            <div style={{ marginTop: "1rem", textAlign: "right" }}>
              <button
                onClick={handleSave}
                className="graphrag-panel__save-btn"
                style={{
                  padding: "0.5rem 1rem",
                  fontSize: "0.85rem",
                  background: "#0f766e",
                  color: "white",
                  border: "none",
                  borderRadius: "0.375rem",
                  cursor: "pointer"
                }}
              >
                ðŸ’¾ Guardar Informe
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
                    marginLeft: "0.5rem",
                  }}
                >
                  {sendingCodes ? "Enviando..." : `ðŸ“‹ Enviar ${extractedCodes.length} CÃ³digos a Bandeja`}
                </button>
              )}
            </div>
          </div>

          {response.context && (
            <details className="graphrag-panel__context">
              <summary>Contexto del Grafo ({response.nodes?.length || 0} nodos)</summary>
              <pre className="graphrag-panel__context-pre">{response.context}</pre>
            </details>
          )}

          {response.fragments && response.fragments.length > 0 && (
            <details className="graphrag-panel__fragments">
              <summary>Fragmentos de Evidencia ({response.fragments.length})</summary>
              <ul className="graphrag-panel__fragment-list">
                {response.fragments.map((frag, idx) => (
                  <li key={frag.fragmento_id || idx} className="graphrag-panel__fragment-item">
                    <div className="graphrag-panel__fragment-source">
                      ðŸ“„ {frag.archivo}
                    </div>
                    <div className="graphrag-panel__fragment-text">
                      {frag.fragmento?.substring(0, 300)}...
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {response.relationships && response.relationships.length > 0 && (
            <details className="graphrag-panel__relationships">
              <summary>Relaciones ({response.relationships.length})</summary>
              <ul className="graphrag-panel__rel-list">
                {response.relationships.map((rel, idx) => (
                  <li key={idx}>
                    {rel.from} â†’[{rel.type}]â†’ {rel.to}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {/* Nodos Centrales */}
          {response.central_nodes && response.central_nodes.length > 0 && (
            <div className="graphrag-panel__central-nodes">
              <h4>ðŸŽ¯ Nodos Centrales (Top {response.central_nodes.length})</h4>
              <div className="graphrag-panel__nodes-grid">
                {response.central_nodes.map((node, idx) => {
                  const nodeId = node.code_id || node.id || node.label || `nodo-${idx}`;
                  const nodeLabel = node.label || node.id || node.code_id || 'Sin nombre';
                  const metricName = node.role || node.metric_name || node.metric || 'pagerank';
                  return (
                    <div key={nodeId} className="graphrag-panel__node-card">
                      <span className="graphrag-panel__node-rank">#{idx + 1}</span>
                      <span className="graphrag-panel__node-label">{nodeLabel}</span>
                      <span className={`graphrag-panel__node-badge graphrag-panel__node-badge--${metricName}`}>
                        {metricName}
                      </span>
                      <span className="graphrag-panel__node-score">
                        {typeof node.score === 'number' ? node.score.toFixed(3) : 'â€”'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Panel de Evidencia Estructurado */}
          {response.evidence && response.evidence.length > 0 && (
            <div className="graphrag-panel__evidence-panel">
              <h4>ðŸ“š Evidencia Trazable ({response.evidence.length} citas)</h4>
              <div className="graphrag-panel__evidence-list">
                {response.evidence.map((ev, idx) => (
                  <div key={ev.fragmento_id || ev.fragment_id || idx} className="graphrag-panel__evidence-item">
                    <div className="graphrag-panel__evidence-header">
                      <span className="graphrag-panel__evidence-citation">{ev.citation || `[${ev.rank || idx + 1}]`}</span>
                      <span className="graphrag-panel__evidence-doc">ðŸ“„ {ev.doc_ref || ev.archivo || 'Documento'}</span>
                      <span className={`graphrag-panel__evidence-score ${(ev.score || 0) >= 0.7 ? 'high' : (ev.score || 0) >= 0.5 ? 'medium' : 'low'}`}>
                        {typeof ev.score === 'number' ? `${(ev.score * 100).toFixed(0)}%` : 'â€”'}
                      </span>
                    </div>
                    <div className="graphrag-panel__evidence-snippet">
                      "{ev.snippet || ev.texto?.substring(0, 200) || ev.preview || '(sin extracto)'}"
                    </div>
                    <div className="graphrag-panel__evidence-footer">
                      <span className={`graphrag-panel__evidence-type graphrag-panel__evidence-type--${String(ev.supports || 'observation').toLowerCase()}`}>
                        {ev.supports || 'OBSERVATION'}
                      </span>
                      {ev.evidence_source && (
                        <span className="graphrag-panel__evidence-source">
                          via {ev.evidence_source}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Filtros Aplicados */}
          {response.filters_applied && Object.keys(response.filters_applied).length > 0 && (
            <details className="graphrag-panel__filters">
              <summary>ðŸ”§ Filtros Aplicados</summary>
              <div className="graphrag-panel__filters-content">
                {Object.entries(response.filters_applied).map(([key, value]) => (
                  <div key={key} className="graphrag-panel__filter-item">
                    <span className="graphrag-panel__filter-key">{key}:</span>
                    <span className="graphrag-panel__filter-value">
                      {typeof value === 'object' ? JSON.stringify(value) : String(value ?? 'â€”')}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Nivel de Confianza */}
          {response.confidence && (() => {
            const confLevel = typeof response.confidence === 'string'
              ? response.confidence
              : (response.confidence?.level || 'media');
            const confReason = typeof response.confidence === 'object'
              ? response.confidence?.reason
              : response.confidence_reason;
            return (
              <div className={`graphrag-panel__confidence graphrag-panel__confidence--${confLevel}`}>
                <span className="graphrag-panel__confidence-label">Confianza:</span>
                <span className="graphrag-panel__confidence-level">{confLevel.toUpperCase()}</span>
                {confReason && (
                  <span className="graphrag-panel__confidence-reason">â€” {confReason}</span>
                )}
              </div>
            );
          })()}
        </div>
      )}

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
              âš ï¸ CÃ³digos Similares Detectados
            </h3>
            <p style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: '1rem' }}>
              Algunos cÃ³digos del grafo son similares a cÃ³digos existentes.
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
                    alert('No hay cÃ³digos nuevos para enviar.');
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
                âœ… Enviar Solo Nuevos ({dedupResults.filter(r => !r.has_similar).length})
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
        .graphrag-panel {
          padding: 1rem;
          background: #f8fafc;
          border-radius: 0.5rem;
          margin-bottom: 1rem;
        }
        .graphrag-panel__title {
          margin: 0 0 1rem 0;
          font-size: 1.1rem;
          color: #1e293b;
        }
        .graphrag-panel__form {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .graphrag-panel__textarea {
          width: 100%;
          padding: 0.75rem;
          border: 1px solid #cbd5e1;
          border-radius: 0.375rem;
          font-size: 0.95rem;
          resize: vertical;
        }
        .graphrag-panel__textarea:focus {
          outline: none;
          border-color: #3b82f6;
          box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
        }
        .graphrag-panel__options {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 1rem;
        }
        .graphrag-panel__checkbox {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.875rem;
          color: #64748b;
        }
        .graphrag-panel__submit {
          padding: 0.5rem 1.5rem;
          background: #3b82f6;
          color: white;
          border: none;
          border-radius: 0.375rem;
          font-weight: 500;
          cursor: pointer;
        }
        .graphrag-panel__submit:hover:not(:disabled) {
          background: #2563eb;
        }
        .graphrag-panel__submit:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        .graphrag-panel__error {
          margin-top: 1rem;
          padding: 0.75rem;
          background: #fef2f2;
          border: 1px solid #fecaca;
          border-radius: 0.375rem;
          color: #dc2626;
        }
        .graphrag-panel__response {
          margin-top: 1rem;
        }
        .graphrag-panel__badge {
          display: inline-block;
          padding: 0.25rem 0.5rem;
          border-radius: 0.25rem;
          font-size: 0.75rem;
          font-weight: 700;
          text-transform: uppercase;
        }
        .graphrag-panel__badge--deep { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
        .graphrag-panel__badge--exploratory { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }
        .graphrag-panel__badge--insufficient { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
        
        .graphrag-panel__score-indicator { font-size: 0.8rem; color: #475569; display: flex; alignItems: center; }
        
        .graphrag-panel__alert { padding: 0.75rem; border-radius: 0.375rem; font-size: 0.9rem; }
        .graphrag-panel__alert--warning { background: #fffbeb; color: #92400e; border: 1px solid #fcd34d; }
        .graphrag-panel__alert--error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .graphrag-panel__alert-tooltip { margin-top: 0.25rem; font-size: 0.8rem; opacity: 0.9; }

        .graphrag-panel__status-header { margin-bottom: 0.75rem; display: flex; justify-content: space-between; align-items: center; }

        .graphrag-panel__summary-box { margin-bottom: 0.75rem; padding: 0.75rem; background: #f1f5f9; border-radius: 0.375rem; font-size: 0.9rem; color: #334155; }
        
        .graphrag-panel__answer {
          background: white;
          padding: 1rem;
          border-radius: 0.375rem;
          border: 1px solid #e2e8f0;
          margin-bottom: 0.75rem;
        }
        .graphrag-panel__answer h4 {
          margin: 0 0 0.5rem 0;
          font-size: 0.95rem;
          color: #64748b;
        }
        .graphrag-panel__answer-text {
          white-space: pre-wrap;
          line-height: 1.6;
        }
        .graphrag-panel__context,
        .graphrag-panel__fragments,
        .graphrag-panel__relationships {
          margin-top: 0.5rem;
        }
        .graphrag-panel__context summary,
        .graphrag-panel__fragments summary,
        .graphrag-panel__relationships summary {
          cursor: pointer;
          padding: 0.5rem;
          background: #f1f5f9;
          border-radius: 0.25rem;
          font-size: 0.875rem;
        }
        .graphrag-panel__context-pre {
          margin: 0.5rem 0 0 0;
          padding: 0.75rem;
          background: #1e293b;
          color: #e2e8f0;
          border-radius: 0.25rem;
          font-size: 0.8rem;
          overflow-x: auto;
          white-space: pre-wrap;
        }
        .graphrag-panel__fragment-list {
          margin: 0.5rem 0 0 0;
          padding: 0;
          list-style: none;
        }
        .graphrag-panel__fragment-item {
          padding: 0.5rem;
          background: white;
          border: 1px solid #e2e8f0;
          border-radius: 0.25rem;
          margin-bottom: 0.5rem;
        }
        .graphrag-panel__fragment-source {
          font-size: 0.8rem;
          color: #64748b;
          margin-bottom: 0.25rem;
        }
        .graphrag-panel__fragment-text {
          font-size: 0.875rem;
          color: #475569;
        }
        .graphrag-panel__rel-list {
          margin: 0.5rem 0 0 0;
          padding-left: 1.5rem;
          font-size: 0.875rem;
        }
        /* Top N Nodos Centrales */
        .graphrag-panel__central-nodes {
          margin-top: 1rem;
          padding: 1rem;
          background: linear-gradient(135deg, #f0fdf4, #ecfdf5);
          border: 1px solid #86efac;
          border-radius: 0.5rem;
        }
        .graphrag-panel__central-nodes h4 {
          margin: 0 0 0.75rem 0;
          font-size: 0.95rem;
          color: #166534;
        }
        .graphrag-panel__nodes-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem;
        }
        .graphrag-panel__node-card {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem 0.75rem;
          background: white;
          border-radius: 0.375rem;
          border: 1px solid #d1fae5;
          font-size: 0.875rem;
        }
        .graphrag-panel__node-rank {
          font-weight: 700;
          color: #059669;
        }
        .graphrag-panel__node-label {
          font-weight: 500;
          color: #1e293b;
        }
        .graphrag-panel__node-badge {
          padding: 0.125rem 0.375rem;
          border-radius: 9999px;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
        }
        .graphrag-panel__node-badge--pagerank {
          background: #dbeafe;
          color: #1d4ed8;
        }
        .graphrag-panel__node-badge--degree {
          background: #fef3c7;
          color: #b45309;
        }
        .graphrag-panel__node-badge--betweenness {
          background: #f3e8ff;
          color: #7c3aed;
        }
        .graphrag-panel__node-score {
          font-family: monospace;
          font-size: 0.8rem;
          color: #64748b;
        }
        /* Panel de Evidencia */
        .graphrag-panel__evidence-panel {
          margin-top: 1rem;
          padding: 1rem;
          background: linear-gradient(135deg, #fefce8, #fef9c3);
          border: 1px solid #fde047;
          border-radius: 0.5rem;
        }
        .graphrag-panel__evidence-panel h4 {
          margin: 0 0 0.75rem 0;
          font-size: 0.95rem;
          color: #854d0e;
        }
        .graphrag-panel__evidence-list {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .graphrag-panel__evidence-item {
          background: white;
          border-radius: 0.375rem;
          border: 1px solid #fde68a;
          overflow: hidden;
        }
        .graphrag-panel__evidence-header {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.5rem 0.75rem;
          background: #fefce8;
          border-bottom: 1px solid #fde68a;
        }
        .graphrag-panel__evidence-citation {
          font-weight: 700;
          color: #b45309;
        }
        .graphrag-panel__evidence-doc {
          flex: 1;
          font-size: 0.8rem;
          color: #64748b;
        }
        .graphrag-panel__evidence-score {
          padding: 0.125rem 0.5rem;
          border-radius: 9999px;
          font-size: 0.75rem;
          font-weight: 600;
        }
        .graphrag-panel__evidence-score.high {
          background: #dcfce7;
          color: #166534;
        }
        .graphrag-panel__evidence-score.medium {
          background: #fef3c7;
          color: #b45309;
        }
        .graphrag-panel__evidence-score.low {
          background: #fee2e2;
          color: #dc2626;
        }
        .graphrag-panel__evidence-snippet {
          padding: 0.75rem;
          font-size: 0.875rem;
          font-style: italic;
          color: #475569;
          line-height: 1.5;
        }
        .graphrag-panel__evidence-footer {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.375rem 0.75rem;
          background: #fffbeb;
          border-top: 1px solid #fde68a;
          font-size: 0.75rem;
        }
        .graphrag-panel__evidence-type {
          padding: 0.125rem 0.5rem;
          border-radius: 0.25rem;
          font-weight: 600;
          text-transform: uppercase;
        }
        .graphrag-panel__evidence-type--observation {
          background: #dbeafe;
          color: #1d4ed8;
        }
        .graphrag-panel__evidence-type--interpretation {
          background: #f3e8ff;
          color: #7c3aed;
        }
        .graphrag-panel__evidence-type--hypothesis {
          background: #fce7f3;
          color: #be185d;
        }
        .graphrag-panel__evidence-source {
          color: #94a3b8;
        }
        /* Filtros Aplicados */
        .graphrag-panel__filters {
          margin-top: 0.75rem;
        }
        .graphrag-panel__filters summary {
          cursor: pointer;
          padding: 0.5rem;
          background: #f1f5f9;
          border-radius: 0.25rem;
          font-size: 0.875rem;
        }
        .graphrag-panel__filters-content {
          margin-top: 0.5rem;
          padding: 0.75rem;
          background: white;
          border: 1px solid #e2e8f0;
          border-radius: 0.25rem;
        }
        .graphrag-panel__filter-item {
          display: flex;
          gap: 0.5rem;
          font-size: 0.8rem;
          margin-bottom: 0.25rem;
        }
        .graphrag-panel__filter-key {
          color: #64748b;
          font-weight: 500;
        }
        .graphrag-panel__filter-value {
          color: #1e293b;
          font-family: monospace;
        }
        /* Nivel de Confianza */
        .graphrag-panel__confidence {
          margin-top: 1rem;
          padding: 0.75rem 1rem;
          border-radius: 0.5rem;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.875rem;
        }
        .graphrag-panel__confidence--alta {
          background: linear-gradient(135deg, #dcfce7, #bbf7d0);
          border: 1px solid #86efac;
        }
        .graphrag-panel__confidence--media {
          background: linear-gradient(135deg, #fef3c7, #fde68a);
          border: 1px solid #fcd34d;
        }
        .graphrag-panel__confidence--baja {
          background: linear-gradient(135deg, #fee2e2, #fecaca);
          border: 1px solid #fca5a5;
        }
        .graphrag-panel__confidence-label {
          color: #64748b;
        }
        .graphrag-panel__confidence-level {
          font-weight: 700;
        }
        .graphrag-panel__confidence--alta .graphrag-panel__confidence-level {
          color: #166534;
        }
        .graphrag-panel__confidence--media .graphrag-panel__confidence-level {
          color: #b45309;
        }
        .graphrag-panel__confidence--baja .graphrag-panel__confidence-level {
          color: #dc2626;
        }
        .graphrag-panel__confidence-reason {
          color: #64748b;
          font-size: 0.8rem;
        }
      `}</style>
    </div>
  );
}

export default GraphRAGPanel;
