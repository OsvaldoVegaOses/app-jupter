/**
 * @fileoverview Componente de ejemplos canónicos de un código.
 * 
 * Muestra citas validadas previas para facilitar la comparación constante
 * durante la validación de nuevos códigos candidatos.
 * 
 * @module components/CanonicalExamples
 */

import React, { useEffect, useState } from "react";
import { getCanonicalExamples, CanonicalExample } from "../services/api";

interface CanonicalExamplesProps {
    candidateId: number;
    project: string;
    /** Número máximo de ejemplos a mostrar */
    limit?: number;
    /** Título del componente */
    title?: string;
}

/**
 * Muestra ejemplos canónicos (citas validadas previas) de un código.
 * 
 * Útil para comparación constante: al validar un nuevo candidato,
 * el investigador puede ver cómo se usó este código anteriormente.
 */
export function CanonicalExamples({
    candidateId,
    project,
    limit = 3,
    title = "Ejemplos previos de este código",
}: CanonicalExamplesProps): React.ReactElement {
    const [examples, setExamples] = useState<CanonicalExample[]>([]);
    const [codigo, setCodigo] = useState<string>("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let mounted = true;

        const fetchExamples = async () => {
            setLoading(true);
            setError(null);

            try {
                const result = await getCanonicalExamples(candidateId, project, limit);
                if (mounted) {
                    setExamples(result.examples);
                    setCodigo(result.codigo);
                }
            } catch (err) {
                if (mounted) {
                    setError(err instanceof Error ? err.message : "Error al cargar ejemplos");
                }
            } finally {
                if (mounted) {
                    setLoading(false);
                }
            }
        };

        fetchExamples();

        return () => {
            mounted = false;
        };
    }, [candidateId, project, limit]);

    const containerStyle: React.CSSProperties = {
        backgroundColor: "#f8fafc",
        borderRadius: "8px",
        padding: "16px",
        marginTop: "16px",
        border: "1px solid #e2e8f0",
    };

    const titleStyle: React.CSSProperties = {
        fontSize: "14px",
        fontWeight: 600,
        color: "#475569",
        marginBottom: "12px",
        display: "flex",
        alignItems: "center",
        gap: "8px",
    };

    const badgeStyle: React.CSSProperties = {
        backgroundColor: "#dbeafe",
        color: "#1e40af",
        padding: "2px 8px",
        borderRadius: "12px",
        fontSize: "12px",
        fontWeight: 500,
    };

    const exampleCardStyle: React.CSSProperties = {
        backgroundColor: "white",
        borderRadius: "6px",
        padding: "12px",
        marginBottom: "8px",
        border: "1px solid #e2e8f0",
        fontSize: "14px",
    };

    const citaStyle: React.CSSProperties = {
        fontStyle: "italic",
        color: "#1e293b",
        marginBottom: "8px",
        lineHeight: 1.5,
    };

    const metaStyle: React.CSSProperties = {
        display: "flex",
        gap: "12px",
        fontSize: "12px",
        color: "#64748b",
    };

    const emptyStyle: React.CSSProperties = {
        textAlign: "center",
        color: "#94a3b8",
        padding: "16px",
        fontSize: "14px",
    };

    const loadingStyle: React.CSSProperties = {
        textAlign: "center",
        padding: "16px",
        color: "#64748b",
    };

    if (loading) {
        return (
            <div style={containerStyle}>
                <div style={loadingStyle}>Cargando ejemplos...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div style={containerStyle}>
                <div style={{ ...emptyStyle, color: "#ef4444" }}>
                    ⚠️ {error}
                </div>
            </div>
        );
    }

    return (
        <div style={containerStyle}>
            <div style={titleStyle}>
                📚 {title}
                {codigo && <span style={badgeStyle}>{codigo}</span>}
            </div>

            {examples.length === 0 ? (
                <div style={emptyStyle}>
                    Este código aún no tiene ejemplos validados.
                    <br />
                    <span style={{ fontSize: "12px" }}>
                        Los ejemplos aparecen después de validar y promover códigos.
                    </span>
                </div>
            ) : (
                examples.map((example, idx) => (
                    <div key={idx} style={exampleCardStyle}>
                        <div style={citaStyle}>
                            "{example.cita}"
                        </div>
                        <div style={metaStyle}>
                            <span>📁 {example.archivo}</span>
                            {example.fragmento_id && (
                                <span>🔗 {example.fragmento_id.slice(0, 8)}...</span>
                            )}
                            {example.created_at && (
                                <span>
                                    📅 {new Date(example.created_at).toLocaleDateString("es-CL")}
                                </span>
                            )}
                        </div>
                        {example.memo && (
                            <div style={{ marginTop: "8px", fontSize: "12px", color: "#64748b" }}>
                                💬 {example.memo}
                            </div>
                        )}
                    </div>
                ))
            )}
        </div>
    );
}

export default CanonicalExamples;
