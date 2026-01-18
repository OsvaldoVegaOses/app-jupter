/**
 * @fileoverview Toast para errores de API globales.
 * 
 * Escucha eventos 'api-error' despachados por el módulo api.ts
 * y muestra notificaciones visuales al usuario.
 * 
 * @module components/ApiErrorToast
 */

import { useState, useEffect, useCallback, useRef } from "react";
import type { ApiErrorEvent } from "../services/api";

interface ErrorToast {
    id: string;
    status: number;
    message: string;
    path: string;
    timestamp: Date;
}

export function ApiErrorToast() {
    const [toasts, setToasts] = useState<ErrorToast[]>([]);
    const seqRef = useRef(0);

    const makeToastId = (status: number, path: string): string => {
        // Date.now() can collide when multiple errors occur in the same millisecond (common in dev/StrictMode)
        seqRef.current += 1;
        const seq = seqRef.current;
        const uuid =
            typeof crypto !== "undefined" && "randomUUID" in crypto
                ? crypto.randomUUID()
                : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        return `${status}-${path}-${seq}-${uuid}`;
    };

    const addToast = useCallback((event: CustomEvent<ApiErrorEvent>) => {
        const { status, message, path, timestamp } = event.detail;

        // Avoid duplicate toasts for the same error
        const id = makeToastId(status, path);

        setToasts((prev) => {
            // Limit to 3 toasts
            const newToasts = [...prev, { id, status, message, path, timestamp }];
            return newToasts.slice(-3);
        });

        // Auto-dismiss after 8 seconds
        setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 8000);
    }, []);

    useEffect(() => {
        // Listen for API error events
        const handler = (event: Event) => {
            addToast(event as CustomEvent<ApiErrorEvent>);
        };

        window.addEventListener("api-error", handler);
        return () => window.removeEventListener("api-error", handler);
    }, [addToast]);

    const dismissToast = (id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    };

    const getStatusLabel = (status: number): string => {
        if (status === 0) return "Sin conexión";
        if (status === 401) return "No autorizado";
        if (status === 403) return "Prohibido";
        if (status === 404) return "No encontrado";
        if (status >= 500) return "Error del servidor";
        return `Error ${status}`;
    };

    if (toasts.length === 0) {
        return null;
    }

    return (
        <div className="api-error-toast-container">
            {toasts.map((toast) => (
                <div key={toast.id} className="api-error-toast">
                    <span className="api-error-toast__icon">⚠️</span>
                    <div className="api-error-toast__content">
                        <div className="api-error-toast__title">
                            {getStatusLabel(toast.status)}
                        </div>
                        <div className="api-error-toast__message">
                            {toast.message.length > 150
                                ? toast.message.substring(0, 150) + "..."
                                : toast.message}
                        </div>
                    </div>
                    <button
                        className="api-error-toast__close"
                        onClick={() => dismissToast(toast.id)}
                        aria-label="Cerrar"
                    >
                        ×
                    </button>
                </div>
            ))}
            <style>{`
        .api-error-toast-container {
          position: fixed;
          bottom: 1.5rem;
          right: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
          z-index: 9999;
        }
      `}</style>
        </div>
    );
}

export default ApiErrorToast;
