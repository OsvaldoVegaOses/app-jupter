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

  // Sprint: Códigos a bandeja de candidatos
  const [sendingCodes, setSendingCodes] = useState(false);
  const [showDedupModal, setShowDedupModal] = useState(false);
  const [dedupResults, setDedupResults] = useState<BatchCheckResult[]>([]);
  const [codesToSend, setCodesToSend] = useState<string[]>([]);

  // Extraer códigos de los nodos del grafo
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
        answer: response.answer,
        context: response.context,
        nodes: response.nodes,
        relationships: response.relationships,
        fragments: response.fragments,
        project,
      });
      alert(`Reporte guardado en: ${res.path}`);
    } catch (err) {
      alert("Error al guardar reporte: " + (err instanceof Error ? err.message : String(err)));
    }
  }, [response, project]);

  // Enviar códigos extraídos a bandeja de candidatos
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
      alert(`Error verificando códigos: ${err instanceof Error ? err.message : String(err)}`);
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
          cita: firstFrag?.fragmento?.substring(0, 300) || response.answer.substring(0, 300),
          fragmento_id: firstFrag?.fragmento_id || "",
          archivo: firstFrag?.archivo || "graphrag_query",
          fuente_origen: "discovery_ai",  // Same source type for consistency
          score_confianza: 0.75,
          memo: `Código del grafo relacionado con: ${query.substring(0, 100)}`,
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
  }, [response, project, query]);

  return (
    <div className="graphrag-panel">
      <h3 className="graphrag-panel__title">
        🧠 GraphRAG - Chat con Contexto de Grafo
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
          <div className="graphrag-panel__answer">
            <h4>Respuesta</h4>
            <div className="graphrag-panel__answer-text">{response.answer}</div>
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
                💾 Guardar Informe
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
                  {sendingCodes ? "Enviando..." : `📋 Enviar ${extractedCodes.length} Códigos a Bandeja`}
                </button>
              )}
            </div>
          </div>

          {response.context && (
            <details className="graphrag-panel__context">
              <summary>Contexto del Grafo ({response.nodes.length} nodos)</summary>
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
                      📄 {frag.archivo}
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
                    {rel.from} →[{rel.type}]→ {rel.to}
                  </li>
                ))}
              </ul>
            </details>
          )}
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
              ⚠️ Códigos Similares Detectados
            </h3>
            <p style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: '1rem' }}>
              Algunos códigos del grafo son similares a códigos existentes.
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
      `}</style>
    </div>
  );
}

export default GraphRAGPanel;
