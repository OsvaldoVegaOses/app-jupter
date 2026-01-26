/**
 * LinkPredictionValidationPanel.tsx
 * 
 * Bandeja para validar/rechazar predicciones de relaciones axiales
 * previamente generadas por algoritmos de Link Prediction.
 * 
 * Diferente de LinkPredictionPanel.tsx que GENERA predicciones,
 * este panel las VALIDA y sincroniza con Neo4j.
 */

import React, { useState, useEffect, useCallback } from "react";
import {
  getLinkPredictions,
  updateLinkPrediction,
  batchUpdateLinkPredictions,
  LinkPrediction,
  LinkPredictionStats,
} from "../services/api";

interface LinkPredictionValidationPanelProps {
  project: string;
  onRelationValidated?: () => void;
}

const RELATION_TYPES = [
  { value: "asociado_con", label: "Asociado con" },
  { value: "causa", label: "Causa" },
  { value: "condicion", label: "Condición" },
  { value: "consecuencia", label: "Consecuencia" },
  { value: "partede", label: "Parte de" },
];

const ALGORITHM_LABELS: Record<string, string> = {
  common_neighbors: "Vecinos Comunes",
  adamic_adar: "Adamic-Adar",
  jaccard: "Jaccard",
  preferential_attachment: "Preferential Attachment",
};

export const LinkPredictionValidationPanel: React.FC<LinkPredictionValidationPanelProps> = ({
  project,
  onRelationValidated,
}) => {
  const [predictions, setPredictions] = useState<LinkPrediction[]>([]);
  const [stats, setStats] = useState<LinkPredictionStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Filtros
  const [estadoFilter, setEstadoFilter] = useState<string>("pendiente");
  const [algorithmFilter, setAlgorithmFilter] = useState<string>("");
  
  // Selección para batch
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  
  // Paginación
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const limit = 50;

  const fetchPredictions = useCallback(async () => {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getLinkPredictions(project, {
        estado: estadoFilter || undefined,
        algorithm: algorithmFilter || undefined,
        limit,
        offset,
      });
      setPredictions(result.items);
      setTotal(result.total);
      setStats(result.stats);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar predicciones");
    } finally {
      setLoading(false);
    }
  }, [project, estadoFilter, algorithmFilter, offset]);

  useEffect(() => {
    fetchPredictions();
  }, [fetchPredictions]);

  const handleUpdateEstado = async (
    id: number,
    estado: "validado" | "rechazado" | "pendiente",
    relationType?: string
  ) => {
    try {
      await updateLinkPrediction(id, estado, {
        relation_type: relationType,
      });
      await fetchPredictions();
      if (estado === "validado" && onRelationValidated) {
        onRelationValidated();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al actualizar");
    }
  };

  const handleBatchUpdate = async (estado: "validado" | "rechazado") => {
    if (selectedIds.size === 0) return;
    try {
      await batchUpdateLinkPredictions(Array.from(selectedIds), estado, project);
      setSelectedIds(new Set());
      await fetchPredictions();
      if (estado === "validado" && onRelationValidated) {
        onRelationValidated();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error en batch update");
    }
  };

  const toggleSelection = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAll = () => {
    if (selectedIds.size === (predictions?.length ?? 0)) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(predictions?.map((p) => p.id) ?? []));
    }
  };

  const formatScore = (score: number) => {
    return score >= 1 ? score.toFixed(0) : score.toFixed(3);
  };

  return (
    <div style={{ padding: "1rem", backgroundColor: "#fff", borderRadius: "8px", marginTop: "1rem" }}>
      <h4 style={{ marginBottom: "1rem", color: "#4a5568", display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <span style={{ fontSize: "1.25rem" }}>📋</span>
        Bandeja de Validación de Predicciones
      </h4>
      
      {/* Estadísticas */}
      {stats && (
        <div style={{ 
          display: "flex", 
          gap: "1rem", 
          marginBottom: "1rem",
          flexWrap: "wrap" 
        }}>
          <div style={{ 
            padding: "0.5rem 1rem", 
            backgroundColor: "#fef3c7", 
            borderRadius: "8px",
            textAlign: "center",
            minWidth: "80px"
          }}>
            <div style={{ fontSize: "1.25rem", fontWeight: "bold" }}>
              {stats.totals.pendiente || 0}
            </div>
            <div style={{ fontSize: "0.7rem", color: "#92400e" }}>Pendientes</div>
          </div>
          <div style={{ 
            padding: "0.5rem 1rem", 
            backgroundColor: "#d1fae5", 
            borderRadius: "8px",
            textAlign: "center",
            minWidth: "80px"
          }}>
            <div style={{ fontSize: "1.25rem", fontWeight: "bold" }}>
              {stats.totals.validado || 0}
            </div>
            <div style={{ fontSize: "0.7rem", color: "#065f46" }}>Validadas → Neo4j</div>
          </div>
          <div style={{ 
            padding: "0.5rem 1rem", 
            backgroundColor: "#fee2e2", 
            borderRadius: "8px",
            textAlign: "center",
            minWidth: "80px"
          }}>
            <div style={{ fontSize: "1.25rem", fontWeight: "bold" }}>
              {stats.totals.rechazado || 0}
            </div>
            <div style={{ fontSize: "0.7rem", color: "#991b1b" }}>Rechazadas</div>
          </div>
        </div>
      )}

      {/* Filtros */}
      <div style={{ 
        display: "flex", 
        gap: "1rem", 
        marginBottom: "1rem",
        alignItems: "center",
        flexWrap: "wrap"
      }}>
        <label style={{ fontSize: "0.875rem" }}>
          Estado:
          <select
            value={estadoFilter}
            onChange={(e) => { setEstadoFilter(e.target.value); setOffset(0); }}
            style={{ marginLeft: "0.5rem", padding: "0.25rem", fontSize: "0.875rem" }}
          >
            <option value="">Todos</option>
            <option value="pendiente">Pendiente</option>
            <option value="validado">Validado</option>
            <option value="rechazado">Rechazado</option>
          </select>
        </label>
        
        <label style={{ fontSize: "0.875rem" }}>
          Algoritmo:
          <select
            value={algorithmFilter}
            onChange={(e) => { setAlgorithmFilter(e.target.value); setOffset(0); }}
            style={{ marginLeft: "0.5rem", padding: "0.25rem", fontSize: "0.875rem" }}
          >
            <option value="">Todos</option>
            {Object.entries(ALGORITHM_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>

        <button
          onClick={fetchPredictions}
          disabled={loading}
          style={{
            padding: "0.25rem 0.5rem",
            backgroundColor: "#f3f4f6",
            border: "1px solid #d1d5db",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "0.875rem"
          }}
        >
          🔄
        </button>
      </div>

      {/* Acciones batch */}
      {selectedIds.size > 0 && (
        <div style={{ 
          display: "flex", 
          gap: "0.5rem", 
          marginBottom: "1rem",
          padding: "0.5rem",
          backgroundColor: "#f0f9ff",
          borderRadius: "4px",
          alignItems: "center"
        }}>
          <span style={{ fontSize: "0.875rem" }}>
            {selectedIds.size} seleccionadas:
          </span>
          <button
            onClick={() => handleBatchUpdate("validado")}
            style={{
              padding: "0.25rem 0.5rem",
              backgroundColor: "#10b981",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "0.75rem"
            }}
          >
            ✓ Validar
          </button>
          <button
            onClick={() => handleBatchUpdate("rechazado")}
            style={{
              padding: "0.25rem 0.5rem",
              backgroundColor: "#ef4444",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "0.75rem"
            }}
          >
            ✗ Rechazar
          </button>
        </div>
      )}

      {error && (
        <div style={{ 
          padding: "0.5rem", 
          backgroundColor: "#fee2e2", 
          color: "#991b1b",
          borderRadius: "4px",
          marginBottom: "1rem",
          fontSize: "0.875rem"
        }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: "center", padding: "1rem", color: "#6b7280" }}>Cargando...</div>
      ) : !predictions || predictions.length === 0 ? (
        <div style={{ 
          textAlign: "center", 
          padding: "1.5rem",
          color: "#6b7280",
          backgroundColor: "#f9fafb",
          borderRadius: "8px",
          fontSize: "0.875rem"
        }}>
          No hay predicciones {estadoFilter ? `con estado "${estadoFilter}"` : ""}.
          <br />
          <small>Usa el panel "Sugerir Relaciones" para generar predicciones.</small>
        </div>
      ) : (
        <>
          {/* Tabla compacta */}
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
            <thead>
              <tr style={{ backgroundColor: "#f9fafb" }}>
                <th style={{ padding: "0.4rem", textAlign: "left", borderBottom: "1px solid #e5e7eb", width: "30px" }}>
                  <input
                    type="checkbox"
                    checked={selectedIds.size === (predictions?.length ?? 0) && (predictions?.length ?? 0) > 0}
                    onChange={selectAll}
                  />
                </th>
                <th style={{ padding: "0.4rem", textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                  Relación Sugerida
                </th>
                <th style={{ padding: "0.4rem", textAlign: "center", borderBottom: "1px solid #e5e7eb", width: "100px" }}>
                  Algoritmo
                </th>
                <th style={{ padding: "0.4rem", textAlign: "center", borderBottom: "1px solid #e5e7eb", width: "60px" }}>
                  Score
                </th>
                <th style={{ padding: "0.4rem", textAlign: "center", borderBottom: "1px solid #e5e7eb", width: "150px" }}>
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody>
              {predictions.map((pred) => (
                <tr 
                  key={pred.id}
                  style={{ 
                    backgroundColor: selectedIds.has(pred.id) ? "#eff6ff" : "transparent",
                  }}
                >
                  <td style={{ padding: "0.4rem", borderBottom: "1px solid #e5e7eb" }}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(pred.id)}
                      onChange={() => toggleSelection(pred.id)}
                    />
                  </td>
                  <td style={{ padding: "0.4rem", borderBottom: "1px solid #e5e7eb" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
                      <code style={{ 
                        padding: "0.1rem 0.3rem", 
                        backgroundColor: "#e0e7ff",
                        borderRadius: "3px",
                        fontSize: "0.8rem"
                      }}>
                        {pred.source_code}
                      </code>
                      <span style={{ color: "#9ca3af", fontSize: "0.75rem" }}>→</span>
                      <code style={{ 
                        padding: "0.1rem 0.3rem", 
                        backgroundColor: "#fef3c7",
                        borderRadius: "3px",
                        fontSize: "0.8rem"
                      }}>
                        {pred.target_code}
                      </code>
                    </div>
                  </td>
                  <td style={{ padding: "0.4rem", borderBottom: "1px solid #e5e7eb", textAlign: "center" }}>
                    <span style={{ 
                      fontSize: "0.7rem",
                      padding: "0.1rem 0.3rem",
                      backgroundColor: "#f3f4f6",
                      borderRadius: "3px"
                    }}>
                      {ALGORITHM_LABELS[pred.algorithm] || pred.algorithm}
                    </span>
                  </td>
                  <td style={{ 
                    padding: "0.4rem", 
                    borderBottom: "1px solid #e5e7eb",
                    textAlign: "center"
                  }}>
                    <span style={{ 
                      fontWeight: "600",
                      fontSize: "0.8rem",
                      color: pred.score > 2 ? "#059669" : pred.score > 1 ? "#d97706" : "#6b7280"
                    }}>
                      {formatScore(pred.score)}
                    </span>
                  </td>
                  <td style={{ 
                    padding: "0.4rem", 
                    borderBottom: "1px solid #e5e7eb",
                    textAlign: "center"
                  }}>
                    {pred.estado === "pendiente" ? (
                      <div style={{ display: "flex", gap: "0.2rem", justifyContent: "center" }}>
                        <select
                          defaultValue=""
                          onChange={(e) => {
                            if (e.target.value) {
                              handleUpdateEstado(pred.id, "validado", e.target.value);
                            }
                          }}
                          style={{ 
                            padding: "0.2rem",
                            fontSize: "0.7rem",
                            backgroundColor: "#10b981",
                            color: "white",
                            border: "none",
                            borderRadius: "3px",
                            cursor: "pointer"
                          }}
                          title="Validar con tipo de relación"
                        >
                          <option value="" disabled>✓ Validar...</option>
                          {RELATION_TYPES.map((rt) => (
                            <option key={rt.value} value={rt.value}>
                              {rt.label}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => handleUpdateEstado(pred.id, "rechazado")}
                          style={{
                            padding: "0.2rem 0.4rem",
                            backgroundColor: "#ef4444",
                            color: "white",
                            border: "none",
                            borderRadius: "3px",
                            cursor: "pointer",
                            fontSize: "0.7rem"
                          }}
                          title="Rechazar"
                        >
                          ✗
                        </button>
                      </div>
                    ) : (
                      <span style={{ 
                        fontSize: "0.7rem",
                        padding: "0.1rem 0.4rem",
                        backgroundColor: pred.estado === "validado" ? "#d1fae5" : "#fee2e2",
                        color: pred.estado === "validado" ? "#065f46" : "#991b1b",
                        borderRadius: "3px"
                      }}>
                        {pred.estado === "validado" ? "✓ Neo4j" : "✗ Rechazado"}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Paginación */}
          {total > limit && (
            <div style={{ 
              display: "flex", 
              justifyContent: "center", 
              gap: "0.5rem", 
              marginTop: "0.75rem",
              fontSize: "0.875rem"
            }}>
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
                style={{
                  padding: "0.2rem 0.5rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "3px",
                  cursor: offset === 0 ? "not-allowed" : "pointer",
                  opacity: offset === 0 ? 0.5 : 1,
                  fontSize: "0.8rem"
                }}
              >
                ←
              </button>
              <span style={{ alignSelf: "center", color: "#6b7280", fontSize: "0.8rem" }}>
                {offset + 1}-{Math.min(offset + limit, total)} / {total}
              </span>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= total}
                style={{
                  padding: "0.2rem 0.5rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "3px",
                  cursor: offset + limit >= total ? "not-allowed" : "pointer",
                  opacity: offset + limit >= total ? 0.5 : 1,
                  fontSize: "0.8rem"
                }}
              >
                →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default LinkPredictionValidationPanel;
