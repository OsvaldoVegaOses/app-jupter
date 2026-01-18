/**
 * @fileoverview Panel de códigos similares para sugerir fusiones.
 * 
 * Muestra códigos con nombres similares al seleccionado, ordenados por
 * score de similitud, para ayudar a identificar y fusionar duplicados.
 * 
 * @module components/SimilarCodesPanel
 */

import React, { useEffect, useState } from "react";
import { getSimilarCodes, SimilarCode } from "../services/api";

interface SimilarCodesPanelProps {
    codigo: string;
    project: string;
    /** Número máximo de sugerencias */
    topK?: number;
    /** Callback cuando el usuario selecciona un código para fusionar */
    onSelectForMerge?: (codigo: string) => void;
    /** Título del panel */
    title?: string;
}

/**
 * Panel que muestra códigos semánticamente similares.
 * 
 * Usa distancia de Levenshtein para encontrar códigos con nombres parecidos.
 * Útil para sugerir fusiones durante la validación y evitar duplicados.
 */
export function SimilarCodesPanel({
    codigo,
    project,
    topK = 5,
    onSelectForMerge,
    title = "Códigos similares (posibles duplicados)",
}: SimilarCodesPanelProps): React.ReactElement {
    const [similarCodes, setSimilarCodes] = useState<SimilarCode[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let mounted = true;

        const fetchSimilar = async () => {
            if (!codigo.trim()) {
                setLoading(false);
                return;
            }

            setLoading(true);
            setError(null);

            try {
                const result = await getSimilarCodes(codigo, project, topK);
                if (mounted) {
                    setSimilarCodes(result.similar_codes);
                }
            } catch (err) {
                if (mounted) {
                    setError(err instanceof Error ? err.message : "Error al buscar similares");
                }
            } finally {
                if (mounted) {
                    setLoading(false);
                }
            }
        };

        fetchSimilar();

        return () => {
            mounted = false;
        };
    }, [codigo, project, topK]);

    const containerStyle: React.CSSProperties = {
        backgroundColor: "#fefce8",
        borderRadius: "8px",
        padding: "16px",
        border: "1px solid #fde047",
        marginTop: "16px",
    };

    const titleStyle: React.CSSProperties = {
        fontSize: "14px",
        fontWeight: 600,
        color: "#854d0e",
        marginBottom: "12px",
        display: "flex",
        alignItems: "center",
        gap: "8px",
    };

    const codeCardStyle: React.CSSProperties = {
        backgroundColor: "white",
        borderRadius: "6px",
        padding: "10px 12px",
        marginBottom: "6px",
        border: "1px solid #fde68a",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: "14px",
    };

    const codeNameStyle: React.CSSProperties = {
        fontWeight: 500,
        color: "#1e293b",
    };

    const scoreStyle: React.CSSProperties = {
        display: "flex",
        alignItems: "center",
        gap: "8px",
        fontSize: "13px",
        color: "#64748b",
    };

    const scoreBadgeStyle = (score: number): React.CSSProperties => ({
        backgroundColor: score > 0.8 ? "#fee2e2" : score > 0.6 ? "#fef3c7" : "#dbeafe",
        color: score > 0.8 ? "#b91c1c" : score > 0.6 ? "#b45309" : "#1e40af",
        padding: "2px 8px",
        borderRadius: "12px",
        fontSize: "11px",
        fontWeight: 600,
    });

    const mergeButtonStyle: React.CSSProperties = {
        padding: "4px 10px",
        borderRadius: "4px",
        border: "none",
        cursor: "pointer",
        fontSize: "12px",
        fontWeight: 500,
        backgroundColor: "#f59e0b",
        color: "white",
    };

    const emptyStyle: React.CSSProperties = {
        textAlign: "center",
        color: "#a16207",
        padding: "12px",
        fontSize: "14px",
    };

    const loadingStyle: React.CSSProperties = {
        textAlign: "center",
        padding: "12px",
        color: "#a16207",
    };

    if (!codigo.trim()) {
        return <></>;
    }

    if (loading) {
        return (
            <div style={containerStyle}>
                <div style={loadingStyle}>Buscando códigos similares...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div style={{ ...containerStyle, backgroundColor: "#fef2f2", borderColor: "#fecaca" }}>
                <div style={{ ...emptyStyle, color: "#ef4444" }}>
                    ⚠️ {error}
                </div>
            </div>
        );
    }

    if (similarCodes.length === 0) {
        return (
            <div style={containerStyle}>
                <div style={titleStyle}>
                    🔍 {title}
                </div>
                <div style={emptyStyle}>
                    ✅ No se encontraron códigos similares a "{codigo}"
                    <br />
                    <span style={{ fontSize: "12px" }}>
                        Este código parece ser único en el proyecto.
                    </span>
                </div>
            </div>
        );
    }

    return (
        <div style={containerStyle}>
            <div style={titleStyle}>
                ⚠️ {title}
                <span style={{ fontSize: "12px", fontWeight: 400 }}>
                    ({similarCodes.length} encontrados)
                </span>
            </div>

            {similarCodes.map((similar, idx) => (
                <div key={idx} style={codeCardStyle}>
                    <div style={codeNameStyle}>
                        {similar.codigo}
                    </div>
                    <div style={scoreStyle}>
                        <span>📊 {similar.occurrences} usos</span>
                        <span style={scoreBadgeStyle(similar.score)}>
                            {Math.round(similar.score * 100)}% similar
                        </span>
                        {onSelectForMerge && (
                            <button
                                style={mergeButtonStyle}
                                onClick={() => onSelectForMerge(similar.codigo)}
                                title={`Fusionar "${codigo}" con "${similar.codigo}"`}
                            >
                                🔗 Fusionar
                            </button>
                        )}
                    </div>
                </div>
            ))}

            {similarCodes.some(s => s.score > 0.8) && (
                <div style={{ marginTop: "12px", fontSize: "13px", color: "#b45309", textAlign: "center" }}>
                    💡 <strong>Tip:</strong> Códigos con &gt;80% similitud probablemente son duplicados.
                    Considera fusionarlos para evitar fragmentación.
                </div>
            )}
        </div>
    );
}

export default SimilarCodesPanel;
