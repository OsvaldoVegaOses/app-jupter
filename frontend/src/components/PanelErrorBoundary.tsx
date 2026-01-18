/**
 * @fileoverview Error Boundary para paneles del dashboard.
 * 
 * Captura errores de renderizado en componentes hijos y muestra
 * una UI de fallback en lugar de colapsar toda la aplicación.
 * 
 * @module components/PanelErrorBoundary
 */

import React, { Component, ReactNode } from "react";

interface Props {
    children: ReactNode;
    /** Nombre del panel para mostrar en el error */
    panelName?: string;
    /** Callback cuando ocurre un error */
    onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

interface State {
    hasError: boolean;
    error: Error | null;
    errorInfo: React.ErrorInfo | null;
}

export class PanelErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = {
            hasError: false,
            error: null,
            errorInfo: null
        };
    }

    static getDerivedStateFromError(error: Error): Partial<State> {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
        this.setState({ errorInfo });

        // Log to console for debugging
        console.error(`[PanelErrorBoundary] Error in ${this.props.panelName || "panel"}:`, error);
        console.error("Component stack:", errorInfo.componentStack);

        // Call optional error handler
        this.props.onError?.(error, errorInfo);
    }

    handleRetry = (): void => {
        this.setState({ hasError: false, error: null, errorInfo: null });
    };

    render(): ReactNode {
        if (this.state.hasError) {
            return (
                <div className="panel-error">
                    <div className="panel-error__icon">⚠️</div>
                    <h4 className="panel-error__title">
                        Error en {this.props.panelName || "este panel"}
                    </h4>
                    <p className="panel-error__message">
                        {this.state.error?.message || "Ha ocurrido un error inesperado"}
                    </p>
                    <div className="panel-error__actions">
                        <button
                            onClick={this.handleRetry}
                            className="panel-error__retry-btn"
                        >
                            🔄 Reintentar
                        </button>
                        <button
                            onClick={() => window.location.reload()}
                            className="panel-error__reload-btn"
                        >
                            ↻ Recargar página
                        </button>
                    </div>
                    {process.env.NODE_ENV === "development" && this.state.errorInfo && (
                        <details className="panel-error__details">
                            <summary>Detalles técnicos</summary>
                            <pre>{this.state.error?.stack}</pre>
                            <pre>{this.state.errorInfo.componentStack}</pre>
                        </details>
                    )}
                </div>
            );
        }

        return this.props.children;
    }
}

export default PanelErrorBoundary;
