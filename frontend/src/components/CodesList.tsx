import { useState, useEffect } from "react";
import { apiFetchJson, getCodeHistory, type CodeHistoryEntry } from "../services/api";

import { CodeHistoryModal } from "./CodeHistoryModal";

interface CodeEntry {
  codigo: string;
  citas: number;
  fragmentos: number;
  primera_cita: string | null;
  ultima_cita: string | null;
}

interface CodesListProps {
  project: string;
  refreshKey?: number;
}

export function CodesList({ project, refreshKey }: CodesListProps) {
  const [codes, setCodes] = useState<CodeEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);

  // Code history modal
  const [showHistory, setShowHistory] = useState(false);
  const [historyCodigo, setHistoryCodigo] = useState<string>("");
  const [historyItems, setHistoryItems] = useState<CodeHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const fetchCodes = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetchJson<{ codes: CodeEntry[] }>(
        `/api/coding/codes?project=${encodeURIComponent(project)}&limit=100`
      );
      setCodes(data.codes);
    } catch (err: any) {
      setError(err.message || "Error al cargar códigos");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (visible) {
      fetchCodes();
    }
  }, [visible, project]);

  // Reload data when refreshKey changes (triggered by external events)
  useEffect(() => {
    if (refreshKey !== undefined && refreshKey > 0 && visible) {
      fetchCodes();
    }
  }, [refreshKey, visible]);

  const handleShowHistory = async (codigo: string) => {
    const clean = (codigo || "").trim();
    if (!clean) return;

    setShowHistory(true);
    setHistoryCodigo(clean);
    setHistoryItems([]);
    setHistoryError(null);
    setHistoryLoading(true);
    try {
      const result = await getCodeHistory(project, clean, 50);
      setHistoryItems(result.history || []);
    } catch (err: any) {
      setHistoryError(err?.message || String(err));
    } finally {
      setHistoryLoading(false);
    }
  };

  if (!visible) {
    return (
      <div className="my-4">
        <button
          onClick={() => setVisible(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
        >
          Ver Códigos Validados
        </button>
      </div>
    );
  }

  return (
    <div className="my-4 border rounded p-4 bg-white shadow">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-bold">Códigos Validados</h3>
        <div className="space-x-2">
          <button
            onClick={fetchCodes}
            disabled={loading}
            className="px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 text-sm"
          >
            {loading ? "Cargando..." : "Refrescar"}
          </button>
          <button
            onClick={() => setVisible(false)}
            className="px-3 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200 text-sm"
          >
            Cerrar
          </button>
        </div>
      </div>

      {error && <div className="text-red-600 mb-2">{error}</div>}

      {codes.length === 0 && !loading ? (
        <p className="text-gray-500 italic">No hay códigos registrados.</p>
      ) : (
        <div className="overflow-x-auto max-h-96 overflow-y-auto">
          <table className="min-w-full text-sm text-left">
            <thead className="bg-gray-50 font-medium text-gray-700 sticky top-0">
              <tr>
                <th className="px-4 py-2">Código</th>
                <th className="px-4 py-2">Historial</th>
                <th className="px-4 py-2">Citas</th>
                <th className="px-4 py-2">Fragmentos</th>
                <th className="px-4 py-2">Última Cita</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {codes.map((code) => (
                <tr key={code.codigo} className="hover:bg-gray-50">
                  <td className="px-4 py-2 font-medium">{code.codigo}</td>
                  <td className="px-4 py-2">
                    <button
                      type="button"
                      onClick={() => handleShowHistory(code.codigo)}
                      title="Ver historial del código"
                      className="px-2 py-1 bg-slate-700 text-white rounded hover:bg-slate-800 text-xs"
                    >
                      🕒
                    </button>
                  </td>
                  <td className="px-4 py-2">{code.citas}</td>
                  <td className="px-4 py-2">{code.fragmentos}</td>
                  <td className="px-4 py-2 text-gray-500">
                    {code.ultima_cita ? new Date(code.ultima_cita).toLocaleString() : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CodeHistoryModal
        isOpen={showHistory}
        codigo={historyCodigo}
        loading={historyLoading}
        error={historyError}
        history={historyItems}
        onClose={() => {
          setShowHistory(false);
          setHistoryItems([]);
          setHistoryError(null);
          setHistoryCodigo("");
        }}
      />
    </div>
  );
}
