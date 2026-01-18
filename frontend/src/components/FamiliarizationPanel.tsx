/**
 * @fileoverview Panel de Familiarización - Etapa 2.
 *
 * Este componente permite revisar los fragmentos transcritos antes de
 * la codificación abierta, siguiendo la metodología de Teoría Fundamentada.
 *
 * @module components/FamiliarizationPanel
 */

import React, { useMemo, useState, useEffect, useCallback } from "react";
import { apiFetchJson, deleteFileData, getFamiliarizationReviews, setFamiliarizationReviewed } from "../services/api";

interface FamiliarizationPanelProps {
  project: string;
  onProgressChanged?: () => void;
}

interface FragmentInfo {
  id: string;
  text: string;
  speaker: string;
  archivo: string;
  fragmento_idx: number;
  char_count: number;
  interviewee_tokens: number;
  interviewer_tokens: number;
}

interface FragmentsResponse {
  fragments: FragmentInfo[];
  total: number;
  files: string[];
  project: string;
}

export function FamiliarizationPanel({ project, onProgressChanged }: FamiliarizationPanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fragments, setFragments] = useState<FragmentInfo[]>([]);
  const [files, setFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [expandedFragments, setExpandedFragments] = useState<Set<string>>(new Set());
  const [collapsedInterviews, setCollapsedInterviews] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [reviewedFiles, setReviewedFiles] = useState<Set<string>>(new Set());
  const [reviewProgress, setReviewProgress] = useState<{ reviewed: number; total: number; percentage: number } | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);

  const fetchFragments = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({ project });
      if (selectedFile) {
        params.append("file_filter", selectedFile);
      }
      const response = await apiFetchJson<FragmentsResponse>(
        `/api/familiarization/fragments?${params.toString()}`
      );
      setFragments(response.fragments);
      setFiles(response.files);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
  }, [project, selectedFile]);

  const fetchReviews = useCallback(async () => {
    setReviewLoading(true);
    try {
      const resp = await getFamiliarizationReviews(project);
      setReviewedFiles(new Set(resp.reviewed_files.map((r) => r.archivo)));
      setReviewProgress({
        reviewed: resp.reviewed_count,
        total: resp.total_interviews,
        percentage: resp.percentage,
      });
    } catch {
      // Non-fatal: keep panel usable even if Postgres isn't available
      setReviewProgress(null);
    } finally {
      setReviewLoading(false);
    }
  }, [project]);

  useEffect(() => {
    fetchFragments();
  }, [fetchFragments]);

  useEffect(() => {
    fetchReviews();
  }, [fetchReviews]);

  // Colapsar todas las entrevistas por defecto cuando cambian los archivos
  useEffect(() => {
    if (files.length > 0) {
      setCollapsedInterviews(new Set(files));
    }
  }, [files]);

  const toggleFragment = (id: string) => {
    setExpandedFragments(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedFragments(new Set(fragments.map(f => f.id)));
    setCollapsedInterviews(new Set()); // Mostrar todas las entrevistas
  };

  const collapseAll = () => {
    setExpandedFragments(new Set());
    setCollapsedInterviews(new Set(files)); // Ocultar todas las entrevistas
  };

  // Expand all fragments of a specific interview
  const expandInterview = (archivo: string) => {
    const fragsOfFile = fragments.filter(f => f.archivo === archivo);
    setExpandedFragments(prev => {
      const next = new Set(prev);
      fragsOfFile.forEach(f => next.add(f.id));
      return next;
    });
    // Also ensure interview is not collapsed
    setCollapsedInterviews(prev => {
      const next = new Set(prev);
      next.delete(archivo);
      return next;
    });
  };

  // Collapse all fragments of a specific interview
  const collapseInterview = (archivo: string) => {
    const fragsOfFile = fragments.filter(f => f.archivo === archivo);
    setExpandedFragments(prev => {
      const next = new Set(prev);
      fragsOfFile.forEach(f => next.delete(f.id));
      return next;
    });
  };

  // Toggle interview visibility (show/hide all fragments)
  const toggleInterviewCollapse = (archivo: string) => {
    setCollapsedInterviews(prev => {
      const next = new Set(prev);
      if (next.has(archivo)) {
        next.delete(archivo);
      } else {
        next.add(archivo);
      }
      return next;
    });
  };

  const handleDeleteFile = async () => {
    if (!selectedFile) return;
    if (!confirm(`¿Eliminar TODOS los datos de "${selectedFile}"?\n\nEsta acción borrará fragmentos, códigos y nodos en todas las bases de datos.\n\nNo se puede deshacer.`)) {
      return;
    }

    setDeleting(true);
    try {
      await deleteFileData(project, selectedFile);
      // Refresh fragments list
      const params = new URLSearchParams({ project });
      const response = await apiFetchJson<FragmentsResponse>(
        `/api/familiarization/fragments?${params.toString()}`
      );
      setFragments(response.fragments);
      setFiles(response.files);
      // Reset selection if file no longer exists
      if (!response.files.includes(selectedFile)) {
        setSelectedFile("");
      }
      alert(`Datos de "${selectedFile}" eliminados correctamente.`);
    } catch (err) {
      alert(`Error al eliminar: ${err instanceof Error ? err.message : "Error desconocido"}`);
    } finally {
      setDeleting(false);
    }
  };

  const isSelectedReviewed = useMemo(() => {
    if (!selectedFile) return false;
    return reviewedFiles.has(selectedFile);
  }, [selectedFile, reviewedFiles]);

  const toggleSelectedReviewed = useCallback(async () => {
    if (!selectedFile) return;
    await setFamiliarizationReviewed(project, selectedFile, !isSelectedReviewed);
    await fetchReviews();
    onProgressChanged?.();
  }, [project, selectedFile, isSelectedReviewed, fetchReviews, onProgressChanged]);

  // Group fragments by file
  const fragmentsByFile = fragments.reduce((acc, frag) => {
    if (!acc[frag.archivo]) {
      acc[frag.archivo] = [];
    }
    acc[frag.archivo].push(frag);
    return acc;
  }, {} as Record<string, FragmentInfo[]>);

  return (
    <div className="familiarization-panel">
      <header className="familiarization-panel__header">
        <h3>📖 Etapa 2 – Familiarización</h3>
        <p>
          Revisa los fragmentos transcritos antes de codificar. Verifica que los cortes
          respetan las unidades de significado y que no hay errores de transcripción.
        </p>
      </header>

      <div className="familiarization-panel__controls">
        <div className="familiarization-panel__filter">
          <label>Filtrar por entrevista:</label>
          <select
            value={selectedFile}
            onChange={(e) => setSelectedFile(e.target.value)}
            disabled={loading || deleting}
          >
            <option value="">Todas las entrevistas</option>
            {files.map((file) => (
              <option key={file} value={file}>
                {file}
              </option>
            ))}
          </select>

          {selectedFile && (
            <button
              onClick={toggleSelectedReviewed}
              disabled={reviewLoading || deleting}
              title="Marca esta entrevista como revisada en Familiarización"
              style={{ marginLeft: 8 }}
            >
              {isSelectedReviewed ? "↩ Desmarcar revisada" : "✅ Marcar revisada"}
            </button>
          )}

          {selectedFile && (
            <button
              className="familiarization-panel__delete-btn"
              onClick={handleDeleteFile}
              disabled={loading || deleting}
              title="Eliminar todos los datos de esta entrevista"
            >
              {deleting ? "Eliminando..." : "🗑️ Eliminar"}
            </button>
          )}
        </div>

        <div className="familiarization-panel__actions">
          <button onClick={expandAll} disabled={loading || fragments.length === 0}>
            Expandir todo
          </button>
          <button onClick={collapseAll} disabled={loading || fragments.length === 0}>
            Colapsar todo
          </button>
          <button onClick={fetchFragments} disabled={loading}>
            {loading ? "Cargando..." : "↻ Refrescar"}
          </button>
        </div>
      </div>

      {error && <div className="familiarization-panel__error">{error}</div>}

      <div className="familiarization-panel__stats">
        <span>📊 {fragments.length} fragmentos</span>
        <span>📁 {files.length} archivos</span>
        <span>🎤 {fragments.filter(f => f.speaker === "interviewee").length} del entrevistado</span>
        {reviewProgress && (
          <span>
            ✅ {reviewProgress.reviewed}/{reviewProgress.total} revisadas ({reviewProgress.percentage.toFixed(1)}%)
          </span>
        )}
      </div>

      {loading && fragments.length === 0 && (
        <div className="familiarization-panel__loading">Cargando fragmentos...</div>
      )}

      {!loading && fragments.length === 0 && (
        <div className="familiarization-panel__empty">
          <p>No hay fragmentos ingestados en este proyecto.</p>
          <p>Transcribe e ingesta entrevistas primero.</p>
        </div>
      )}

      <div className="familiarization-panel__content">
        {Object.entries(fragmentsByFile).map(([archivo, frags]) => (
          <div key={archivo} className="familiarization-panel__file-group">
            <div className="familiarization-panel__file-header">
              <h4
                className="familiarization-panel__file-title"
                onClick={() => toggleInterviewCollapse(archivo)}
                style={{ cursor: 'pointer' }}
              >
                {collapsedInterviews.has(archivo) ? '▶' : '▼'} 📄 {archivo} ({frags.length} fragmentos)
              </h4>
              <div className="familiarization-panel__file-actions">
                <button
                  onClick={() => expandInterview(archivo)}
                  disabled={collapsedInterviews.has(archivo)}
                  title="Expandir todos los fragmentos de esta entrevista"
                >
                  ⬇️ Expandir
                </button>
                <button
                  onClick={() => collapseInterview(archivo)}
                  disabled={collapsedInterviews.has(archivo)}
                  title="Colapsar todos los fragmentos de esta entrevista"
                >
                  ⬆️ Colapsar
                </button>
              </div>
            </div>
            {!collapsedInterviews.has(archivo) && (
              <ul className="familiarization-panel__list">
                {frags.map((frag, idx) => {
                  const isExpanded = expandedFragments.has(frag.id);
                  const isInterviewer = frag.speaker === "interviewer";

                  return (
                    <li
                      key={frag.id}
                      className={`familiarization-panel__item ${isInterviewer ? "familiarization-panel__item--interviewer" : ""}`}
                    >
                      <div
                        className="familiarization-panel__item-header"
                        onClick={() => toggleFragment(frag.id)}
                      >
                        <span className="familiarization-panel__item-index">
                          #{idx + 1}
                        </span>
                        <span className={`familiarization-panel__speaker familiarization-panel__speaker--${frag.speaker}`}>
                          {frag.speaker === "interviewee" ? "🗣️ Entrevistado" : "🎤 Entrevistador"}
                        </span>
                        <span className="familiarization-panel__chars">
                          {frag.char_count} chars
                        </span>
                        <span className="familiarization-panel__toggle">
                          {isExpanded ? "▼" : "▶"}
                        </span>
                      </div>

                      <div className={`familiarization-panel__preview ${isExpanded ? "" : "familiarization-panel__preview--collapsed"}`}>
                        {isExpanded ? frag.text : `${frag.text.substring(0, 150)}...`}
                      </div>

                      {isExpanded && (
                        <div className="familiarization-panel__item-footer">
                          <span>Tokens entrevistado: {frag.interviewee_tokens}</span>
                          {frag.interviewer_tokens > 0 && (
                            <span>Tokens entrevistador: {frag.interviewer_tokens}</span>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ))}
      </div>

      <style>{`
        .familiarization-panel {
          background: linear-gradient(135deg, #fef3c7, #fef9c3);
          border-radius: 1rem;
          padding: 1.5rem;
          margin-bottom: 1.5rem;
        }
        .familiarization-panel__header h3 {
          margin: 0 0 0.5rem;
          color: #92400e;
          font-size: 1.25rem;
        }
        .familiarization-panel__header p {
          margin: 0 0 1rem;
          color: #78350f;
          font-size: 0.9rem;
          opacity: 0.8;
        }
        .familiarization-panel__controls {
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 1rem;
          margin-bottom: 1rem;
        }
        .familiarization-panel__filter {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .familiarization-panel__filter label {
          font-size: 0.85rem;
          color: #78350f;
        }
        .familiarization-panel__filter select {
          padding: 0.4rem 0.75rem;
          border: 1px solid #fbbf24;
          border-radius: 0.375rem;
          background: white;
          font-size: 0.85rem;
        }
        .familiarization-panel__delete-btn {
          padding: 0.4rem 0.75rem;
          border: 1px solid #ef4444;
          border-radius: 0.375rem;
          background: #fef2f2;
          color: #dc2626;
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        .familiarization-panel__delete-btn:hover:not(:disabled) {
          background: #fee2e2;
          border-color: #dc2626;
        }
        .familiarization-panel__delete-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .familiarization-panel__actions {
          display: flex;
          gap: 0.5rem;
        }
        .familiarization-panel__actions button {
          padding: 0.4rem 0.75rem;
          border: 1px solid #f59e0b;
          border-radius: 0.375rem;
          background: white;
          color: #92400e;
          font-size: 0.8rem;
          cursor: pointer;
        }
        .familiarization-panel__actions button:hover:not(:disabled) {
          background: #fef3c7;
        }
        .familiarization-panel__actions button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .familiarization-panel__error {
          background: #fef2f2;
          color: #dc2626;
          padding: 0.75rem;
          border-radius: 0.375rem;
          margin-bottom: 1rem;
        }
        .familiarization-panel__stats {
          display: flex;
          gap: 1.5rem;
          font-size: 0.85rem;
          color: #78350f;
          margin-bottom: 1rem;
          padding: 0.5rem 0;
          border-bottom: 1px solid rgba(251, 191, 36, 0.3);
        }
        .familiarization-panel__loading,
        .familiarization-panel__empty {
          text-align: center;
          padding: 2rem;
          color: #92400e;
        }
        .familiarization-panel__file-group {
          margin-bottom: 1.5rem;
        }
        .familiarization-panel__file-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.75rem;
          padding-bottom: 0.5rem;
          border-bottom: 2px solid #fbbf24;
        }
        .familiarization-panel__file-title {
          margin: 0;
          font-size: 1rem;
          color: #78350f;
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .familiarization-panel__file-title:hover {
          color: #92400e;
        }
        .familiarization-panel__file-actions {
          display: flex;
          gap: 0.5rem;
        }
        .familiarization-panel__file-actions button {
          padding: 0.3rem 0.6rem;
          border: 1px solid #f59e0b;
          border-radius: 0.375rem;
          background: white;
          color: #92400e;
          font-size: 0.75rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        .familiarization-panel__file-actions button:hover:not(:disabled) {
          background: #fef3c7;
          border-color: #d97706;
        }
        .familiarization-panel__file-actions button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .familiarization-panel__list {
          list-style: none;
          margin: 0;
          padding: 0;
        }
        .familiarization-panel__item {
          background: white;
          border: 1px solid #fcd34d;
          border-radius: 0.5rem;
          margin-bottom: 0.5rem;
          overflow: hidden;
        }
        .familiarization-panel__item--interviewer {
          background: #f0f9ff;
          border-color: #93c5fd;
        }
        .familiarization-panel__item-header {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.75rem;
          cursor: pointer;
          background: rgba(251, 191, 36, 0.1);
        }
        .familiarization-panel__item--interviewer .familiarization-panel__item-header {
          background: rgba(147, 197, 253, 0.2);
        }
        .familiarization-panel__item-index {
          font-weight: 600;
          color: #92400e;
          min-width: 2.5rem;
        }
        .familiarization-panel__speaker {
          padding: 0.2rem 0.5rem;
          border-radius: 0.25rem;
          font-size: 0.75rem;
          font-weight: 500;
        }
        .familiarization-panel__speaker--interviewee {
          background: #d1fae5;
          color: #065f46;
        }
        .familiarization-panel__speaker--interviewer {
          background: #dbeafe;
          color: #1e40af;
        }
        .familiarization-panel__chars {
          margin-left: auto;
          font-size: 0.75rem;
          color: #9ca3af;
        }
        .familiarization-panel__toggle {
          color: #6b7280;
          font-size: 0.8rem;
        }
        .familiarization-panel__preview {
          padding: 0.75rem;
          font-size: 0.9rem;
          line-height: 1.6;
          color: #374151;
        }
        .familiarization-panel__preview--collapsed {
          color: #6b7280;
          font-style: italic;
        }
        .familiarization-panel__item-footer {
          display: flex;
          gap: 1rem;
          padding: 0.5rem 0.75rem;
          font-size: 0.75rem;
          color: #6b7280;
          background: rgba(0,0,0,0.02);
          border-top: 1px solid rgba(0,0,0,0.05);
        }
      `}</style>
    </div>
  );
}

export default FamiliarizationPanel;
