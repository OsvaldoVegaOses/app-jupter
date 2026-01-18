/**
 * @fileoverview Hook para analytics de UI.
 * 
 * Proporciona tracking de eventos de usuario para análisis de comportamiento.
 * Los eventos se envían al backend de forma asíncrona y no bloquean la UI.
 * 
 * Eventos soportados:
 * - click: Interacción con elementos de UI
 * - navigation: Cambio de vista/panel
 * - action: Acciones de negocio (análisis, ingesta, etc.)
 * 
 * @example
 * const { trackEvent, trackClick, trackNavigation } = useAnalytics();
 * trackClick('analyze_button', { project: 'nubeweb' });
 */

import { useCallback, useRef } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || "";
const API_KEY = import.meta.env.VITE_NEO4J_API_KEY || import.meta.env.VITE_API_KEY;

interface AnalyticsEvent {
    event_type: 'click' | 'navigation' | 'action' | 'error';
    element_id: string;
    timestamp: string;
    metadata?: Record<string, unknown>;
    page?: string;
    session_id?: string;
}

// Generar session_id único por sesión de navegador
const SESSION_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

/**
 * Hook para tracking de analytics en el frontend.
 * 
 * Los eventos se envían de forma asíncrona para no bloquear la UI.
 * En caso de error de red, el evento se descarta silenciosamente.
 */
export function useAnalytics() {
    const pendingRef = useRef<AnalyticsEvent[]>([]);
    const flushTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Flush batch de eventos al backend
    const flush = useCallback(async () => {
        if (pendingRef.current.length === 0) return;

        const events = [...pendingRef.current];
        pendingRef.current = [];

        try {
            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };
            if (API_KEY) {
                headers['X-API-Key'] = API_KEY;
            }

            await fetch(`${API_BASE}/api/analytics/track`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ events }),
            });
        } catch {
            // Silently discard - analytics should never break the app
            console.debug('[analytics] Failed to send events', events.length);
        }
    }, []);

    // Queue event and schedule flush
    const queueEvent = useCallback((event: AnalyticsEvent) => {
        pendingRef.current.push(event);

        // Debounce: flush after 2 seconds of inactivity or when batch reaches 10
        if (pendingRef.current.length >= 10) {
            flush();
        } else {
            if (flushTimeoutRef.current) {
                clearTimeout(flushTimeoutRef.current);
            }
            flushTimeoutRef.current = setTimeout(flush, 2000);
        }
    }, [flush]);

    /**
     * Track a generic event.
     */
    const trackEvent = useCallback((
        eventType: AnalyticsEvent['event_type'],
        elementId: string,
        metadata?: Record<string, unknown>
    ) => {
        queueEvent({
            event_type: eventType,
            element_id: elementId,
            timestamp: new Date().toISOString(),
            metadata,
            page: window.location.pathname,
            session_id: SESSION_ID,
        });
    }, [queueEvent]);

    /**
     * Track a click event.
     */
    const trackClick = useCallback((
        elementId: string,
        metadata?: Record<string, unknown>
    ) => {
        trackEvent('click', elementId, metadata);
    }, [trackEvent]);

    /**
     * Track a navigation event (panel/view change).
     */
    const trackNavigation = useCallback((
        viewName: string,
        metadata?: Record<string, unknown>
    ) => {
        trackEvent('navigation', viewName, metadata);
    }, [trackEvent]);

    /**
     * Track an action (business operation like analyze, ingest).
     */
    const trackAction = useCallback((
        actionName: string,
        metadata?: Record<string, unknown>
    ) => {
        trackEvent('action', actionName, metadata);
    }, [trackEvent]);

    /**
     * Track an error event.
     */
    const trackError = useCallback((
        errorId: string,
        metadata?: Record<string, unknown>
    ) => {
        trackEvent('error', errorId, { ...metadata });
        // Flush immediately for errors
        flush();
    }, [trackEvent, flush]);

    return {
        trackEvent,
        trackClick,
        trackNavigation,
        trackAction,
        trackError,
        flush, // Expose for cleanup on unmount
    };
}

export default useAnalytics;
