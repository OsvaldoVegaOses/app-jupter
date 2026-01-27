/**
 * @fileoverview Explorador interactivo de Neo4j con visualización de grafos.
 * 
 * Permite ejecutar consultas Cypher y visualizar resultados en tres formatos:
 * - RAW: JSON crudo de la respuesta
 * - TABLE: Vista tabular con columnas y filas
 * - GRAPH: Visualización interactiva con react-force-graph-2d
 * 
 * Características de la visualización de grafo:
 * - Nodos coloreados por community_id
 * - Tamaño de nodos por score_centralidad
 * - Click en nodo Codigo muestra citas relacionadas
 * - Zoom y pan interactivos
 * 
 * API endpoints:
 * - POST /api/neo4j/query → Ejecutar Cypher
 * - POST /api/neo4j/export → Exportar CSV/JSON
 * - GET /api/coding/citations → Citas por código (detalle de nodo)
 * 
 * NOTA: Los controles GDS en UI fueron removidos; la ejecución de GDS ocurre vía API/CLI
 * (p.ej. `POST /api/axial/gds` o `python main.py axial gds ...`).
 * 
 * @module components/Neo4jExplorer
 */

import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import type { Neo4jGraph, Neo4jTable } from "../types";
import type { Neo4jFormat, Neo4jQueryResponse } from "../services/neo4jClient";
import { exportNeo4jQuery, runNeo4jQuery } from "../services/neo4jClient";
import { apiFetch, apiFetchJson } from "../services/api";
import { analyzeNeo4jView, graphragQuery, type EpistemicStatement, type GraphRAGResponse } from "../services/api";
import type { CodingCitation } from "../types";
import { EpistemicMemo } from "./common/Analysis";

const DEFAULT_CYPHER =
  "MATCH (c:Categoria)-[r:REL]->(k:Codigo)\nRETURN c.nombre AS categoria, k.nombre AS codigo, size(r.evidencia) AS evidencia\nORDER BY categoria, codigo\nLIMIT 20";

const FORMATS: Neo4jFormat[] = ["raw", "table", "graph"];

// Quick Query templates for common exploration patterns
interface QuickQuery {
  label: string;
  icon: string;
  cypher: string;
  params?: string;
  description: string;
}

const QUICK_QUERIES: QuickQuery[] = [
  {
    label: "Estructura Axial",
    icon: "🏗️",
    cypher: `MATCH (c:Categoria)-[r:REL]->(k:Codigo)
WHERE c.project_id = $project_id
RETURN c.nombre AS categoria, type(r) AS relacion, k.nombre AS codigo
ORDER BY categoria, codigo
LIMIT 50`,
    params: "project_id=$PROJECT",
    description: "Categorías y sus códigos asociados"
  },
  {
    label: "Top Códigos por Centralidad",
    icon: "📊",
    cypher: `MATCH (k:Codigo)
WHERE k.project_id = $project_id AND k.score_centralidad IS NOT NULL
RETURN k.nombre AS codigo, k.score_centralidad AS centralidad, k.community_id AS comunidad
ORDER BY k.score_centralidad DESC
LIMIT 20`,
    params: "project_id=$PROJECT",
    description: "Códigos más importantes según PageRank"
  },
  {
    label: "Comunidades Louvain",
    icon: "🎨",
    cypher: `MATCH (k:Codigo)
WHERE k.project_id = $project_id AND k.community_id IS NOT NULL
RETURN k.community_id AS comunidad, collect(k.nombre) AS codigos, count(*) AS total
ORDER BY total DESC`,
    params: "project_id=$PROJECT",
    description: "Agrupaciones detectadas por Louvain"
  },
  {
    label: "Códigos sin Categoría",
    icon: "⚠️",
    cypher: `MATCH (k:Codigo)
WHERE k.project_id = $project_id
AND NOT (k)<-[:REL]-(:Categoria)
RETURN k.nombre AS codigo_huerfano
ORDER BY codigo_huerfano`,
    params: "project_id=$PROJECT",
    description: "Códigos que no están asignados a ninguna categoría"
  },
  {
    label: "Fragmentos por Código",
    icon: "📝",
    cypher: `MATCH (f:Fragmento)-[:TIENE_CODIGO]->(k:Codigo)
WHERE k.project_id = $project_id
RETURN k.nombre AS codigo, count(f) AS fragmentos
ORDER BY fragmentos DESC
LIMIT 20`,
    params: "project_id=$PROJECT",
    description: "Cantidad de fragmentos asociados a cada código"
  },
  {
    label: "Grafo Completo (Graph View)",
    icon: "🕸️",
    cypher: `MATCH (n)-[r]->(m)
WHERE n.project_id = $project_id
RETURN n, r, m
LIMIT 100`,
    params: "project_id=$PROJECT",
    description: "Visualización completa del grafo (usar con modo Graph)"
  }
];

function parseParams(input: string): Record<string, unknown> | undefined {
  const trimmed = input.trim();
  if (!trimmed) {
    return undefined;
  }
  const params: Record<string, unknown> = {};
  for (const line of trimmed.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const separator = line.indexOf("=");
    if (separator === -1) {
      throw new Error(`Formato invalido en la linea: "${line}" (usa clave=valor).`);
    }
    const key = line.slice(0, separator).trim();
    let value: string | number | boolean | null = line.slice(separator + 1).trim();
    if (!key) {
      throw new Error("El nombre del parametro no puede estar vacio.");
    }
    if (value === "true" || value === "false") {
      params[key] = value === "true";
    } else if (value === "null") {
      params[key] = null;
    } else if (!Number.isNaN(Number(value))) {
      params[key] = Number(value);
    } else {
      params[key] = value;
    }
  }
  return params;
}

interface ResponseTabsProps {
  response: Neo4jQueryResponse | null;
  active: Neo4jFormat;
  onChange: (value: Neo4jFormat) => void;
  project: string;
}

function ResponseTabs({ response, active, onChange, project }: ResponseTabsProps) {
  const availableTabs = useMemo(() => {
    if (!response) return [];
    return FORMATS.filter((format) => response[format as keyof Neo4jQueryResponse]);
  }, [response]);

  if (!response) {
    return (
      <div className="neo4j-explorer__placeholder">
        Ejecuta una consulta para ver el resultado.
      </div>
    );
  }

  if (!availableTabs.length) {
    return (
      <div className="neo4j-explorer__placeholder">
        La respuesta no contiene los formatos solicitados.
      </div>
    );
  }

  const safeActive = availableTabs.includes(active) ? active : availableTabs[0];
  const current = response[safeActive as keyof Neo4jQueryResponse];

  return (
    <div className="neo4j-explorer__result">
      <div className="neo4j-explorer__tabs">
        {availableTabs.map((format) => (
          <button
            type="button"
            key={format}
            className={`neo4j-explorer__tab ${safeActive === format ? "neo4j-explorer__tab--active" : ""}`}
            onClick={() => onChange(format)}
          >
            {format.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="neo4j-explorer__panel">
        {safeActive === "raw" && (
          <pre className="neo4j-explorer__pre">
            {JSON.stringify(current, null, 2)}
          </pre>
        )}
        {safeActive === "table" && (
          <TableView table={current as Neo4jTable} />
        )}
        {safeActive === "graph" && (
          <GraphView graph={current as Neo4jGraph} project={project} />
        )}
      </div>
    </div>
  );
}

interface TableViewProps {
  table?: Neo4jTable;
}

function TableView({ table }: TableViewProps) {
  if (!table || !table.columns.length) {
    return <p>No hay datos tabulares para mostrar.</p>;
  }
  return (
    <div className="neo4j-explorer__table-wrapper">
      <table className="neo4j-explorer__table">
        <thead>
          <tr>
            {table.columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.length === 0 && (
            <tr>
              <td colSpan={table.columns.length}>Sin filas.</td>
            </tr>
          )}
          {table.rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, columnIndex) => (
                <td key={columnIndex}>
                  {typeof cell === "object" ? JSON.stringify(cell) : String(cell ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface GraphViewProps {
  graph?: Neo4jGraph;
  project: string;
}

interface ForceNode {
  id: string;
  name: string;
  group: string;
  raw: Neo4jGraph["nodes"][number];
}

interface ForceLink {
  id: string;
  source: string;
  target: string;
  name: string;
  raw: Neo4jGraph["relationships"][number];
}

type ForceData = {
  nodes: ForceNode[];
  links: ForceLink[];
};

function GraphView({ graph, project }: GraphViewProps) {
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<ForceGraphMethods<any, any> | undefined>(undefined);
  const [dimensions, setDimensions] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const [selectedNode, setSelectedNode] = useState<ForceNode | null>(null);
  const [citations, setCitations] = useState<CodingCitation[]>([]);
  const [loadingCitations, setLoadingCitations] = useState(false);

  // AI interpret view
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiStatements, setAiStatements] = useState<EpistemicStatement[]>([]);
  const [selectedStatementId, setSelectedStatementId] = useState<string | null>(null);
  const [highlightNodeIds, setHighlightNodeIds] = useState<Set<string>>(new Set());
  const [highlightRelIds, setHighlightRelIds] = useState<Set<string>>(new Set());

  // GraphRAG (Vista Actual)
  const [viewQuery, setViewQuery] = useState("");
  const [viewRagLoading, setViewRagLoading] = useState(false);
  const [viewRagError, setViewRagError] = useState<string | null>(null);
  const [viewRagResponse, setViewRagResponse] = useState<GraphRAGResponse | null>(null);

  const data = useMemo<ForceData>(() => {
    if (!graph) {
      return { nodes: [], links: [] };
    }

    const nodes: ForceNode[] = graph.nodes.map((node, index) => {
      const id = node.id != null ? String(node.id) : `node-${index}`;
      const name = String(
        node.properties?.nombre ?? node.labels?.[0] ?? id
      );
      return {
        id,
        name,
        group: node.labels?.[0] ?? "nodo",
        raw: node,
      };
    });

    const validIds = new Set(nodes.map((node) => node.id));

    const links: ForceLink[] = graph.relationships
      .map((rel, index) => {
        const source = rel.start != null ? String(rel.start) : "";
        const target = rel.end != null ? String(rel.end) : "";
        if (!source || !target || !validIds.has(source) || !validIds.has(target)) {
          return null;
        }
        return {
          id: rel.id != null ? String(rel.id) : `rel-${index}`,
          source,
          target,
          name: rel.type ?? "REL",
          raw: rel,
        };
      })
      .filter(Boolean) as ForceLink[];

    return { nodes, links };
  }, [graph]);

  const handleInterpretView = async () => {
    if (!graph) return;
    setAiLoading(true);
    setAiError(null);
    setAiStatements([]);
    setSelectedStatementId(null);
    setHighlightNodeIds(new Set());
    setHighlightRelIds(new Set());

    try {
      const nodeIds = (graph.nodes || [])
        .map((n) => (n.id != null ? String(n.id) : ""))
        .filter(Boolean);
      const relIds = (graph.relationships || [])
        .map((r) => (r.id != null ? String(r.id) : ""))
        .filter(Boolean);

      const res = await analyzeNeo4jView({
        project,
        node_ids: nodeIds,
        relationship_ids: relIds,
        max_nodes: 300,
        max_relationships: 600,
      });

      setAiStatements(Array.isArray(res.memo_statements) ? res.memo_statements : []);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : String(err));
    } finally {
      setAiLoading(false);
    }
  };

  const visibleCodigoNodeIds = useMemo(() => {
    if (!graph?.nodes) return [] as Array<string | number>;
    return graph.nodes
      .filter((n) => Array.isArray(n.labels) && n.labels.includes("Codigo"))
      .map((n) => (n.id != null ? String(n.id) : ""))
      .filter(Boolean);
  }, [graph]);

  const handleAskViewGraphRag = async () => {
    const q = viewQuery.trim();
    if (!q) return;
    setViewRagLoading(true);
    setViewRagError(null);
    setViewRagResponse(null);
    try {
      const view_nodes = (graph?.nodes || []).map((n) => ({
        id: n.id as string | number,
        label: String(n.properties?.nombre ?? (Array.isArray(n.labels) && n.labels.length > 0 ? n.labels[0] : n.id)),
        community: n.properties?.community_id,
        properties: n.properties || {},
      }));

      const graph_metrics: Record<string, Record<string, number>> = {
        pagerank: {},
        degree: {},
      };
      (graph?.nodes || []).forEach((n) => {
        const nid = n.id != null ? String(n.id) : "";
        graph_metrics.pagerank[nid] = typeof n.properties?.score_centralidad === 'number' ? n.properties.score_centralidad : 0;
        graph_metrics.degree[nid] = typeof n.properties?.degree === 'number' ? n.properties.degree : 0;
      });

      const graph_edges = (graph?.relationships || []).map((r) => ({
        from: r.start as string | number,
        to: r.end as string | number,
        type: r.type || "REL",
      }));

      // Communities detected: group by community_id and pick top nodes by pagerank
      const commMap: Record<string, Array<{ id: string | number; score: number }>> = {};
      (graph?.nodes || []).forEach((n) => {
        const comm = n.properties?.community_id ?? "-";
        const nid = n.id != null ? String(n.id) : String(Math.random());
        const score = typeof n.properties?.score_centralidad === 'number' ? n.properties.score_centralidad : 0;
        if (!commMap[String(comm)]) commMap[String(comm)] = [];
        commMap[String(comm)].push({ id: nid, score });
      });
      const communities_detected = Object.keys(commMap).map((k) => ({
        community_id: k,
        top_nodes: commMap[k].sort((a, b) => b.score - a.score).slice(0, 5).map((x) => x.id),
      }));

      const evidence_candidates: Array<{ fragmento_id: string; archivo?: string; fragmento?: string; score?: number }> = [];

      const res = await graphragQuery({
        query: q,
        project,
        include_fragments: true,
        chain_of_thought: false,
        node_ids: visibleCodigoNodeIds,
        view_nodes,
        graph_metrics,
        graph_edges,
        communities_detected,
        evidence_candidates,
        filters: {},
        max_central: Math.min(10, visibleCodigoNodeIds.length || 10),
      });
      setViewRagResponse(res);
    } catch (err) {
      setViewRagError(err instanceof Error ? err.message : String(err));
    } finally {
      setViewRagLoading(false);
    }
  };

  const handleSelectStatement = (st: EpistemicStatement) => {
    const id = st.id ? String(st.id) : null;
    setSelectedStatementId(id);

    const nodeIds = Array.isArray(st.evidence?.node_ids)
      ? st.evidence!.node_ids.map((v) => String(v))
      : [];
    const relIds = Array.isArray(st.evidence?.relationship_ids)
      ? st.evidence!.relationship_ids.map((v) => String(v))
      : [];

    setHighlightNodeIds(new Set(nodeIds));
    setHighlightRelIds(new Set(relIds));
  };

  useEffect(() => {
    const element = canvasRef.current;
    if (!element) {
      return;
    }

    const computeDimensions = () => {
      const target = canvasRef.current;
      if (!target) {
        return;
      }
      setDimensions({ width: target.clientWidth, height: target.clientHeight });
    };

    computeDimensions();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", computeDimensions);
      return () => window.removeEventListener("resize", computeDimensions);
    }

    const observer = new ResizeObserver(computeDimensions);
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const api = graphRef.current;
    if (!api || !api.zoomToFit || !data.nodes.length) {
      return;
    }
    const timeout = window.setTimeout(() => {
      api.zoomToFit(400, 40);
    }, 120);
    return () => window.clearTimeout(timeout);
  }, [data]);

  const handleNodeClick = async (node: ForceNode) => {
    setSelectedNode(node);
    setCitations([]);

    // Check if it is a Code node (has label 'Codigo') or property 'nombre'
    // To be safe, we check if it has a 'nombre' property which is usually the code name
    const codeName = node.raw.properties?.nombre;
    const isCode = node.group === "Codigo" || (node.raw.labels && node.raw.labels.includes("Codigo"));

    if (isCode && codeName && typeof codeName === 'string') {
      setLoadingCitations(true);
      try {
        const data = await apiFetchJson<{ citations: CodingCitation[] }>(
          `/api/coding/citations?codigo=${encodeURIComponent(codeName)}&project=${project}`
        );
        setCitations(data.citations || []);
      } catch (error) {
        console.error("Failed to fetch citations", error);
      } finally {
        setLoadingCitations(false);
      }
    }
  };

  const handleBackToStats = () => {
    setSelectedNode(null);
    setCitations([]);
  };

  if (!graph || (!graph.nodes.length && !graph.relationships.length)) {
    return <p>No se recibio informacion de grafo.</p>;
  }

  return (
    <div className="neo4j-explorer__graph neo4j-explorer__graph--enhanced">
      <div ref={canvasRef} className="neo4j-explorer__graph-canvas">
        {dimensions.width > 0 && dimensions.height > 0 ? (
          <ForceGraph2D
            ref={graphRef as MutableRefObject<ForceGraphMethods<any, any> | undefined>}
            graphData={data}
            width={dimensions.width}
            height={dimensions.height}
            backgroundColor="#f8fafc"
            // Use Centrality Score for size (default 4 if missing)
            nodeVal={(node: ForceNode) => {
              const score = node.raw.properties?.score_centralidad;
              return typeof score === 'number' ? score * 50 : 2;
            }}
            nodeRelSize={1} // Multiplier for nodeVal
            onNodeClick={handleNodeClick}
            nodeLabel={(node: ForceNode) => {
              const props = node.raw.properties && Object.keys(node.raw.properties).length
                ? `\n${JSON.stringify(node.raw.properties, null, 2)}`
                : "";
              return `${node.name}${props}`;
            }}
            linkLabel={(link: ForceLink) => {
              const props = link.raw.properties && Object.keys(link.raw.properties).length
                ? `\n${JSON.stringify(link.raw.properties, null, 2)}`
                : "";
              return `${link.name}${props}`;
            }}
            // Use Community ID for color group
            nodeAutoColorBy={(node: ForceNode) => {
              const comm = node.raw.properties?.community_id;
              return comm !== undefined ? String(comm) : node.group;
            }}
            linkDirectionalArrowLength={5}
            linkDirectionalArrowRelPos={0.5}
            linkColor={(link: ForceLink) => (highlightRelIds.has(link.id) ? "#ef4444" : "#94a3b8")}
            linkWidth={(link: ForceLink) => (highlightRelIds.has(link.id) ? 2.5 : 1)}
            dagMode={undefined}
            cooldownTicks={120}
            nodeCanvasObject={(node: ForceNode & { x?: number; y?: number }, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const label = node.name;
              const fontSize = Math.max(12 / globalScale, 7);
              ctx.font = `${fontSize}px Sans-Serif`;
              ctx.fillStyle = "#0f172a";
              ctx.fillText(label, (node.x ?? 0) + 8, (node.y ?? 0) + 4);

              // Draw ring if selected
              if (selectedNode && selectedNode.id === node.id) {
                ctx.beginPath();
                ctx.arc(node.x ?? 0, node.y ?? 0, 8, 0, 2 * Math.PI, false);
                ctx.strokeStyle = '#2563eb';
                ctx.lineWidth = 2;
                ctx.stroke();
              }

              // Draw ring if highlighted by AI evidence
              if (highlightNodeIds.has(node.id)) {
                ctx.beginPath();
                ctx.arc(node.x ?? 0, node.y ?? 0, 10, 0, 2 * Math.PI, false);
                ctx.strokeStyle = '#ef4444';
                ctx.lineWidth = 3;
                ctx.stroke();
              }
            }}
          />
        ) : (
          <div className="neo4j-explorer__placeholder">Preparando visualización…</div>
        )}
      </div>

      <div className="neo4j-explorer__graph-details">
        {selectedNode ? (
          <div className="neo4j-explorer__node-detail">
            <button
              onClick={handleBackToStats}
              style={{ marginBottom: '1rem', cursor: 'pointer', background: 'none', border: 'none', color: '#2563eb', textDecoration: 'underline' }}>
              ← Volver al resumen
            </button>
            <h4>{selectedNode.name}</h4>
            <div style={{ marginBottom: '1rem' }}>
              <span className="neo4j-explorer__badge">{selectedNode.group}</span>
              {selectedNode.raw.properties && (
                <pre style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>{JSON.stringify(selectedNode.raw.properties, null, 2)}</pre>
              )}
            </div>

            {(selectedNode.group === "Codigo" || selectedNode.raw.labels?.includes("Codigo")) && (
              <div>
                <h5>Fragmentos Relacionados ({citations.length})</h5>
                {loadingCitations && <p>Cargando citas...</p>}
                {!loadingCitations && citations.length === 0 && <p>No hay citas registradas.</p>}
                <ul style={{ maxHeight: '300px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {citations.map((cite, idx) => (
                    <li key={idx} style={{ backgroundColor: '#fff', padding: '0.5rem', borderRadius: '0.5rem', border: '1px solid #e2e8f0' }}>
                      <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: '0.2rem' }}>
                        {cite.archivo}
                      </div>
                      <div style={{ fontSize: '0.85rem', fontStyle: 'italic' }}>
                        "{cite.cita}"
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <>
            <div style={{ marginBottom: "1rem" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
                <h4 style={{ margin: 0 }}>✨ IA (Vista Actual)</h4>
                <button
                  type="button"
                  onClick={handleInterpretView}
                  disabled={aiLoading}
                  style={{
                    padding: "0.45rem 0.7rem",
                    borderRadius: "0.5rem",
                    border: "1px solid #e2e8f0",
                    background: aiLoading ? "#f1f5f9" : "#ffffff",
                    cursor: aiLoading ? "wait" : "pointer",
                  }}
                  title="Analiza el subgrafo devuelto por la consulta actual y devuelve un memo epistemológico con evidencia (IDs)."
                >
                  {aiLoading ? "Analizando…" : "Interpretar Vista"}
                </button>
              </div>
              {aiError && (
                <div style={{ marginTop: "0.5rem", color: "#b91c1c", fontSize: "0.85rem" }}>
                  {aiError}
                </div>
              )}
              {aiStatements.length > 0 && (
                <div style={{ marginTop: "0.75rem" }}>
                  <EpistemicMemo
                    statements={aiStatements as any}
                    onSelect={handleSelectStatement as any}
                    selectedId={selectedStatementId}
                  />
                  <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "#64748b" }}>
                    Tip: clic en una OBSERVATION para resaltar evidencia.
                  </div>
                </div>
              )}
            </div>

            <div style={{ marginBottom: "1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
                <h4 style={{ margin: 0 }}>🧠 GraphRAG (Vista Actual)</h4>
                <button
                  type="button"
                  onClick={handleAskViewGraphRag}
                  disabled={viewRagLoading || !viewQuery.trim()}
                  style={{
                    padding: "0.45rem 0.7rem",
                    borderRadius: "0.5rem",
                    border: "1px solid #e2e8f0",
                    background: viewRagLoading ? "#f1f5f9" : "#ffffff",
                    cursor: viewRagLoading ? "wait" : "pointer",
                  }}
                  title="Consulta GraphRAG limitada a los nodos Codigo visibles en esta vista."
                >
                  {viewRagLoading ? "Consultando…" : "Preguntar"}
                </button>
              </div>
              <div style={{ marginTop: "0.5rem" }}>
                <textarea
                  value={viewQuery}
                  onChange={(e) => setViewQuery(e.target.value)}
                  placeholder="Pregunta usando SOLO la evidencia de esta vista…"
                  rows={2}
                  disabled={viewRagLoading}
                  style={{
                    width: "100%",
                    padding: "0.6rem",
                    borderRadius: "0.5rem",
                    border: "1px solid #e2e8f0",
                    fontSize: "0.9rem",
                  }}
                />
                <div style={{ marginTop: "0.4rem", fontSize: "0.8rem", color: "#64748b" }}>
                  Scope: {visibleCodigoNodeIds.length} códigos visibles.
                </div>
              </div>
              {viewRagError && (
                <div style={{ marginTop: "0.5rem", color: "#b91c1c", fontSize: "0.85rem" }}>
                  {viewRagError}
                </div>
              )}
              {viewRagResponse && (
                <div style={{ marginTop: "0.75rem", background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "0.75rem", padding: "0.75rem" }}>
                  <div style={{ fontSize: "0.9rem", color: "#0f172a", whiteSpace: "pre-wrap" }}>{viewRagResponse.answer}</div>
                </div>
              )}
            </div>

            <div>
              <h4>Nodos ({graph?.nodes?.length || 0})</h4>
              <ul>
                {(graph?.nodes || []).map((node, index) => (
                  <li key={`${String(node.id)}-${index}`}>
                    <strong>{String(node.id ?? index)}</strong>
                    {node.labels?.length ? (
                      <span className="neo4j-explorer__badge">{node.labels.join(", ")}</span>
                    ) : null}
                    {node.properties && Object.keys(node.properties).length > 0 && (
                      <pre>{JSON.stringify(node.properties, null, 2)}</pre>
                    )}
                  </li>
                ))}
                {!(graph?.nodes?.length) && <li>Sin nodos.</li>}
              </ul>
            </div>
            <div>
              <h4>Relaciones ({graph?.relationships?.length || 0})</h4>
              <ul>
                {(graph?.relationships || []).map((rel, index) => (
                  <li key={`${String(rel.id)}-${index}`}>
                    <strong>{rel.type || "(sin tipo)"}</strong> ({String(rel.start)} → {String(rel.end)})
                    {rel.properties && Object.keys(rel.properties).length > 0 && (
                      <pre>{JSON.stringify(rel.properties, null, 2)}</pre>
                    )}
                  </li>
                ))}
                {!(graph?.relationships?.length) && <li>Sin relaciones.</li>}
              </ul>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

interface Neo4jExplorerProps {
  project: string;
  defaultDatabase?: string;
}

export function Neo4jExplorer({ project, defaultDatabase }: Neo4jExplorerProps) {
  const [cypher, setCypher] = useState(DEFAULT_CYPHER);
  const [params, setParams] = useState("");
  const [formats, setFormats] = useState<Record<Neo4jFormat, boolean>>({
    raw: true,
    table: true,
    graph: false
  });
  const [database, setDatabase] = useState(defaultDatabase || "");
  const [response, setResponse] = useState<Neo4jQueryResponse | null>(null);
  const [activeTab, setActiveTab] = useState<Neo4jFormat>("raw");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const selectedFormats = useMemo(
    () => FORMATS.filter((format) => formats[format]),
    [formats]
  );

  const handleToggleFormat = (format: Neo4jFormat) => {
    setFormats((prev) => ({
      ...prev,
      [format]: !prev[format]
    }));
  };

  const handleQuickQuery = (query: QuickQuery) => {
    setCypher(query.cypher);
    // Replace $PROJECT placeholder with actual project ID
    const paramsWithProject = query.params?.replace("$PROJECT", project) || "";
    setParams(paramsWithProject);
    setError(null);
    setExportMessage(null);
    // If it's the graph query, enable graph format
    if (query.label.includes("Graph")) {
      setFormats(prev => ({ ...prev, graph: true }));
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setExportMessage(null);
    try {
      const parsedParams = parseParams(params);
      setLoading(true);
      const result = await runNeo4jQuery({
        cypher,
        params: parsedParams,
        formats: selectedFormats.length ? selectedFormats : ["raw"],
        database: database.trim() || undefined,
        project
      });
      setResponse(result.data);
      setLatencyMs(result.durationMs ?? null);
      if (result.data.raw) {
        setActiveTab("raw");
      } else if (result.data.table) {
        setActiveTab("table");
      } else if (result.data.graph) {
        setActiveTab("graph");
      }
    } catch (err) {
      setResponse(null);
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("No se pudo ejecutar la consulta.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (format: "csv" | "json") => {
    setError(null);
    setExportMessage(null);
    try {
      const parsedParams = parseParams(params);
      setExporting(true);
      const { blob } = await exportNeo4jQuery(
        {
          cypher,
          params: parsedParams,
          database: database.trim() || undefined,
          project
        },
        format
      );
      const url = URL.createObjectURL(blob);
      const extension = format === "csv" ? "csv" : "json";
      const link = document.createElement("a");
      link.href = url;
      link.download = `neo4j_export.${extension}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setExportMessage(`Exportación ${format.toUpperCase()} generada correctamente.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo exportar la consulta.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="neo4j-explorer">
      <div className="neo4j-explorer__header">
        <div>
          <h2>Explorador Neo4j</h2>
          <p>
            Ejecuta consultas Cypher y visualiza la respuesta en modo <strong>Raw</strong>,{" "}
            <strong>Table</strong> o <strong>Graph</strong>. El endpoint se configura con{" "}
            <code>VITE_NEO4J_API_URL</code> (por defecto, <code>/neo4j/query</code>).
          </p>
        </div>
      </div>

      {/* Quick Query Buttons */}
      <div className="neo4j-explorer__quick-queries">
        <span className="neo4j-explorer__quick-label">⚡ Consultas rápidas:</span>
        <div className="neo4j-explorer__quick-buttons">
          {QUICK_QUERIES.map((query, idx) => (
            <button
              key={idx}
              type="button"
              className="neo4j-explorer__quick-btn"
              onClick={() => handleQuickQuery(query)}
              title={query.description}
            >
              <span>{query.icon}</span>
              <span>{query.label}</span>
            </button>
          ))}
        </div>
      </div>

      <form className="neo4j-explorer__form" onSubmit={handleSubmit}>
        <div className="neo4j-explorer__grid">
          <label className="neo4j-explorer__field">
            <span>Cypher</span>
            <textarea
              value={cypher}
              onChange={(event) => setCypher(event.target.value)}
              rows={6}
            />
          </label>
          <label className="neo4j-explorer__field">
            <span>Parámetros (clave=valor por línea)</span>
            <textarea
              value={params}
              onChange={(event) => setParams(event.target.value)}
              rows={6}
              placeholder={"limit=10\nactivo=true"}
            />
          </label>
        </div>
        <div className="neo4j-explorer__options">
          <fieldset>
            <legend>Formatos</legend>
            <div className="neo4j-explorer__checkboxes">
              {FORMATS.map((format) => (
                <label key={format}>
                  <input
                    type="checkbox"
                    checked={formats[format]}
                    onChange={() => handleToggleFormat(format)}
                  />
                  <span>{format.toUpperCase()}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <label className="neo4j-explorer__field neo4j-explorer__field--database">
            <span>Base de datos (opcional)</span>
            <input
              type="text"
              value={database}
              onChange={(event) => setDatabase(event.target.value)}
              placeholder="neo4j"
            />
          </label>
        </div>
        {error && <p className="neo4j-explorer__error">{error}</p>}
        {exportMessage && <p className="neo4j-explorer__success">{exportMessage}</p>}
        <button type="submit" disabled={loading} className="neo4j-explorer__submit">
          {loading ? "Ejecutando..." : "Ejecutar consulta"}
        </button>
        <div className="neo4j-explorer__actions">
          <button
            type="button"
            className="neo4j-explorer__secondary"
            onClick={() => handleExport("csv")}
            disabled={exporting || loading}
          >
            Exportar CSV
          </button>
          <div className="neo4j-explorer__metrics">
            <span>Última consulta:</span>
            <strong>{latencyMs != null ? `${latencyMs.toFixed(2)} ms` : "-"}</strong>
          </div>
        </div>
      </form>

      <ResponseTabs response={response} active={activeTab} onChange={setActiveTab} project={project} />
    </section>
  );
}

// NOTA: GDSControls fue eliminado. La funcionalidad de Louvain/PageRank
// ahora está disponible en LinkPredictionPanel con mejor integración.
