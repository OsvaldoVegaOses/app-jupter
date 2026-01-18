/**
 * @fileoverview Componente de alerta de salud del backlog.
 * 
 * Muestra alertas visuales cuando el backlog de candidatos pendientes
 * excede umbrales saludables (muchos pendientes o muy antiguos).
 * 
 * @module components/BacklogHealthAlert
 */

import React, { useEffect, useState } from "react";
import { getBacklogHealth, BacklogHealth } from "../services/api";

interface BacklogHealthAlertProps {
    project: string;
    /** Callback cuando el usuario hace clic para ver pendientes */
    onViewPending?: () => void;
    /** Intervalo de refresco en ms (default: 60000 = 1 minuto) */
    refreshInterval?: number;
}

/**
 * Muestra un banner de alerta si el backlog no está saludable.
 * 
 * - Banner amarillo: backlog no saludable
 * - Banner rojo: backlog crítico (>100 pendientes o >7 días)
 */
export function BacklogHealthAlert({
    project,
    onViewPending,
    refreshInterval = 60000,
}: BacklogHealthAlertProps): React.ReactElement | null {
    const [health, setHealth] = useState<BacklogHealth | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let mounted = true;
        let timeoutId: ReturnType<typeof setTimeout>;

        const fetchHealth = async () => {
            try {
                const result = await getBacklogHealth(project);
                if (mounted) {
                    setHealth(result);
                    setError(null);
                }
            } catch (err) {
                if (mounted) {
                    setError(err instanceof Error ? err.message : "Error al verificar backlog");
                }
            } finally {
                if (mounted) {
                    setLoading(false);
                    // Programar próximo fetch
                    timeoutId = setTimeout(fetchHealth, refreshInterval);
                }
            }
        };

        fetchHealth();

        return () => {
            mounted = false;
            if (timeoutId) clearTimeout(timeoutId);
        };
    }, [project, refreshInterval]);

    // No mostrar si está cargando o hay error
    if (loading || error || !health) return null;

    // No mostrar si está saludable
    if (health.is_healthy) return null;

    // Determinar severidad
    const isCritical = health.pending_count > 100 || health.oldest_pending_days > 7;

    const containerStyle: React.CSSProperties = {
        padding: "12px 16px",
        borderRadius: "8px",
        marginBottom: "16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "12px",
        backgroundColor: isCritical ? "#fef2f2" : "#fffbeb",
        border: `1px solid ${isCritical ? "#fecaca" : "#fde68a"}`,
        color: isCritical ? "#991b1b" : "#92400e",
    };

    const iconStyle: React.CSSProperties = {
        fontSize: "20px",
        flexShrink: 0,
    };

    const contentStyle: React.CSSProperties = {
        flex: 1,
    };

    const titleStyle: React.CSSProperties = {
        fontWeight: 600,
        marginBottom: "4px",
    };

    const metricsStyle: React.CSSProperties = {
        display: "flex",
        gap: "16px",
        fontSize: "14px",
        opacity: 0.9,
    };

    const buttonStyle: React.CSSProperties = {
        padding: "6px 12px",
        borderRadius: "6px",
        border: "none",
        cursor: "pointer",
        fontWeight: 500,
        fontSize: "14px",
        backgroundColor: isCritical ? "#dc2626" : "#f59e0b",
        color: "white",
    };

    return (
        <div style={containerStyle}>
            <span style={iconStyle}>
                {isCritical ? "🚨" : "⚠️"}
            </span>

            <div style={contentStyle}>
                <div style={titleStyle}>
                    {isCritical ? "Backlog Crítico" : "Backlog Requiere Atención"}
                </div>

                <div style={metricsStyle}>
                    <span>
                        📋 <strong>{health.pending_count}</strong> pendientes
                    </span>
                    <span>
                        ⏰ Más antiguo: <strong>{health.oldest_pending_days}</strong> días
                    </span>
                    {health.avg_resolution_hours && (
                        <span>
                            ⚡ Resolución promedio: <strong>{Math.round(health.avg_resolution_hours)}h</strong>
                        </span>
                    )}
                </div>

                {health.alerts.length > 0 && (
                    <div style={{ marginTop: "4px", fontSize: "13px", opacity: 0.8 }}>
                        {health.alerts.join(" • ")}
                    </div>
                )}
            </div>

            {onViewPending && (
                <button
                    style={buttonStyle}
                    onClick={onViewPending}
                >
                    Ver Pendientes
                </button>
            )}
        </div>
    );
}

export default BacklogHealthAlert;
