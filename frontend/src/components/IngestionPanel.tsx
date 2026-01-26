/**
 * @fileoverview Panel de ingesta de documentos DOCX mejorado.
 * 
 * Este componente permite:
 * - Drag & drop de archivos DOCX
 * - Cola de archivos con progreso visual
 * - Configurar parámetros de fragmentación
 * - Ejecutar el pipeline de ingesta via API
 * 
 * @module components/IngestionPanel
 */

import { useMemo, useState, useRef, useCallback } from "react";
import { IngestResult } from "../types";


interface IngestionPanelProps {
  project: string;
  disabled?: boolean;
  onCompleted?: (result: IngestResult) => void;
}

interface FileQueueItem {
  id: string;
  file: File;
  status: "pending" | "uploading" | "processing" | "completed" | "error";
  progress: number;
  result?: any;
  error?: string;
}

const SUPPORTED_EXTENSIONS = [".docx", ".doc"];
const MAX_FILE_SIZE_MB = 50;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}


export function IngestionPanel({ project, disabled, onCompleted }: IngestionPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileQueue, setFileQueue] = useState<FileQueueItem[]>([]);
  const [batchSize, setBatchSize] = useState(64);
  const [minChars, setMinChars] = useState(200);
  const [maxChars, setMaxChars] = useState(1200);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const completedCount = useMemo(() =>
    fileQueue.filter(f => f.status === "completed").length,
    [fileQueue]
  );

  const totalProgress = useMemo(() => {
    if (fileQueue.length === 0) return 0;
    const total = fileQueue.reduce((sum, f) => sum + f.progress, 0);
    return Math.round(total / fileQueue.length);
  }, [fileQueue]);

  const handleFilesChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    setError(null);

    if (!files || files.length === 0) return;

    const newItems: FileQueueItem[] = [];
    const errors: string[] = [];

    Array.from(files).forEach(file => {
      const ext = "." + file.name.split(".").pop()?.toLowerCase();
      if (!SUPPORTED_EXTENSIONS.includes(ext)) {
        errors.push(`${file.name}: formato no soportado (solo DOCX)`);
        return;
      }
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
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const dt = new DataTransfer();
      Array.from(files).forEach(f => dt.items.add(f));
      if (fileInputRef.current) {
        fileInputRef.current.files = dt.files;
        const event = new Event('change', { bubbles: true });
        fileInputRef.current.dispatchEvent(event);
      }
    }
  }, []);

  const startProcessing = useCallback(async () => {
    if (fileQueue.length === 0 || isProcessing) return;

    setIsProcessing(true);
    setError(null);

    try {
      const pendingFiles = fileQueue.filter(f => f.status === "pending");

      for (let i = 0; i < pendingFiles.length; i++) {
        const item = pendingFiles[i];

        setFileQueue(prev => prev.map(f =>
          f.id === item.id ? { ...f, status: "uploading", progress: 10 } : f
        ));

        try {
          setFileQueue(prev => prev.map(f =>
            f.id === item.id ? { ...f, status: "processing", progress: 30 } : f
          ));

          // Simulate progress
          const progressInterval = setInterval(() => {
            setFileQueue(prev => prev.map(f => {
              if (f.id === item.id && f.progress < 90) {
                return { ...f, progress: Math.min(f.progress + 10, 90) };
              }
              return f;
            }));
          }, 1000);

          // Use FormData for file upload
          const formData = new FormData();
          formData.append("file", item.file);
          formData.append("project", project);
          formData.append("batch_size", batchSize.toString());
          formData.append("min_chars", minChars.toString());
          formData.append("max_chars", maxChars.toString());

          // Get auth token from localStorage
          const authToken = localStorage.getItem("access_token");
          const headers: Record<string, string> = {};
          if (authToken) {
            headers["Authorization"] = `Bearer ${authToken}`;
          }

          // Use fetch directly with FormData (browser auto-sets Content-Type with boundary)
          const response = await fetch("/api/upload-and-ingest", {
            method: "POST",
            body: formData,
            headers,
            credentials: "include",
          });


          clearInterval(progressInterval);

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(errorData.detail || errorData.error || `Error ${response.status}`);
          }

          const data = await response.json();

          if (data.error || data.detail) {
            throw new Error(data.error || data.detail);
          }

          setFileQueue(prev => prev.map(f =>
            f.id === item.id
              ? { ...f, status: "completed", progress: 100, result: data }
              : f
          ));

          if (onCompleted) {
            onCompleted(data);
          }

        } catch (fileErr) {
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
    }
  }, [fileQueue, isProcessing, project, batchSize, minChars, maxChars, onCompleted]);


  const canStartProcessing = useMemo(() => {
    return !disabled && !isProcessing && fileQueue.some(f => f.status === "pending");
  }, [disabled, isProcessing, fileQueue]);

  return (
    <section className="ingestion-modern">
      <div className="ingestion-modern__header">
        <div>
          <h2>📄 Ingesta de Documentos</h2>
          <p>
            Sube archivos DOCX de entrevistas para fragmentarlos e indexarlos.
            Los fragmentos se almacenan en Qdrant para búsqueda semántica.
          </p>
        </div>
        {completedCount > 0 && (
          <div className="ingestion-modern__header-stats">
            <span className="ingestion-modern__stat">
              ✅ {completedCount} ingestados
            </span>
          </div>
        )}
      </div>

      {/* Drop Zone */}
      <div
        className="ingestion-modern__dropzone"
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          id="ingestion-files"
          type="file"
          accept={SUPPORTED_EXTENSIONS.join(",")}
          onChange={handleFilesChange}
          disabled={isProcessing || disabled}
          multiple
          className="ingestion-modern__file-input"
          data-testid="ingestion-file-input"
        />
        <label htmlFor="ingestion-files" className="ingestion-modern__dropzone-label">
          <span className="ingestion-modern__dropzone-icon">📁</span>
          <span className="ingestion-modern__dropzone-text">
            <strong>Click para seleccionar</strong> o arrastra archivos aquí
          </span>
          <span className="ingestion-modern__dropzone-hint">
            DOCX • Hasta {MAX_FILE_SIZE_MB} MB por archivo
          </span>
        </label>
      </div>

      {/* File Queue */}
      {fileQueue.length > 0 && (
        <div className="ingestion-modern__queue">
          <div className="ingestion-modern__queue-header">
            <h3>Archivos ({fileQueue.length})</h3>
            {!isProcessing && (
              <button type="button" onClick={clearQueue} className="ingestion-modern__link">
                Limpiar todo
              </button>
            )}
          </div>
          <div className="ingestion-modern__queue-list">
            {fileQueue.map((item) => (
              <div
                key={item.id}
                className={`ingestion-modern__queue-item ingestion-modern__queue-item--${item.status}`}
              >
                <div className="ingestion-modern__queue-item-info">
                  <span className="ingestion-modern__queue-item-icon">
                    {item.status === "pending" && "⏳"}
                    {item.status === "uploading" && "📤"}
                    {item.status === "processing" && "⚙️"}
                    {item.status === "completed" && "✅"}
                    {item.status === "error" && "❌"}
                  </span>
                  <span className="ingestion-modern__queue-item-name">{item.file.name}</span>
                  <span className="ingestion-modern__queue-item-size">
                    ({(item.file.size / 1024 / 1024).toFixed(1)} MB)
                  </span>
                </div>

                {(item.status === "uploading" || item.status === "processing") && (
                  <div className="ingestion-modern__progress">
                    <div
                      className="ingestion-modern__progress-bar"
                      style={{ width: `${item.progress}%` }}
                    />
                    <span className="ingestion-modern__progress-text">{item.progress}%</span>
                  </div>
                )}

                {item.status === "completed" && item.result && (
                  <div className="ingestion-modern__queue-item-meta">
                    <span>📊 {item.result.fragments || item.result.total_fragments || "?"} fragmentos</span>
                  </div>
                )}

                {item.status === "error" && (
                  <span className="ingestion-modern__queue-item-error">{item.error}</span>
                )}

                {item.status === "pending" && !isProcessing && (
                  <button
                    type="button"
                    onClick={() => removeFile(item.id)}
                    className="ingestion-modern__queue-item-remove"
                  >❌</button>
                )}
              </div>
            ))}
          </div>

          {/* Global Progress */}
          {isProcessing && (
            <div className="ingestion-modern__global-progress">
              <div className="ingestion-modern__progress ingestion-modern__progress--global">
                <div
                  className="ingestion-modern__progress-bar"
                  style={{ width: `${totalProgress}%` }}
                />
              </div>
              <span>Procesando archivos...</span>
            </div>
          )}
        </div>
      )}

      {/* Advanced Options Toggle */}
      <button
        type="button"
        className="ingestion-modern__advanced-toggle"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        ⚙️ Opciones avanzadas {showAdvanced ? "▲" : "▼"}
      </button>

      {/* Advanced Options */}
      {showAdvanced && (
        <div className="ingestion-modern__advanced">
          <label>
            Batch size
            <input
              type="number"
              min={1}
              value={batchSize}
              onChange={(e) => setBatchSize(Number(e.target.value))}
              disabled={isProcessing || disabled}
            />
          </label>
          <label>
            Min caracteres
            <input
              type="number"
              min={0}
              value={minChars}
              onChange={(e) => setMinChars(Number(e.target.value))}
              disabled={isProcessing || disabled}
            />
          </label>
          <label>
            Max caracteres
            <input
              type="number"
              min={1}
              value={maxChars}
              onChange={(e) => setMaxChars(Number(e.target.value))}
              disabled={isProcessing || disabled}
            />
          </label>
        </div>
      )}

      {/* Submit Button */}
      <button
        type="button"
        onClick={startProcessing}
        disabled={!canStartProcessing}
        className="ingestion-modern__submit"
      >
        {isProcessing ? "⏳ Procesando..." : "📥 Ingestar Archivos"}
      </button>

      {/* Error Display */}
      {error && (
        <div className="ingestion-modern__error">
          <strong>⚠️ Error</strong>
          <span>{error}</span>
        </div>
      )}

      <style>{`
        .ingestion-modern {
          background: linear-gradient(180deg, #1a2e1a 0%, #162e16 100%);
          border-radius: 12px;
          padding: 1.5rem;
          margin-bottom: 1.5rem;
          box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        .ingestion-modern__header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 1.5rem;
          flex-wrap: wrap;
          gap: 1rem;
        }
        .ingestion-modern__header h2 {
          margin: 0;
          color: #4caf50;
          font-size: 1.5rem;
        }
        .ingestion-modern__header p {
          margin: 0.5rem 0 0;
          color: #b8d0b8;
          font-size: 0.9rem;
        }
        .ingestion-modern__header-stats {
          display: flex;
          gap: 0.5rem;
        }
        .ingestion-modern__stat {
          background: rgba(76, 175, 80, 0.2);
          padding: 0.3rem 0.6rem;
          border-radius: 4px;
          font-size: 0.85rem;
          color: #4caf50;
        }
        .ingestion-modern__dropzone {
          border: 2px dashed #4a5;
          border-radius: 12px;
          padding: 2rem;
          text-align: center;
          transition: all 0.3s;
          background: rgba(76, 175, 80, 0.02);
          margin-bottom: 1rem;
        }
        .ingestion-modern__dropzone:hover {
          border-color: #4caf50;
          background: rgba(76, 175, 80, 0.08);
        }
        .ingestion-modern__file-input {
          display: none;
        }
        .ingestion-modern__dropzone-label {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.5rem;
          cursor: pointer;
        }
        .ingestion-modern__dropzone-icon {
          font-size: 3rem;
          animation: pulse-green 2s infinite;
        }
        @keyframes pulse-green {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.1); }
        }
        .ingestion-modern__dropzone-text {
          font-size: 1rem;
          color: #e0f0e0;
        }
        .ingestion-modern__dropzone-hint {
          font-size: 0.8rem;
          color: #9abf9a;
        }
        .ingestion-modern__queue {
          background: rgba(0,0,0,0.2);
          border-radius: 8px;
          padding: 1rem;
          margin-bottom: 1rem;
        }
        .ingestion-modern__queue-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.75rem;
        }
        .ingestion-modern__queue-header h3 {
          margin: 0;
          font-size: 1rem;
          color: #4caf50;
        }
        .ingestion-modern__link {
          background: none;
          border: none;
          color: #4caf50;
          cursor: pointer;
          font-size: 0.85rem;
          text-decoration: underline;
        }
        .ingestion-modern__queue-list {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .ingestion-modern__queue-item {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 0.5rem;
          padding: 0.75rem;
          background: rgba(255,255,255,0.03);
          border-radius: 6px;
          border-left: 3px solid transparent;
        }
        .ingestion-modern__queue-item--pending { border-left-color: #888; }
        .ingestion-modern__queue-item--uploading { border-left-color: #ff9800; }
        .ingestion-modern__queue-item--processing { border-left-color: #2196f3; }
        .ingestion-modern__queue-item--completed { border-left-color: #4caf50; }
        .ingestion-modern__queue-item--error { border-left-color: #f44336; }
        .ingestion-modern__queue-item-info {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          flex: 1;
        }
        .ingestion-modern__queue-item-icon {
          font-size: 1.2rem;
        }
        .ingestion-modern__queue-item-name {
          font-weight: 500;
          color: #e8f5e9;
        }
        .ingestion-modern__queue-item-size {
          color: #9e9e9e;
          font-size: 0.85rem;
        }
        .ingestion-modern__queue-item-meta {
          display: flex;
          gap: 0.75rem;
          font-size: 0.85rem;
          color: #a5d6a7;
        }
        .ingestion-modern__queue-item-error {
          color: #ef5350;
          font-size: 0.85rem;
          width: 100%;
          margin-top: 0.25rem;
        }
        .ingestion-modern__queue-item-remove {
          background: none;
          border: none;
          color: #ef5350;
          cursor: pointer;
          font-size: 1rem;
          padding: 0.25rem;
        }
        .ingestion-modern__progress {
          width: 100%;
          height: 6px;
          background: rgba(255,255,255,0.1);
          border-radius: 3px;
          position: relative;
          overflow: hidden;
        }
        .ingestion-modern__progress-bar {
          height: 100%;
          background: linear-gradient(90deg, #4caf50, #81c784);
          border-radius: 3px;
          transition: width 0.3s;
        }
        .ingestion-modern__progress-text {
          position: absolute;
          right: 4px;
          top: -16px;
          font-size: 0.75rem;
          color: #a5d6a7;
        }
        .ingestion-modern__progress--global {
          height: 8px;
          margin-bottom: 0.5rem;
        }
        .ingestion-modern__global-progress {
          margin-top: 1rem;
          text-align: center;
          color: #a5d6a7;
          font-size: 0.9rem;
        }
        .ingestion-modern__advanced-toggle {
          background: transparent;
          border: 1px solid #4a5;
          color: #a5d6a7;
          padding: 0.5rem 1rem;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.9rem;
          margin-bottom: 1rem;
          width: 100%;
          text-align: left;
        }
        .ingestion-modern__advanced-toggle:hover {
          background: rgba(76, 175, 80, 0.1);
        }
        .ingestion-modern__advanced {
          display: flex;
          gap: 1rem;
          flex-wrap: wrap;
          background: rgba(0,0,0,0.2);
          padding: 1rem;
          border-radius: 8px;
          margin-bottom: 1rem;
        }
        .ingestion-modern__advanced label {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
          color: #a5d6a7;
          font-size: 0.85rem;
        }
        .ingestion-modern__advanced input {
          padding: 0.5rem;
          border: 1px solid #4a5;
          border-radius: 4px;
          background: rgba(255,255,255,0.05);
          color: #e8f5e9;
          width: 100px;
        }
        .ingestion-modern__submit {
          width: 100%;
          padding: 1rem;
          background: linear-gradient(135deg, #4caf50, #388e3c);
          border: none;
          border-radius: 8px;
          color: #fff;
          font-size: 1.1rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        .ingestion-modern__submit:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(76, 175, 80, 0.4);
        }
        .ingestion-modern__submit:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        .ingestion-modern__error {
          margin-top: 1rem;
          padding: 1rem;
          background: rgba(244, 67, 54, 0.1);
          border: 1px solid #f44336;
          border-radius: 8px;
          color: #ef5350;
        }
        .ingestion-modern__error strong {
          display: block;
          margin-bottom: 0.25rem;
        }
      `}</style>
    </section>
  );
}
