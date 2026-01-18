/**
 * Modal para visualizar el context completo de un fragmento.
 * 
 * Muestra:
 * - Texto completo del fragmento (sin truncar)
 * - Todos los códigos asignados a este fragmento
 * - Fragmentos adyacentes para contexto
 * - Botones para crear nuevo código o aplicar al formulario
 */

import { useCallback, useEffect, useState } from 'react';
import { apiFetchJson } from '../services/api';
import './FragmentContextModal.css';

interface FragmentData {
    id: string;
    archivo: string;
    fragmento: string;
    par_idx: number;
    area_tematica?: string;
    actor_principal?: string;
    speaker?: string;
    created_at?: string;
}

interface CodeData {
    codigo: string;
    cita: string;
    fuente?: string;
    memo?: string;
    created_at?: string;
}

interface AdjacentFragment {
    id: string;
    par_idx: number;
    fragmento: string;
    speaker?: string;
    position: 'before' | 'after';
}

interface FragmentContextData {
    fragment: FragmentData;
    codes: CodeData[];
    codes_count: number;
    adjacent_fragments: AdjacentFragment[];
}

interface FragmentContextModalProps {
    project: string;
    fragmentId: string;
    currentCode?: string;  // Código actual seleccionado (para destacarlo)
    isOpen: boolean;
    onClose: () => void;
    onApplyToForm?: (fragment: FragmentData, code?: string) => void;
}

export function FragmentContextModal({
    project,
    fragmentId,
    currentCode,
    isOpen,
    onClose,
    onApplyToForm,
}: FragmentContextModalProps) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [data, setData] = useState<FragmentContextData | null>(null);

    const loadContext = useCallback(async () => {
        if (!fragmentId || !project) return;

        setLoading(true);
        setError(null);
        try {
            const response = await apiFetchJson<FragmentContextData & { error?: string }>(
                `/api/coding/fragment-context?project=${encodeURIComponent(project)}&fragment_id=${encodeURIComponent(fragmentId)}`
            );
            if (response.error) {
                throw new Error(response.error);
            }
            setData(response);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error al cargar contexto');
        } finally {
            setLoading(false);
        }
    }, [fragmentId, project]);

    useEffect(() => {
        if (isOpen && fragmentId) {
            void loadContext();
        }
    }, [isOpen, fragmentId, loadContext]);

    // Cerrar con Escape
    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && isOpen) {
                onClose();
            }
        };
        document.addEventListener('keydown', handleEscape);
        return () => document.removeEventListener('keydown', handleEscape);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    return (
        <div className="fragment-modal__overlay" onClick={onClose}>
            <div
                className="fragment-modal__container"
                onClick={(e) => e.stopPropagation()}
            >
                <header className="fragment-modal__header">
                    <h2>📄 Contexto del Fragmento</h2>
                    <button className="fragment-modal__close" onClick={onClose} title="Cerrar (Esc)">
                        ✕
                    </button>
                </header>

                <div className="fragment-modal__body">
                    {loading && (
                        <div className="fragment-modal__loading">
                            <span>Cargando contexto...</span>
                        </div>
                    )}

                    {error && (
                        <div className="fragment-modal__error">
                            <strong>Error:</strong> {error}
                        </div>
                    )}

                    {!loading && !error && data && (
                        <>
                            {/* Metadatos del fragmento */}
                            <section className="fragment-modal__meta">
                                <div className="fragment-modal__meta-grid">
                                    <div>
                                        <label>ID</label>
                                        <span title={data.fragment.id}>{data.fragment.id.slice(0, 20)}...</span>
                                    </div>
                                    <div>
                                        <label>Archivo</label>
                                        <span>{data.fragment.archivo}</span>
                                    </div>
                                    <div>
                                        <label>Párrafo</label>
                                        <span>#{data.fragment.par_idx}</span>
                                    </div>
                                    {data.fragment.actor_principal && (
                                        <div>
                                            <label>Actor</label>
                                            <span>{data.fragment.actor_principal}</span>
                                        </div>
                                    )}
                                    {data.fragment.area_tematica && (
                                        <div>
                                            <label>Área</label>
                                            <span>{data.fragment.area_tematica}</span>
                                        </div>
                                    )}
                                    {data.fragment.speaker && (
                                        <div>
                                            <label>Speaker</label>
                                            <span>{data.fragment.speaker}</span>
                                        </div>
                                    )}
                                </div>
                            </section>

                            {/* Fragmentos adyacentes (contexto anterior) */}
                            {data.adjacent_fragments.filter(f => f.position === 'before').length > 0 && (
                                <section className="fragment-modal__adjacent fragment-modal__adjacent--before">
                                    <h4>📌 Contexto anterior</h4>
                                    {data.adjacent_fragments
                                        .filter(f => f.position === 'before')
                                        .map(adj => (
                                            <div key={adj.id} className="fragment-modal__adjacent-item">
                                                <small>Párrafo #{adj.par_idx}</small>
                                                <p>{adj.fragmento}</p>
                                            </div>
                                        ))
                                    }
                                </section>
                            )}

                            {/* Texto completo del fragmento */}
                            <section className="fragment-modal__content">
                                <h4>📝 Fragmento completo</h4>
                                <blockquote>{data.fragment.fragmento}</blockquote>
                            </section>

                            {/* Fragmentos adyacentes (contexto posterior) */}
                            {data.adjacent_fragments.filter(f => f.position === 'after').length > 0 && (
                                <section className="fragment-modal__adjacent fragment-modal__adjacent--after">
                                    <h4>📌 Contexto posterior</h4>
                                    {data.adjacent_fragments
                                        .filter(f => f.position === 'after')
                                        .map(adj => (
                                            <div key={adj.id} className="fragment-modal__adjacent-item">
                                                <small>Párrafo #{adj.par_idx}</small>
                                                <p>{adj.fragmento}</p>
                                            </div>
                                        ))
                                    }
                                </section>
                            )}

                            {/* Lista de códigos asociados */}
                            <section className="fragment-modal__codes">
                                <h4>🏷️ Códigos asignados ({data.codes_count})</h4>
                                {data.codes.length === 0 ? (
                                    <p className="fragment-modal__no-codes">
                                        Este fragmento no tiene códigos asignados aún.
                                    </p>
                                ) : (
                                    <ul className="fragment-modal__codes-list">
                                        {data.codes.map((code, idx) => (
                                            <li
                                                key={`${code.codigo}-${idx}`}
                                                className={currentCode === code.codigo ? 'is-current' : ''}
                                            >
                                                <div className="fragment-modal__code-header">
                                                    <strong>{code.codigo}</strong>
                                                    {currentCode === code.codigo && (
                                                        <span className="fragment-modal__current-badge">actual</span>
                                                    )}
                                                </div>
                                                <div className="fragment-modal__code-meta">
                                                    {code.fuente && <span>📎 {code.fuente}</span>}
                                                    {code.created_at && (
                                                        <span>📅 {new Date(code.created_at).toLocaleDateString()}</span>
                                                    )}
                                                </div>
                                                {code.cita && (
                                                    <p className="fragment-modal__code-cita">"{code.cita}"</p>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </section>
                        </>
                    )}
                </div>

                <footer className="fragment-modal__footer">
                    {data && onApplyToForm && (
                        <button
                            className="fragment-modal__btn fragment-modal__btn--primary"
                            onClick={() => {
                                onApplyToForm(data.fragment);
                                onClose();
                            }}
                        >
                            📝 Usar en asignación
                        </button>
                    )}
                    <button
                        className="fragment-modal__btn fragment-modal__btn--secondary"
                        onClick={onClose}
                    >
                        Cerrar
                    </button>
                </footer>
            </div>
        </div>
    );
}
