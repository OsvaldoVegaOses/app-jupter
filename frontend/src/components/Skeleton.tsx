/**
 * @fileoverview Componentes skeleton para estados de carga.
 * 
 * Proporciona skeletons animados que reemplazan los simples
 * "Cargando..." por indicadores visuales más sofisticados.
 * 
 * @module components/Skeleton
 */

import React from "react";

interface SkeletonProps {
    /** Ancho del skeleton (px o %) */
    width?: string | number;
    /** Alto del skeleton (px) */
    height?: string | number;
    /** Variante de forma */
    variant?: "text" | "rectangular" | "circular";
    /** Aplicar animación */
    animate?: boolean;
    /** Clases CSS adicionales */
    className?: string;
}

export function Skeleton({
    width = "100%",
    height = 20,
    variant = "text",
    animate = true,
    className = ""
}: SkeletonProps) {
    const style: React.CSSProperties = {
        width: typeof width === "number" ? `${width}px` : width,
        height: typeof height === "number" ? `${height}px` : height,
    };

    return (
        <div
            className={`skeleton skeleton--${variant} ${animate ? "skeleton--animate" : ""} ${className}`}
            style={style}
            aria-hidden="true"
        />
    );
}

interface SkeletonTextProps {
    /** Número de líneas */
    lines?: number;
    /** Ancho de la última línea (%) */
    lastLineWidth?: string;
}

export function SkeletonText({ lines = 3, lastLineWidth = "60%" }: SkeletonTextProps) {
    return (
        <div className="skeleton-text">
            {Array.from({ length: lines }).map((_, index) => (
                <Skeleton
                    key={index}
                    width={index === lines - 1 ? lastLineWidth : "100%"}
                    height={16}
                    variant="text"
                />
            ))}
        </div>
    );
}

export function SkeletonTable({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
    return (
        <div className="skeleton-table">
            {/* Header */}
            <div className="skeleton-table__header">
                {Array.from({ length: columns }).map((_, i) => (
                    <Skeleton key={i} width="80%" height={20} />
                ))}
            </div>
            {/* Rows */}
            {Array.from({ length: rows }).map((_, rowIndex) => (
                <div key={rowIndex} className="skeleton-table__row">
                    {Array.from({ length: columns }).map((_, colIndex) => (
                        <Skeleton
                            key={colIndex}
                            width={colIndex === 0 ? "90%" : "70%"}
                            height={16}
                        />
                    ))}
                </div>
            ))}
        </div>
    );
}

export function SkeletonCard() {
    return (
        <div className="skeleton-card">
            <Skeleton variant="rectangular" height={120} />
            <div className="skeleton-card__content">
                <Skeleton width="80%" height={24} />
                <SkeletonText lines={2} />
            </div>
        </div>
    );
}

export function SkeletonStats({ count = 4 }: { count?: number }) {
    return (
        <div className="skeleton-stats">
            {Array.from({ length: count }).map((_, i) => (
                <div key={i} className="skeleton-stats__item">
                    <Skeleton width={60} height={12} />
                    <Skeleton width={40} height={28} />
                </div>
            ))}
        </div>
    );
}

export default Skeleton;
