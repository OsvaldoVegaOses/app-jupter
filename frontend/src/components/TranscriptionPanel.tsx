/**
 * @fileoverview Panel de transcripción mejorado con funcionalidades avanzadas.
 * 
 * Funcionalidades:
 * - Multi-file upload con cola de procesamiento
 * - Barra de progreso con estado por archivo
 * - División automática de audios largos (vía backend con ffmpeg)
 * - Guardado en carpeta del proyecto
 * - Merge de transcripciones en archivo único
 * - Vista de segmentos por speaker con colores
 * 
 * @module components/TranscriptionPanel
 */

import { useMemo, useState, useRef, useCallback, useEffect } from "react";
import { apiFetchJson } from "../services/api";

interface TranscriptionPanelProps {
    project: string;
    disabled?: boolean;
    onCompleted?: (results: TranscriptionResult[]) => void;
}

interface TranscriptionSegment {
    speaker: string;
    text: string;
    start: number;
    end: number;
}

interface TranscriptionResult {
    text: string;
    segments: TranscriptionSegment[];
    speaker_count: number;
    duration_seconds: number;
    fragments_ingested?: number | null;
    filename?: string;
    saved_path?: string;
}

interface FileQueueItem {
    id: string;
    file: File;
    status: "pending" | "uploading" | "processing" | "completed" | "error";
    progress: number;
    result?: TranscriptionResult;
    error?: string;
    taskId?: string;  // Celery task ID for async polling
}

// Batch API types
interface BatchJob {
    task_id: string;
    filename: string;
}

interface BatchResponse {
    batch_id: string;
    jobs: BatchJob[];
    message: string;
}

interface JobStatusResponse {
    task_id: string;
    status: string;  // PENDING, PROCESSING, SUCCESS, FAILURE
    filename?: string;
    stage?: string;  // transcribing, ingesting
    result?: TranscriptionResult;
    error?: string;
}

interface StreamTranscribeResponse {
    task_id: string;
    filename: string;
    message: string;
}

const SUPPORTED_FORMATS = [
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/webm", "audio/flac", "audio/ogg",
];
const SUPPORTED_EXTENSIONS = [".mp3", ".m4a", ".mp4", ".wav", ".webm", ".flac", ".ogg"];
const MAX_FILE_SIZE_MB = 100; // Aumentado porque ahora soportamos chunking
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

const SPEAKER_COLORS = [
    { bg: "#00d9ff", text: "#000" },
    { bg: "#ff6b9d", text: "#000" },
    { bg: "#4caf50", text: "#fff" },
    { bg: "#ff9800", text: "#000" },
    { bg: "#9c27b0", text: "#fff" },
    { bg: "#00bcd4", text: "#000" },
    { bg: "#e91e63", text: "#fff" },
    { bg: "#8bc34a", text: "#000" },
];

function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const dataUrl = reader.result as string;
            const base64 = dataUrl.split(",")[1];
            resolve(base64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

function formatDuration(seconds: number): string {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hrs > 0) return `${hrs}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function formatTimestamp(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function getSpeakerColor(speaker: string): { bg: string; text: string } {
    const match = speaker.match(/(\d+)/);
    const index = match ? parseInt(match[1], 10) : 0;
    return SPEAKER_COLORS[index % SPEAKER_COLORS.length];
}

function generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function TranscriptionPanel({ project, disabled, onCompleted }: TranscriptionPanelProps) {
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [fileQueue, setFileQueue] = useState<FileQueueItem[]>([]);
    const [diarize, setDiarize] = useState(true);
    const [language, setLanguage] = useState("es");
    const [ingestAfter, setIngestAfter] = useState(true);  // Por defecto: ingestar al pipeline
    const [minChars, setMinChars] = useState(200);
    const [maxChars, setMaxChars] = useState(1200);
    const [isProcessing, setIsProcessing] = useState(false);
    const [currentFileIndex, setCurrentFileIndex] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [showMergedView, setShowMergedView] = useState(false);
    const [expandedFile, setExpandedFile] = useState<string | null>(null);


    const completedResults = useMemo(() =>
        fileQueue.filter(f => f.status === "completed" && f.result).map(f => f.result!),
        [fileQueue]
    );

    const totalProgress = useMemo(() => {
        if (fileQueue.length === 0) return 0;
        const totalProgress = fileQueue.reduce((sum, f) => sum + f.progress, 0);
        return Math.round(totalProgress / fileQueue.length);
    }, [fileQueue]);

    const mergedText = useMemo(() => {
        if (completedResults.length === 0) return "";
        return completedResults.map(r => {
            const header = `\n=== ${r.filename || "Archivo"} ===\n`;
            return header + r.text;
        }).join("\n\n");
    }, [completedResults]);

    const allSegments = useMemo(() => {
        const segments: Array<TranscriptionSegment & { filename: string }> = [];
        completedResults.forEach(r => {
            r.segments.forEach(seg => {
                segments.push({ ...seg, filename: r.filename || "Archivo" });
            });
        });
        return segments;
    }, [completedResults]);

    const handleFilesChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
        const files = event.target.files;
        setError(null);

        if (!files || files.length === 0) return;

        const newItems: FileQueueItem[] = [];
        const errors: string[] = [];

        Array.from(files).forEach(file => {
            // Validar extensión
            const ext = "." + file.name.split(".").pop()?.toLowerCase();
            if (!SUPPORTED_EXTENSIONS.includes(ext)) {
                errors.push(`${file.name}: formato no soportado`);
                return;
            }
            // Validar tamaño (ahora 100MB con chunking)
            if (file.size > MAX_FILE_SIZE_BYTES) {
                errors.push(`${file.name}: excede ${MAX_FILE_SIZE_MB} MB`);
                return;
            }

            newItems.push({
                id: generateId(),
                file,
                status: "pending",
                progress: 0,
            });
        });

        if (errors.length > 0) {
            setError(errors.join("; "));
        }

        setFileQueue(prev => [...prev, ...newItems]);
    }, []);

    const removeFile = useCallback((id: string) => {
        setFileQueue(prev => prev.filter(f => f.id !== id));
    }, []);

    const clearQueue = useCallback(() => {
        setFileQueue([]);
        setError(null);
        setShowMergedView(false);
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
    }, []);

    const processFile = useCallback(async (item: FileQueueItem): Promise<FileQueueItem> => {
        // Update status to uploading
        setFileQueue(prev => prev.map(f =>
            f.id === item.id ? { ...f, status: "uploading", progress: 10 } : f
        ));

        try {
            // Convert to base64
            const audioBase64 = await fileToBase64(item.file);

            setFileQueue(prev => prev.map(f =>
                f.id === item.id ? { ...f, status: "processing", progress: 30 } : f
            ));

            const payload = {
                project,
                audio_base64: audioBase64,
                filename: item.file.name,
                diarize,
                language,
                ingest: ingestAfter,
                min_chars: minChars,
                max_chars: maxChars,
            };

            // Simulate progress updates during API call
            const progressInterval = setInterval(() => {
                setFileQueue(prev => prev.map(f => {
                    if (f.id === item.id && f.progress < 90) {
                        return { ...f, progress: Math.min(f.progress + 5, 90) };
                    }
                    return f;
                }));
            }, 2000);

            const data = await apiFetchJson<TranscriptionResult & { error?: string; detail?: string }>(
                "/api/transcribe",
                {
                    method: "POST",
                    body: JSON.stringify(payload),
                }
            );

            clearInterval(progressInterval);

            if (data.error || data.detail) {
                throw new Error(data.error || data.detail);
            }

            return {
                ...item,
                status: "completed",
                progress: 100,
                result: { ...data, filename: item.file.name },
            };

        } catch (err) {
            return {
                ...item,
                status: "error",
                progress: 0,
                error: err instanceof Error ? err.message : "Error desconocido",
            };
        }
    }, [project, diarize, language, ingestAfter, minChars, maxChars]);

    const startProcessing = useCallback(async () => {
        if (fileQueue.length === 0 || isProcessing) return;

        setIsProcessing(true);
        setCurrentFileIndex(0);
        setError(null);

        try {
            const pendingFiles = fileQueue.filter(f => f.status === "pending");

            for (let i = 0; i < pendingFiles.length; i++) {
                const item = pendingFiles[i];
                setCurrentFileIndex(i);

                // Update to uploading
                setFileQueue(prev => prev.map(f =>
                    f.id === item.id ? { ...f, status: "uploading", progress: 10 } : f
                ));

                try {
                    // Convert to base64
                    const audioBase64 = await fileToBase64(item.file);

                    setFileQueue(prev => prev.map(f =>
                        f.id === item.id ? { ...f, status: "processing", progress: 20 } : f
                    ));

                    const payload = {
                        project,
                        audio_base64: audioBase64,
                        filename: item.file.name,
                        diarize,
                        language,
                        ingest: ingestAfter,
                        min_chars: minChars,
                        max_chars: maxChars,
                    };

                    // Simulate progress updates during API call
                    const progressInterval = setInterval(() => {
                        setFileQueue(prev => prev.map(f => {
                            if (f.id === item.id && f.progress < 90) {
                                return { ...f, progress: Math.min(f.progress + 5, 90) };
                            }
                            return f;
                        }));
                    }, 2000);

                    const data = await apiFetchJson<TranscriptionResult & { error?: string; detail?: string }>(
                        "/api/transcribe",
                        {
                            method: "POST",
                            body: JSON.stringify(payload),
                        }
                    );

                    clearInterval(progressInterval);

                    if (data.error || data.detail) {
                        throw new Error(data.error || data.detail);
                    }

                    setFileQueue(prev => prev.map(f =>
                        f.id === item.id
                            ? { ...f, status: "completed", progress: 100, result: { ...data, filename: item.file.name } }
                            : f
                    ));

                } catch (fileErr) {
                    // Mark this file as errored, continue with others
                    setFileQueue(prev => prev.map(f =>
                        f.id === item.id
                            ? { ...f, status: "error", progress: 0, error: fileErr instanceof Error ? fileErr.message : "Error desconocido" }
                            : f
                    ));
                }
            }

        } catch (err) {
            setError(err instanceof Error ? err.message : "Error en procesamiento");
        } finally {
            setIsProcessing(false);

            // Notify completion
            setFileQueue(prev => {
                const completed = prev.filter(f => f.status === "completed" && f.result);
                if (completed.length > 0 && onCompleted) {
                    onCompleted(completed.map(f => f.result!));
                }
                return prev;
            });
        }
    }, [fileQueue, isProcessing, project, diarize, language, ingestAfter, minChars, maxChars, onCompleted]);


    const downloadMergedDocx = useCallback(async () => {
        if (completedResults.length === 0) return;

        try {
            const response = await apiFetchJson<{ docx_base64: string; filename: string }>(
                "/api/transcribe/merge",
                {
                    method: "POST",
                    body: JSON.stringify({
                        project,
                        transcriptions: completedResults.map(r => ({
                            filename: r.filename,
                            text: r.text,
                            segments: r.segments,
                        })),
                    }),
                }
            );

            // Download base64 as file
            const link = document.createElement("a");
            link.href = `data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,${response.docx_base64}`;
            link.download = response.filename || "transcripciones_merged.docx";
            link.click();
        } catch (err) {
            setError("No se pudo generar el DOCX combinado");
        }
    }, [project, completedResults]);

    // Descargar transcripción individual como DOCX
    const downloadSingleDocx = useCallback(async (result: TranscriptionResult) => {
        try {
            const response = await apiFetchJson<{ docx_base64: string; filename: string }>(
                "/api/transcribe/merge",
                {
                    method: "POST",
                    body: JSON.stringify({
                        project,
                        transcriptions: [{
                            filename: result.filename,
                            text: result.text,
                            segments: result.segments,
                        }],
                    }),
                }
            );

            const link = document.createElement("a");
            link.href = `data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,${response.docx_base64}`;
            // Usar nombre original sin extensión + .docx
            const baseName = result.filename?.replace(/\.[^/.]+$/, "") || "transcripcion";
            link.download = `${baseName}.docx`;
            link.click();
        } catch (err) {
            setError("No se pudo descargar la transcripción");
        }
    }, [project]);

    const canStartProcessing = useMemo(() => {
        return !disabled && !isProcessing && fileQueue.some(f => f.status === "pending");
    }, [disabled, isProcessing, fileQueue]);

    return (
        <section className="transcription">
            <div className="transcription__header">
                <div>
                    <h2>🎙️ Transcripción de Audio</h2>
                    <p>
                        Sube archivos de audio para transcribirlos con diarización automática.
                        Archivos grandes se dividen automáticamente.
                    </p>
                </div>
                {completedResults.length > 0 && (
                    <div className="transcription__header-actions">
                        <button
                            type="button"
                            className="transcription__btn transcription__btn--secondary"
                            onClick={() => setShowMergedView(!showMergedView)}
                        >
                            {showMergedView ? "Ver Individual" : "Ver Combinado"}
                        </button>
                        <button
                            type="button"
                            className="transcription__btn transcription__btn--primary"
                            onClick={downloadMergedDocx}
                            disabled={isProcessing || completedResults.some(r => !r.text || r.text.trim().length === 0)}
                            title={isProcessing ? "Espera a que terminen las transcripciones" : "Descargar documento combinado"}
                        >
                            📥 Descargar DOCX {isProcessing && `(${completedResults.length}/${fileQueue.length})`}
                        </button>
                    </div>
                )}
            </div>

            {/* File Drop Zone */}
            <div className="transcription__dropzone">
                <input
                    ref={fileInputRef}
                    id="transcription-files"
                    type="file"
                    accept={SUPPORTED_EXTENSIONS.join(",")}
                    onChange={handleFilesChange}
                    disabled={isProcessing || disabled}
                    multiple
                    className="transcription__file-input"
                />
                <label htmlFor="transcription-files" className="transcription__dropzone-label">
                    <span className="transcription__dropzone-icon">🎵</span>
                    <span className="transcription__dropzone-text">
                        <strong>Click para seleccionar</strong> o arrastra archivos aquí
                    </span>
                    <span className="transcription__dropzone-hint">
                        MP3, M4A, WAV, FLAC, OGG • Hasta {MAX_FILE_SIZE_MB} MB por archivo
                    </span>
                </label>
            </div>

            {/* File Queue */}
            {fileQueue.length > 0 && (
                <div className="transcription__queue">
                    <div className="transcription__queue-header">
                        <h3>Archivos ({fileQueue.length})</h3>
                        {!isProcessing && (
                            <button type="button" onClick={clearQueue} className="transcription__link">
                                Limpiar todo
                            </button>
                        )}
                    </div>
                    <div className="transcription__queue-list">
                        {fileQueue.map((item, index) => (
                            <div
                                key={item.id}
                                className={`transcription__queue-item transcription__queue-item--${item.status}`}
                            >
                                <div className="transcription__queue-item-info">
                                    <span className="transcription__queue-item-icon">
                                        {item.status === "pending" && "⏳"}
                                        {item.status === "uploading" && "📤"}
                                        {item.status === "processing" && "⚙️"}
                                        {item.status === "completed" && "✅"}
                                        {item.status === "error" && "❌"}
                                    </span>
                                    <span className="transcription__queue-item-name">{item.file.name}</span>
                                    <span className="transcription__queue-item-size">
                                        ({(item.file.size / 1024 / 1024).toFixed(1)} MB)
                                    </span>
                                </div>

                                {(item.status === "uploading" || item.status === "processing") && (
                                    <div className="transcription__progress">
                                        <div
                                            className="transcription__progress-bar"
                                            style={{ width: `${item.progress}%` }}
                                        />
                                        <span className="transcription__progress-text">{item.progress}%</span>
                                    </div>
                                )}

                                {item.status === "completed" && item.result && (
                                    <div className="transcription__queue-item-meta">
                                        <span>👥 {item.result.speaker_count} speakers</span>
                                        <span>⏱️ {formatDuration(item.result.duration_seconds)}</span>
                                        <button
                                            type="button"
                                            className="transcription__link"
                                            onClick={() => setExpandedFile(expandedFile === item.id ? null : item.id)}
                                        >
                                            {expandedFile === item.id ? "Ocultar" : "Ver"}
                                        </button>
                                        <button
                                            type="button"
                                            className="transcription__link transcription__link--download"
                                            onClick={() => downloadSingleDocx(item.result!)}
                                            title="Descargar transcripción individual"
                                        >
                                            📥 DOCX
                                        </button>
                                    </div>
                                )}

                                {item.status === "error" && (
                                    <span className="transcription__queue-item-error">{item.error}</span>
                                )}

                                {item.status === "pending" && !isProcessing && (
                                    <button
                                        type="button"
                                        onClick={() => removeFile(item.id)}
                                        className="transcription__queue-item-remove"
                                    >✕</button>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Global Progress Bar */}
                    {isProcessing && (
                        <div className="transcription__global-progress">
                            <div className="transcription__progress transcription__progress--global">
                                <div
                                    className="transcription__progress-bar"
                                    style={{ width: `${totalProgress}%` }}
                                />
                            </div>
                            <span>Procesando archivo {currentFileIndex + 1} de {fileQueue.length}...</span>
                        </div>
                    )}
                </div>
            )}

            {/* Options */}
            <div className="transcription__options">
                <label className="transcription__checkbox">
                    <input type="checkbox" checked={diarize} onChange={e => setDiarize(e.target.checked)} disabled={isProcessing} />
                    Separar speakers
                </label>
                <label className="transcription__checkbox">
                    <input type="checkbox" checked={ingestAfter} onChange={e => setIngestAfter(e.target.checked)} disabled={isProcessing} />
                    Ingestar al pipeline
                </label>
                <label className="transcription__select-label">
                    Idioma
                    <select value={language} onChange={e => setLanguage(e.target.value)} disabled={isProcessing}>
                        <option value="es">Español</option>
                        <option value="en">English</option>
                        <option value="pt">Português</option>
                    </select>
                </label>
            </div>

            {/* Advanced Options */}
            {ingestAfter && (
                <div className="transcription__advanced">
                    <label>
                        Min caracteres
                        <input type="number" value={minChars} onChange={e => setMinChars(Number(e.target.value))} min={0} disabled={isProcessing} />
                    </label>
                    <label>
                        Max caracteres
                        <input type="number" value={maxChars} onChange={e => setMaxChars(Number(e.target.value))} min={1} disabled={isProcessing} />
                    </label>
                </div>
            )}

            {/* Submit Button */}
            <button
                type="button"
                onClick={startProcessing}
                disabled={!canStartProcessing}
                className="transcription__submit"
            >
                {isProcessing ? "⏳ Procesando..." : "🎤 Transcribir Archivos"}
            </button>

            {/* Error Display */}
            {error && (
                <div className="transcription__error">
                    <strong>⚠️ Error</strong>
                    <span>{error}</span>
                </div>
            )}

            {/* Expanded File View */}
            {expandedFile && fileQueue.find(f => f.id === expandedFile)?.result && (
                <div className="transcription__expanded">
                    <h4>Transcripción: {fileQueue.find(f => f.id === expandedFile)?.file.name}</h4>
                    <div className="transcription__segments">
                        {fileQueue.find(f => f.id === expandedFile)?.result?.segments.slice(0, 10).map((seg, idx) => (
                            <div key={idx} className="transcription__segment">
                                <span
                                    className="transcription__speaker-badge"
                                    style={{
                                        backgroundColor: getSpeakerColor(seg.speaker).bg,
                                        color: getSpeakerColor(seg.speaker).text
                                    }}
                                >
                                    {seg.speaker}
                                </span>
                                <span className="transcription__timestamp">{formatTimestamp(seg.start)}</span>
                                <p>{seg.text}</p>
                            </div>
                        ))}
                        {(fileQueue.find(f => f.id === expandedFile)?.result?.segments.length ?? 0) > 10 && (
                            <p className="transcription__more">
                                ... y {(fileQueue.find(f => f.id === expandedFile)?.result?.segments.length ?? 0) - 10} segmentos más
                            </p>
                        )}
                    </div>
                </div>
            )}

            {/* Merged View */}
            {showMergedView && completedResults.length > 0 && (
                <div className="transcription__merged">
                    <h3>Vista Combinada ({completedResults.length} archivos)</h3>

                    <div className="transcription__merged-stats">
                        <div className="transcription__stat">
                            <strong>Total Duración</strong>
                            <span>{formatDuration(completedResults.reduce((sum, r) => sum + r.duration_seconds, 0))}</span>
                        </div>
                        <div className="transcription__stat">
                            <strong>Total Segmentos</strong>
                            <span>{allSegments.length}</span>
                        </div>
                        <div className="transcription__stat">
                            <strong>Speakers Únicos</strong>
                            <span>{new Set(allSegments.map(s => s.speaker)).size}</span>
                        </div>
                    </div>

                    <details>
                        <summary>Texto Completo</summary>
                        <pre className="transcription__full-text">{mergedText}</pre>
                    </details>
                </div>
            )}

            <style>{`
                .transcription {
                    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
                    border-radius: 12px;
                    padding: 1.5rem;
                    margin-bottom: 1.5rem;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                }
                .transcription__header {
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                    margin-bottom: 1.5rem;
                    flex-wrap: wrap;
                    gap: 1rem;
                }
                .transcription__header h2 {
                    margin: 0;
                    color: #00d9ff;
                    font-size: 1.5rem;
                }
                .transcription__header p {
                    margin: 0.5rem 0 0;
                    color: #b8c5d0;
                    font-size: 0.9rem;
                }
                .transcription__header-actions {
                    display: flex;
                    gap: 0.5rem;
                }
                .transcription__btn {
                    padding: 0.5rem 1rem;
                    border-radius: 6px;
                    border: none;
                    cursor: pointer;
                    font-weight: 500;
                    transition: all 0.2s;
                }
                .transcription__btn--primary {
                    background: linear-gradient(135deg, #00d9ff, #00a8cc);
                    color: #000;
                }
                .transcription__btn--secondary {
                    background: transparent;
                    border: 1px solid #00d9ff;
                    color: #00d9ff;
                }
                .transcription__btn:hover {
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(0,217,255,0.3);
                }
                .transcription__dropzone {
                    border: 2px dashed #444;
                    border-radius: 12px;
                    padding: 2rem;
                    text-align: center;
                    transition: all 0.3s;
                    background: rgba(255,255,255,0.02);
                    margin-bottom: 1rem;
                }
                .transcription__dropzone:hover {
                    border-color: #00d9ff;
                    background: rgba(0,217,255,0.05);
                }
                .transcription__file-input {
                    display: none;
                }
                .transcription__dropzone-label {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 0.5rem;
                    cursor: pointer;
                }
                .transcription__dropzone-icon {
                    font-size: 3rem;
                    animation: pulse 2s infinite;
                }
                @keyframes pulse {
                    0%, 100% { transform: scale(1); }
                    50% { transform: scale(1.1); }
                }
                .transcription__dropzone-text {
                    font-size: 1rem;
                    color: #e0e8f0;
                }
                .transcription__dropzone-hint {
                    font-size: 0.8rem;
                    color: #9aadbf;
                }
                .transcription__queue {
                    background: rgba(0,0,0,0.2);
                    border-radius: 8px;
                    padding: 1rem;
                    margin-bottom: 1rem;
                }
                .transcription__queue-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 0.75rem;
                }
                .transcription__queue-header h3 {
                    margin: 0;
                    font-size: 1rem;
                    color: #00d9ff;
                }
                .transcription__link {
                    background: none;
                    border: none;
                    color: #00d9ff;
                    cursor: pointer;
                    text-decoration: underline;
                    font-size: 0.85rem;
                }
                .transcription__queue-list {
                    display: flex;
                    flex-direction: column;
                    gap: 0.5rem;
                }
                .transcription__queue-item {
                    display: flex;
                    flex-direction: column;
                    gap: 0.5rem;
                    padding: 0.75rem;
                    background: rgba(255,255,255,0.05);
                    border-radius: 6px;
                    border-left: 3px solid #444;
                }
                .transcription__queue-item--completed { border-left-color: #4caf50; }
                .transcription__queue-item--error { border-left-color: #f44336; }
                .transcription__queue-item--processing { border-left-color: #00d9ff; }
                .transcription__queue-item-info {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                }
                .transcription__queue-item-name {
                    font-weight: 500;
                    flex: 1;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    color: #ffffff;
                }
                .transcription__queue-item-size {
                    color: #b8c5d0;
                    font-size: 0.85rem;
                }
                .transcription__queue-item-meta {
                    display: flex;
                    gap: 1rem;
                    font-size: 0.85rem;
                    opacity: 0.8;
                }
                .transcription__queue-item-error {
                    color: #f44336;
                    font-size: 0.85rem;
                }
                .transcription__queue-item-remove {
                    background: none;
                    border: none;
                    color: #f44336;
                    cursor: pointer;
                    padding: 0.25rem;
                    margin-left: auto;
                }
                .transcription__progress {
                    height: 6px;
                    background: rgba(255,255,255,0.1);
                    border-radius: 3px;
                    overflow: hidden;
                    position: relative;
                }
                .transcription__progress--global {
                    height: 8px;
                }
                .transcription__progress-bar {
                    height: 100%;
                    background: linear-gradient(90deg, #00d9ff, #00ffcc);
                    border-radius: 3px;
                    transition: width 0.3s ease;
                }
                .transcription__progress-text {
                    position: absolute;
                    right: 0;
                    top: -18px;
                    font-size: 0.75rem;
                    color: #00d9ff;
                }
                .transcription__global-progress {
                    margin-top: 1rem;
                    text-align: center;
                    font-size: 0.9rem;
                }
                .transcription__chunk-progress {
                    margin-top: 0.75rem;
                    padding: 0.75rem;
                    background: rgba(0, 217, 255, 0.1);
                    border-radius: 8px;
                    border-left: 3px solid #00d9ff;
                }
                .transcription__chunk-badge {
                    display: inline-block;
                    padding: 0.25rem 0.75rem;
                    background: linear-gradient(135deg, #00d9ff33, #00ffcc33);
                    border-radius: 12px;
                    font-size: 0.85rem;
                    font-weight: 500;
                    color: #00d9ff;
                }
                .transcription__chunk-preview {
                    margin: 0.5rem 0 0;
                    font-size: 0.8rem;
                    color: #b8c5d0;
                    font-style: italic;
                    line-height: 1.4;
                    max-height: 60px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                .transcription__options {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 1rem;
                    margin-bottom: 1rem;
                    padding: 1rem;
                    background: rgba(0,0,0,0.2);
                    border-radius: 8px;
                }
                .transcription__checkbox {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    cursor: pointer;
                    color: #ffffff;
                }
                .transcription__checkbox input {
                    accent-color: #00d9ff;
                }
                .transcription__select-label {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    color: #ffffff;
                }
                .transcription__select-label select {
                    padding: 0.25rem 0.5rem;
                    border-radius: 4px;
                    background: #2a2a4e;
                    border: 1px solid #444;
                    color: #fff;
                }
                .transcription__advanced {
                    display: flex;
                    gap: 1rem;
                    padding: 1rem;
                    background: rgba(0,0,0,0.2);
                    border-radius: 8px;
                    margin-bottom: 1rem;
                }
                .transcription__advanced label {
                    display: flex;
                    flex-direction: column;
                    gap: 0.25rem;
                    font-size: 0.85rem;
                    color: #ffffff;
                }
                .transcription__advanced input {
                    padding: 0.5rem;
                    border-radius: 4px;
                    background: #2a2a4e;
                    border: 1px solid #444;
                    color: #fff;
                    width: 100px;
                }
                .transcription__submit {
                    width: 100%;
                    padding: 1rem;
                    font-size: 1.1rem;
                    font-weight: 600;
                    border: none;
                    border-radius: 8px;
                    background: linear-gradient(135deg, #00d9ff, #00a8cc);
                    color: #000;
                    cursor: pointer;
                    transition: all 0.3s;
                }
                .transcription__submit:hover:not(:disabled) {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(0,217,255,0.4);
                }
                .transcription__submit:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                }
                .transcription__error {
                    background: rgba(244,67,54,0.1);
                    border: 1px solid #f44336;
                    border-radius: 8px;
                    padding: 1rem;
                    margin-top: 1rem;
                    display: flex;
                    flex-direction: column;
                    gap: 0.25rem;
                }
                .transcription__error strong {
                    color: #f44336;
                }
                .transcription__expanded, .transcription__merged {
                    margin-top: 1.5rem;
                    padding: 1rem;
                    background: rgba(0,0,0,0.3);
                    border-radius: 8px;
                }
                .transcription__expanded h4, .transcription__merged h3 {
                    margin: 0 0 1rem;
                    color: #00d9ff;
                }
                .transcription__segments {
                    display: flex;
                    flex-direction: column;
                    gap: 0.75rem;
                }
                .transcription__segment {
                    padding: 0.75rem;
                    background: rgba(255,255,255,0.05);
                    border-radius: 6px;
                }
                .transcription__speaker-badge {
                    display: inline-block;
                    padding: 0.125rem 0.5rem;
                    border-radius: 4px;
                    font-size: 0.75rem;
                    font-weight: 600;
                    margin-right: 0.5rem;
                }
                .transcription__timestamp {
                    font-size: 0.8rem;
                    opacity: 0.6;
                }
                .transcription__segment p {
                    margin: 0.5rem 0 0;
                    line-height: 1.5;
                }
                .transcription__more {
                    text-align: center;
                    opacity: 0.6;
                    font-style: italic;
                }
                .transcription__merged-stats {
                    display: flex;
                    gap: 1.5rem;
                    margin-bottom: 1rem;
                    flex-wrap: wrap;
                }
                .transcription__stat {
                    display: flex;
                    flex-direction: column;
                    padding: 0.75rem 1rem;
                    background: rgba(0,217,255,0.1);
                    border-radius: 6px;
                }
                .transcription__stat strong {
                    font-size: 0.75rem;
                    text-transform: uppercase;
                    opacity: 0.7;
                }
                .transcription__stat span {
                    font-size: 1.25rem;
                    font-weight: 600;
                    color: #00d9ff;
                }
                .transcription__full-text {
                    background: #1a1a2e;
                    padding: 1rem;
                    border-radius: 4px;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    max-height: 400px;
                    overflow-y: auto;
                    font-size: 0.85rem;
                    margin-top: 1rem;
                }
            `}</style>
        </section>
    );
}
