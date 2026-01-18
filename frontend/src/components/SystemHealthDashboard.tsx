/**
 * @fileoverview Dashboard de Salud del Sistema.
 * 
 * Panel administrativo que muestra el estado de todos los servicios:
 * - Backend (FastAPI)
 * - PostgreSQL
 * - Neo4j
 * - Qdrant
 * 
 * Incluye métricas de latencia y uso de recursos.
 * 
 * @module components/SystemHealthDashboard
 */

import { useState, useEffect, useCallback } from "react";

interface ServiceStatus {
    name: string;
    status: "online" | "offline" | "degraded" | "checking";
    latency_ms?: number;
    message?: string;
    details?: Record<string, unknown>;
}

interface HealthData {
    timestamp: string;
    services: ServiceStatus[];
    overall_status: "healthy" | "degraded" | "unhealthy";
    uptime_seconds?: number;
}

interface SystemHealthDashboardProps {
    /** Auto-actualizar cada N segundos (0 = deshabilitado) */
    autoRefreshSeconds?: number;
    /** Mostrar panel colapsado por defecto */
    defaultCollapsed?: boolean;
}

export function SystemHealthDashboard({
    autoRefreshSeconds = 60,
    defaultCollapsed = true,
}: SystemHealthDashboardProps) {
    const [healthData, setHealthData] = useState<HealthData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [collapsed, setCollapsed] = useState(defaultCollapsed);
    const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
    const [cacheCleared, setCacheCleared] = useState(false);

    const fetchHealth = useCallback(async () => {
        setLoading(true);
        setError(null);

        // Get API base URL from environment
        const API_BASE = import.meta.env.VITE_API_BASE || "";

        try {
            const response = await fetch(`${API_BASE}/api/health/full`, {
                headers: {
                    "X-API-Key": import.meta.env.VITE_NEO4J_API_KEY || "",
                },
            });

            if (!response.ok) {
                throw new Error(`Error ${response.status}: ${await response.text()}`);
            }

            const data = await response.json();
            setHealthData(data);
            setLastUpdate(new Date());
        } catch (err) {
            setError(err instanceof Error ? err.message : "Error desconocido");
            // Set degraded state on error
            setHealthData({
                timestamp: new Date().toISOString(),
                services: [
                    { name: "Backend", status: "offline", message: "No se pudo conectar" }
                ],
                overall_status: "unhealthy"
            });
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        // Fetch on mount if not collapsed
        if (!collapsed) {
            fetchHealth();
        }

        // Auto-refresh
        if (autoRefreshSeconds > 0 && !collapsed) {
            const interval = setInterval(fetchHealth, autoRefreshSeconds * 1000);
            return () => clearInterval(interval);
        }
    }, [fetchHealth, autoRefreshSeconds, collapsed]);

    // Fetch when expanded
    const handleToggle = () => {
        const newCollapsed = !collapsed;
        setCollapsed(newCollapsed);
        if (!newCollapsed && !healthData) {
            fetchHealth();
        }
    };

    const getStatusIcon = (status: ServiceStatus["status"]): string => {
        switch (status) {
            case "online": return "🟢";
            case "offline": return "🔴";
            case "degraded": return "🟡";
            case "checking": return "⏳";
            default: return "⚪";
        }
    };

    const getStatusClass = (status: ServiceStatus["status"]): string => {
        return `health-service--${status}`;
    };

    const getOverallIcon = (status: HealthData["overall_status"]): string => {
        switch (status) {
            case "healthy": return "✅";
            case "degraded": return "⚠️";
            case "unhealthy": return "❌";
            default: return "❓";
        }
    };

    const formatUptime = (seconds?: number): string => {
        if (!seconds) return "N/A";
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const mins = Math.floor((seconds % 3600) / 60);

        if (days > 0) return `${days}d ${hours}h`;
        if (hours > 0) return `${hours}h ${mins}m`;
        return `${mins}m`;
    };

    const clearAppCache = () => {
        if (!confirm("¿Limpiar cache de la aplicación? Esto NO cerrará tu sesión.")) {
            return;
        }

        // Keys to preserve (authentication)
        const preserveKeys = [
            "access_token",
            "refresh_token",
            "user",
            "qualy-auth-token",
            "qualy-user-data",
            "qualy-refresh-token",
        ];

        // Get all keys
        const allKeys = Object.keys(localStorage);

        // Remove non-auth keys
        let clearedCount = 0;
        allKeys.forEach(key => {
            if (!preserveKeys.includes(key)) {
                localStorage.removeItem(key);
                clearedCount++;
            }
        });

        console.log(`[Cache] Cleared ${clearedCount} items from localStorage`);
        setCacheCleared(true);

        // Reload after short delay
        setTimeout(() => {
            window.location.reload();
        }, 1000);
    };

    return (
        <div className="health-dashboard">
            <header
                className="health-dashboard__header"
                onClick={handleToggle}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && handleToggle()}
            >
                <div className="health-dashboard__title">
                    <span className="health-dashboard__icon">
                        {healthData ? getOverallIcon(healthData.overall_status) : "🔧"}
                    </span>
                    <h3>Estado del Sistema</h3>
                    {lastUpdate && (
                        <span className="health-dashboard__last-update">
                            Actualizado: {lastUpdate.toLocaleTimeString()}
                        </span>
                    )}
                </div>
                <div className="health-dashboard__controls">
                    {!collapsed && (
                        <button
                            onClick={(e) => { e.stopPropagation(); fetchHealth(); }}
                            disabled={loading}
                            className="health-dashboard__refresh"
                        >
                            {loading ? "⏳" : "🔄"}
                        </button>
                    )}
                    <span className="health-dashboard__toggle">
                        {collapsed ? "▼" : "▲"}
                    </span>
                </div>
            </header>

            {!collapsed && (
                <div className="health-dashboard__content">
                    {error && (
                        <div className="health-dashboard__error">
                            ⚠️ {error}
                        </div>
                    )}

                    {loading && !healthData && (
                        <div className="health-dashboard__loading">
                            Verificando servicios...
                        </div>
                    )}

                    {healthData && (
                        <>
                            {/* Overall Status */}
                            <div className={`health-dashboard__overall health-dashboard__overall--${healthData.overall_status}`}>
                                <span>{getOverallIcon(healthData.overall_status)}</span>
                                <strong>
                                    {healthData.overall_status === "healthy" && "Sistema Operativo"}
                                    {healthData.overall_status === "degraded" && "Funcionamiento Degradado"}
                                    {healthData.overall_status === "unhealthy" && "Sistema No Disponible"}
                                </strong>
                                {healthData.uptime_seconds !== undefined && (
                                    <span className="health-dashboard__uptime">
                                        Uptime: {formatUptime(healthData.uptime_seconds)}
                                    </span>
                                )}
                            </div>

                            {/* Services Grid */}
                            <div className="health-dashboard__services">
                                {healthData.services.map((service) => (
                                    <div
                                        key={service.name}
                                        className={`health-service ${getStatusClass(service.status)}`}
                                    >
                                        <div className="health-service__header">
                                            <span className="health-service__icon">
                                                {getStatusIcon(service.status)}
                                            </span>
                                            <span className="health-service__name">{service.name}</span>
                                        </div>
                                        <div className="health-service__details">
                                            {service.latency_ms !== undefined && (
                                                <span className="health-service__latency">
                                                    {service.latency_ms}ms
                                                </span>
                                            )}
                                            {service.message && (
                                                <span className="health-service__message">
                                                    {service.message}
                                                </span>
                                            )}
                                        </div>
                                        {service.details && Object.keys(service.details).length > 0 && (
                                            <details className="health-service__extra">
                                                <summary>Detalles</summary>
                                                <pre>{JSON.stringify(service.details, null, 2)}</pre>
                                            </details>
                                        )}
                                    </div>
                                ))}
                            </div>

                            {/* Cache Clear Button */}
                            <div className="health-dashboard__cache-section">
                                <button
                                    className="health-dashboard__clear-cache"
                                    onClick={clearAppCache}
                                    disabled={cacheCleared}
                                >
                                    {cacheCleared ? "✅ Cache limpiado" : "🧹 Limpiar Cache"}
                                </button>
                                <span className="health-dashboard__cache-hint">
                                    Limpia datos locales sin cerrar sesión
                                </span>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

export default SystemHealthDashboard;
