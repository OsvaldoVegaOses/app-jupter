/**
 * @fileoverview Indicador visual del estado de conexión con el backend.
 * 
 * Este componente muestra en el header del dashboard si el backend está
 * disponible, verificando periódicamente el endpoint /healthz.
 * 
 * Estados:
 * - checking: Verificando conexión (gris)
 * - online: Backend disponible (verde)
 * - offline: Backend no disponible (rojo)
 * 
 * @module components/BackendStatus
 */

import { useState, useEffect, useCallback } from "react";

type ConnectionStatus = "checking" | "online" | "offline";

interface BackendStatusProps {
    /** Intervalo de verificación en ms (default: 30000 = 30s) */
    checkInterval?: number;
    /** Mostrar texto junto al indicador */
    showText?: boolean;
}

export function BackendStatus({
    checkInterval = 30000,
    showText = true
}: BackendStatusProps) {
    const API_BASE = import.meta.env.VITE_API_BASE || "";

    const [status, setStatus] = useState<ConnectionStatus>("checking");
    const [lastCheck, setLastCheck] = useState<Date | null>(null);
    const [latency, setLatency] = useState<number | null>(null);

    const checkBackend = useCallback(async () => {
        const startTime = performance.now();
        try {
            const url = API_BASE ? `${API_BASE}/healthz` : "/healthz";
            const response = await fetch(url, {
                method: "GET",
                cache: "no-store",
                signal: AbortSignal.timeout(5000) // 5s timeout
            });

            if (response.ok) {
                setLatency(Math.round(performance.now() - startTime));
                setStatus("online");
            } else {
                setStatus("offline");
                setLatency(null);
            }
        } catch {
            setStatus("offline");
            setLatency(null);
        }
        setLastCheck(new Date());
    }, [API_BASE]);

    useEffect(() => {
        // Check immediately on mount
        checkBackend();

        // Then check periodically
        const interval = setInterval(checkBackend, checkInterval);

        return () => clearInterval(interval);
    }, [checkBackend, checkInterval]);

    const statusConfig = {
        checking: {
            className: "backend-status--checking",
            text: "Verificando...",
            icon: "⏳"
        },
        online: {
            className: "backend-status--online",
            text: latency ? `Conectado (${latency}ms)` : "Conectado",
            icon: "🟢"
        },
        offline: {
            className: "backend-status--offline",
            text: "Sin conexión al servidor",
            icon: "🔴"
        }
    };

    const config = statusConfig[status];

    return (
        <div
            className={`backend-status ${config.className}`}
            title={lastCheck ? `Última verificación: ${lastCheck.toLocaleTimeString()}` : "Verificando..."}
            onClick={checkBackend}
            role="status"
            aria-live="polite"
        >
            <span className="backend-status__dot">{config.icon}</span>
            {showText && <span className="backend-status__text">{config.text}</span>}
        </div>
    );
}

export default BackendStatus;
