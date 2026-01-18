/**
 * AgentPanel - Panel de control del Agente Autónomo de Investigación
 * 
 * Permite iniciar el agente, ver progreso y revisar resultados.
 * 
 * Sprint 29 - Enero 2026
 */

import React, { useCallback, useRef, useState } from 'react';
import { apiFetchJson } from "../services/api";

interface AgentTask {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'error';
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
  };
  message?: string;
}

interface AgentResult {
  project_id: string;
  status: string;
  iterations: number;
  validated_codes: string[];
  discovery_memos: string[];
  saturation_score: number;
  final_report?: string;
  errors?: string[];
  final_landing_rate?: {
    landing_rate: number;
    matched_count: number;
    total_count: number;
    matched_codes?: string[];
  };
  logs?: string[];
}

const STAGE_NAMES: Record<number, string> = {
  0: 'Preparación',
  1: 'Ingesta',
  2: 'Discovery',
  3: 'Codificación',
  4: 'Análisis Axial',
  9: 'Reporte Final',
};

const API_BASE = '/api/agent';

export const AgentPanel: React.FC<{ project: string }> = ({ project }) => {
  const [concepts, setConcepts] = useState('rol_municipal_planificacion');
  const [maxIterations, setMaxIterations] = useState(30);
  const [discoveryOnly, setDiscoveryOnly] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [currentTask, setCurrentTask] = useState<AgentTask | null>(null);
  const [result, setResult] = useState<AgentResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollingIntervalRef = useRef<number | null>(null);

  const parseConcepts = useCallback((): string[] => {
    return concepts
      .split(/\n|,/)
      .map((c) => c.trim())
      .filter(Boolean);
  }, [concepts]);

  // Start agent execution
  const startAgent = useCallback(async () => {
    if (!project) {
      setError('Selecciona un proyecto primero');
      return;
    }

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await apiFetchJson<{ task_id: string; status?: string; message?: string }>(
        `${API_BASE}/execute`,
        {
          method: "POST",
          body: JSON.stringify({
            project_id: project,
            concepts: parseConcepts(),
            max_iterations: maxIterations,
            discovery_only: discoveryOnly,
          }),
        }
      );
      setCurrentTask({
        task_id: data.task_id,
        status: 'pending',
        current_stage: 0,
        iteration: 0,
        memos_count: 0,
        codes_count: 0,
      });

      // Start polling
      if (pollingIntervalRef.current) {
        window.clearInterval(pollingIntervalRef.current);
      }
      pollingIntervalRef.current = window.setInterval(() => pollStatus(data.task_id), 2000);

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      setIsLoading(false);
    }
  }, [project, maxIterations, discoveryOnly, parseConcepts]);

  // Poll task status
  const pollStatus = useCallback(async (taskId: string) => {
    try {
      const status = await apiFetchJson<AgentTask>(`${API_BASE}/status/${taskId}`);
      setCurrentTask(status);

      if (status.status === 'completed' || status.status === 'error') {
        // Stop polling
        if (pollingIntervalRef.current) {
          window.clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        setIsLoading(false);

        // Fetch result if completed
        if (status.status === 'completed') {
          const resultData = await apiFetchJson<AgentResult>(`${API_BASE}/result/${taskId}`);
          // /result no siempre incluye errors/final_landing_rate; tomarlo de /status.
          setResult({
            ...resultData,
            errors: status.errors,
            final_landing_rate: status.final_landing_rate,
          });
        } else if (status.status === 'error') {
          setError(status.message || 'Error durante ejecución');
        }
      }
    } catch (err) {
      console.error('Poll error:', err);
    }
  }, []);

  // Stop agent
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      window.clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setIsLoading(false);
  }, []);

  return (
    <div className="agent-panel">
      <div className="agent-header">
        <h3>🤖 Agente Autónomo de Investigación</h3>
        <p className="subtitle">
          Ejecuta el pipeline completo de Grounded Theory de forma autónoma
        </p>
      </div>

      {/* Configuration */}
      <div className="agent-config">
        <div className="config-row">
          <label>Proyecto:</label>
          <span className="project-name">{project || '(ninguno)'}</span>
        </div>

        <div className="config-row">
          <label htmlFor="concepts">Conceptos a explorar:</label>
          <input
            id="concepts"
            type="text"
            value={concepts}
            onChange={(e) => setConcepts(e.target.value)}
            placeholder="concepto1, concepto2, ..."
            disabled={isLoading}
          />
        </div>

        <div className="config-row">
          <label htmlFor="maxIter">Máx. iteraciones:</label>
          <input
            id="maxIter"
            type="number"
            min={5}
            max={100}
            value={maxIterations}
            onChange={(e) => setMaxIterations(Number(e.target.value))}
            disabled={isLoading}
          />
        </div>

        <div className="config-row checkbox">
          <input
            id="discoveryOnly"
            type="checkbox"
            checked={discoveryOnly}
            onChange={(e) => setDiscoveryOnly(e.target.checked)}
            disabled={isLoading}
          />
          <label htmlFor="discoveryOnly">Solo Discovery (sin codificación)</label>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="agent-actions">
        <button
          className="btn-primary btn-execute"
          onClick={startAgent}
          disabled={isLoading || !project}
        >
          {isLoading ? '⏳ Ejecutando...' : '▶️ Ejecutar Agente'}
        </button>

        {isLoading && (
          <button className="btn-secondary btn-stop" onClick={stopPolling}>
            ⏹️ Detener
          </button>
        )}
      </div>

      {/* Progress */}
      {currentTask && isLoading && (
        <div className="agent-progress">
          <div className="progress-header">
            <span>Etapa: {STAGE_NAMES[currentTask.current_stage] || `Stage ${currentTask.current_stage}`}</span>
            <span>Iteración: {currentTask.iteration}</span>
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${Math.min((currentTask.current_stage / 9) * 100, 100)}%` }}
            />
          </div>
          <div className="progress-stats">
            <span>📝 Memos: {currentTask.memos_count}</span>
            <span>🏷️ Códigos: {currentTask.codes_count}</span>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="agent-error">
          ❌ {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="agent-result">
          <h4>✅ Ejecución Completada</h4>
          <div className="result-stats">
            <div className="stat">
              <span className="stat-value">{result.iterations}</span>
              <span className="stat-label">Iteraciones</span>
            </div>
            <div className="stat">
              <span className="stat-value">{result.validated_codes.length}</span>
              <span className="stat-label">Códigos</span>
            </div>
            <div className="stat">
              <span className="stat-value">{result.discovery_memos.length}</span>
              <span className="stat-label">Memos</span>
            </div>
            <div className="stat">
              <span className="stat-value">{(result.saturation_score * 100).toFixed(0)}%</span>
              <span className="stat-label">Saturación</span>
            </div>
          </div>

          {result.validated_codes.length > 0 && (
            <div className="result-codes">
              <h5>Códigos generados:</h5>
              <ul>
                {result.validated_codes.slice(0, 10).map((code, i) => (
                  <li key={i}>{code}</li>
                ))}
              </ul>
            </div>
          )}

          {result.discovery_memos.length > 0 && (
            <div className="result-memos">
              <h5>Memos guardados:</h5>
              <ul>
                {result.discovery_memos.slice(0, 5).map((memo, i) => (
                  <li key={i}>{memo}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Logs de ejecución */}
          {result.logs && result.logs.length > 0 && (
            <div className="result-logs">
              <h5>📋 Logs de ejecución:</h5>
              <ul className="logs-list">
                {result.logs.map((log, i) => (
                  <li key={i}>{log}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Errores */}
          {result.errors && result.errors.length > 0 && (
            <div className="result-errors">
              <h5>⚠️ Errores ({result.errors.length}):</h5>
              <ul className="errors-list">
                {result.errors.slice(0, 5).map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
                {result.errors.length > 5 && (
                  <li>... y {result.errors.length - 5} más</li>
                )}
              </ul>
            </div>
          )}

          {/* Landing Rate */}
          {result.final_landing_rate && (
            <div className="result-landing-rate">
              <h5>📊 Landing Rate Final:</h5>
              <div className="landing-rate-stats">
                <span className="lr-value">
                  {result.final_landing_rate.landing_rate.toFixed(1)}%
                </span>
                <span className="lr-detail">
                  ({result.final_landing_rate.matched_count} de {result.final_landing_rate.total_count} fragmentos)
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      <style>{`
        .agent-panel {
          padding: 20px;
          background: var(--bg-secondary, #1a1a2e);
          border-radius: 12px;
          border: 1px solid var(--border-color, #333);
        }

        .agent-header h3 {
          margin: 0 0 4px 0;
          color: var(--text-primary, #fff);
        }

        .agent-header .subtitle {
          margin: 0;
          color: var(--text-secondary, #888);
          font-size: 0.9rem;
        }

        .agent-config {
          margin: 20px 0;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .config-row {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .config-row label {
          min-width: 160px;
          color: var(--text-secondary, #aaa);
        }

        .config-row input[type="text"],
        .config-row input[type="number"] {
          flex: 1;
          padding: 8px 12px;
          border: 1px solid var(--border-color, #444);
          border-radius: 6px;
          background: var(--bg-tertiary, #0f0f1a);
          color: var(--text-primary, #fff);
        }

        .config-row.checkbox {
          gap: 8px;
        }

        .config-row.checkbox label {
          min-width: auto;
        }

        .project-name {
          color: var(--accent, #00d4ff);
          font-weight: 500;
        }

        .agent-actions {
          display: flex;
          gap: 12px;
          margin-bottom: 20px;
        }

        .btn-execute {
          padding: 12px 24px;
          font-size: 1rem;
          background: linear-gradient(135deg, #00d4ff, #0099cc);
          border: none;
          border-radius: 8px;
          color: #000;
          font-weight: 600;
          cursor: pointer;
          transition: transform 0.2s, box-shadow 0.2s;
        }

        .btn-execute:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 4px 20px rgba(0, 212, 255, 0.3);
        }

        .btn-execute:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .btn-stop {
          padding: 12px 20px;
          background: #cc3333;
          border: none;
          border-radius: 8px;
          color: #fff;
          cursor: pointer;
        }

        .agent-progress {
          padding: 16px;
          background: var(--bg-tertiary, #0f0f1a);
          border-radius: 8px;
          margin-bottom: 16px;
        }

        .progress-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 8px;
          color: var(--text-secondary, #aaa);
          font-size: 0.9rem;
        }

        .progress-bar {
          height: 8px;
          background: #333;
          border-radius: 4px;
          overflow: hidden;
          margin-bottom: 12px;
        }

        .progress-fill {
          height: 100%;
          background: linear-gradient(90deg, #00d4ff, #00ff88);
          transition: width 0.3s ease;
        }

        .progress-stats {
          display: flex;
          gap: 20px;
          color: var(--text-secondary, #888);
          font-size: 0.85rem;
        }

        .agent-error {
          padding: 12px 16px;
          background: rgba(204, 51, 51, 0.2);
          border: 1px solid #cc3333;
          border-radius: 8px;
          color: #ff6666;
          margin-bottom: 16px;
        }

        .agent-result {
          padding: 20px;
          background: rgba(0, 255, 136, 0.1);
          border: 1px solid #00ff88;
          border-radius: 8px;
        }

        .agent-result h4 {
          margin: 0 0 16px 0;
          color: #00ff88;
        }

        .result-stats {
          display: flex;
          gap: 24px;
          margin-bottom: 20px;
        }

        .stat {
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .stat-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--text-primary, #fff);
        }

        .stat-label {
          font-size: 0.8rem;
          color: var(--text-secondary, #888);
        }

        .result-codes, .result-memos {
          margin-top: 16px;
        }

        .result-codes h5, .result-memos h5 {
          margin: 0 0 8px 0;
          color: var(--text-secondary, #aaa);
          font-size: 0.9rem;
        }

        .result-codes ul, .result-memos ul {
          margin: 0;
          padding-left: 20px;
        }

        .result-codes li, .result-memos li {
          color: var(--text-primary, #fff);
          font-size: 0.9rem;
          margin-bottom: 4px;
        }

        .result-logs {
          margin-top: 16px;
          padding: 12px;
          background: rgba(0, 100, 200, 0.1);
          border-radius: 6px;
        }

        .result-logs h5 {
          margin: 0 0 8px 0;
          color: #00d4ff;
          font-size: 0.9rem;
        }

        .logs-list {
          margin: 0;
          padding: 0;
          list-style: none;
          font-family: monospace;
          font-size: 0.85rem;
        }

        .logs-list li {
          color: var(--text-secondary, #aaa);
          padding: 4px 0;
          border-bottom: 1px solid rgba(255,255,255,0.05);
        }

        .result-errors {
          margin-top: 16px;
          padding: 12px;
          background: rgba(204, 51, 51, 0.1);
          border-radius: 6px;
        }

        .result-errors h5 {
          margin: 0 0 8px 0;
          color: #ff6666;
          font-size: 0.9rem;
        }

        .errors-list {
          margin: 0;
          padding-left: 16px;
          font-size: 0.85rem;
        }

        .errors-list li {
          color: #ff9999;
          margin-bottom: 4px;
        }

        .result-landing-rate {
          margin-top: 16px;
          padding: 12px;
          background: rgba(0, 255, 136, 0.1);
          border-radius: 6px;
        }

        .result-landing-rate h5 {
          margin: 0 0 8px 0;
          color: #00ff88;
          font-size: 0.9rem;
        }

        .landing-rate-stats {
          display: flex;
          align-items: baseline;
          gap: 12px;
        }

        .lr-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: #00ff88;
        }

        .lr-detail {
          color: var(--text-secondary, #888);
          font-size: 0.85rem;
        }
      `}</style>
    </div>
  );
};

export default AgentPanel;
