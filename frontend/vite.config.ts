import react from "@vitejs/plugin-react";
import { spawn } from "child_process";
import fs from "fs";
import path from "path";
import { loadEnv } from "vite";
import { visualizer } from "rollup-plugin-visualizer";
import type { PluginOption, ViteDevServer } from "vite";
import { configDefaults, defineConfig } from "vitest/config";

const repoRoot = path.resolve(__dirname, "..");
const logsDir = path.join(repoRoot, "logs");
const projectsDir = path.join(repoRoot, "metadata", "projects");
const registryPath = path.join(repoRoot, "metadata", "projects_registry.json");
const manifestPath = path.join(repoRoot, "informes", "report_manifest.json");
const DEFAULT_PROJECT = "default";

ensureDir(projectsDir);

const stageOrder = [
  "preparacion",
  "ingesta",
  "codificacion",
  "axial",
  "nucleo",
  "transversal",
  "validacion",
  "informe",
  "analisis"
] as const;

const stageDefinitions: Record<
  (typeof stageOrder)[number],
  { label: string; log_glob: string; verify: string }
> = {
  preparacion: {
    label: "Etapa 0 - Preparacion y Reflexividad",
    log_glob: "etapa0_*.log",
    verify: "python scripts/healthcheck.py"
  },
  ingesta: {
    label: "Etapa 1 - Ingesta y normalizacion",
    log_glob: "ingest*.log",
    verify: "python main.py ingest ..."
  },
  codificacion: {
    label: "Etapa 3 - Codificacion abierta",
    log_glob: "etapa3_*.log",
    verify: "python main.py coding stats"
  },
  axial: {
    label: "Etapa 4 - Codificacion axial",
    log_glob: "etapa4_*.log",
    verify: "python main.py axial gds --algorithm pagerank"
  },
  nucleo: {
    label: "Etapa 5 - Seleccion del nucleo",
    log_glob: "etapa5_*.log",
    verify: "python main.py nucleus report ..."
  },
  transversal: {
    label: "Etapa 6 - Analisis transversal",
    log_glob: "etapa6_*.log",
    verify: "python main.py transversal dashboard ..."
  },
  validacion: {
    label: "Etapa 8 - Validacion y saturacion",
    log_glob: "etapa8_*.log",
    verify: "python main.py validation curve"
  },
  informe: {
    label: "Etapa 9 - Informe integrado",
    log_glob: "etapa9_*.log",
    verify: "python main.py report build"
  },
  analisis: {
    label: "Etapa LLM - Analisis asistido",
    log_glob: "analysis_*.log",
    verify: "python main.py analyze ..."
  }
};

const pythonBinary =
  process.env.PROJECT_PYTHON ||
  process.env.PYTHON ||
  (process.platform === "win32" ? "python" : "python3");

function ensureDir(target: string) {
  if (!fs.existsSync(target)) {
    fs.mkdirSync(target, { recursive: true });
  }
}

function readJsonFile(target: string): any | null {
  try {
    if (!fs.existsSync(target)) {
      return null;
    }
    const raw = fs.readFileSync(target, "utf-8");
    if (!raw.trim()) {
      return null;
    }
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function runPythonJSON(args: string[]): Promise<any> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBinary, args, { cwd: repoRoot });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("close", (code) => {
      if (code === 0) {
        try {
          resolve(stdout ? JSON.parse(stdout) : {});
        } catch (error) {
          reject(
            new Error(
              `No se pudo parsear la salida JSON (${(error as Error).message}). stdout=${stdout}`
            )
          );
        }
      } else {
        if (stdout.trim()) {
          try {
            const parsed = JSON.parse(stdout);
            if (parsed && typeof parsed.error === "string") {
              reject(new Error(parsed.error));
              return;
            }
            reject(new Error(stdout.trim()));
            return;
          } catch {
            reject(new Error(stdout.trim()));
            return;
          }
        }
        reject(new Error(stderr || `Comando Python termino con codigo ${code}`));
      }
    });
    child.on("error", (error) => reject(error));
  });
}

interface CommandResult {
  stdout: string;
  stderr: string;
  code: number;
  runId?: string | null;
}

async function runCommand(args: string[]): Promise<CommandResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBinary, args, { cwd: repoRoot });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("close", (code) => {
      resolve({
        stdout,
        stderr,
        code: code ?? -1
      });
    });
    child.on("error", (error) => reject(error));
  });
}

function latestLog(pattern: string | undefined) {
  if (!pattern || !fs.existsSync(logsDir)) {
    return null;
  }
  const matcher = new RegExp("^" + pattern.replace(/\./g, "\\.").replace(/\*/g, ".*") + "$");
  const files = fs
    .readdirSync(logsDir)
    .filter((name) => matcher.test(name))
    .map((name) => path.join(logsDir, name));
  if (!files.length) {
    return null;
  }
  const ordered = files
    .map((file) => ({ file, stat: fs.statSync(file) }))
    .sort((a, b) => b.stat.mtimeMs - a.stat.mtimeMs);
  const selected = ordered[0];
  return {
    path: selected.file,
    modified_at: new Date(selected.stat.mtime).toISOString(),
    size: selected.stat.size
  };
}

function collectArtifacts(stageKey: string, manifest: any): Array<Record<string, any>> {
  const artifacts: Array<Record<string, any>> = [];
  if (!manifest) {
    return artifacts;
  }
  if (stageKey === "informe") {
    const report = manifest.report || {};
    if (report && (report.path || report.hash)) {
      artifacts.push({
        label: "report",
        path: report.path,
        hash: report.hash
      });
    }
    const annexes = Array.isArray(manifest.annexes) ? manifest.annexes : [];
    annexes.forEach((annex: any) => {
      artifacts.push({
        label: `annex:${annex?.dimension ?? "-"}`,
        path: annex?.file,
        hash: annex?.hash,
        rows: annex?.rows
      });
    });
  }
  if (stageKey === "nucleo" && manifest.nucleus) {
    artifacts.push({ label: "nucleus", details: manifest.nucleus });
  }
  if (stageKey === "validacion" && manifest.saturation) {
    const plateau = manifest.saturation.plateau || {};
    artifacts.push({
      label: "saturation",
      total_codigos: manifest.saturation.total_codigos,
      plateau: plateau.plateau,
      window: plateau.window
    });
  }
  if (["codificacion", "axial", "nucleo", "validacion", "informe"].includes(stageKey)) {
    const snapshot = manifest.snapshot;
    if (snapshot) {
      artifacts.push({
        label: "snapshot",
        fragmentos: snapshot.fragmentos,
        codigos: snapshot.codigos,
        categorias: snapshot.categorias
      });
    }
  }
  return artifacts.filter((item) =>
    Object.values(item).some((value) => value !== undefined && value !== null && value !== "")
  );
}

function fallbackProjects(): { projects: Array<Record<string, any>> } {
  const registry = readJsonFile(registryPath) || {};
  const projects = Array.isArray(registry.projects) ? registry.projects : [];
  return { projects };
}

function getProjectStatePath(project: string): string {
  ensureDir(projectsDir);
  return path.join(projectsDir, `${project}.json`);
}

function buildFallbackSnapshot(project: string) {
  const statePath = getProjectStatePath(project);
  const state = readJsonFile(statePath) || {};
  const manifest = readJsonFile(manifestPath);
  const stages: Record<string, any> = {};
  stageOrder.forEach((key) => {
    const definition = stageDefinitions[key];
    const stored = state[key] || {};
    const entry = {
      ...definition,
      ...stored,
      label: stored.label || definition.label || key
    };
    const logHint = latestLog(definition.log_glob);
    if (logHint) {
      entry.log_hint = logHint;
    }
    const artifacts = collectArtifacts(key, manifest);
    if (artifacts.length) {
      entry.artifacts = artifacts;
    }
    stages[key] = entry;
  });
  return {
    project,
    stages,
    manifest,
    state_path: statePath,
    updated: false
  };
}

async function parseBody(req: any): Promise<any> {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk: Buffer) => {
      raw += chunk.toString();
    });
    req.on("end", () => {
      if (!raw.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

const apiPlugin: PluginOption & {
  configureServer?(server: ViteDevServer): void;
  configurePreviewServer?(server: ViteDevServer): void;
} = {
  name: "project-dashboard-api",
  configureServer(server) {
    server.middlewares.use(async (req, res, next) => {
      if (!req.url?.startsWith("/api/")) {
        return next();
      }
      res.setHeader("Content-Type", "application/json");
      const url = new URL(req.url, "http://localhost");
      try {
        // NOTE: /api/projects ahora es manejado por el backend FastAPI (con autenticación)
        // Esto garantiza que los proyectos se creen con org_id correcto para multi-tenant

        if (req.method === "GET" && url.pathname === "/api/status") {
          const project = url.searchParams.get("project") || DEFAULT_PROJECT;
          try {
            const payload = await runPythonJSON([
              "main.py",
              "--log-level",
              "ERROR",
              "status",
              "--json",
              "--no-update",
              "--project",
              project
            ]);
            res.end(JSON.stringify(payload));
          } catch {
            res.end(JSON.stringify(buildFallbackSnapshot(project)));
          }
          return;
        }

        // Sprint 18: Todas las rutas de codificación van al backend FastAPI
        // para garantizar autenticación y multi-tenant correcto (org_id)
        // El proxy en línea 743+ redirigirá estas solicitudes

        // BYPASS: Las siguientes rutas ahora van al backend:
        // - POST /api/coding/assign
        // - POST /api/coding/suggest
        // - GET /api/coding/stats
        // - GET /api/coding/codes
        // - GET /api/fragments/sample
        // - GET /api/interviews
        // - GET /api/coding/citations
        // - GET /api/coding/fragment-context
        // - POST /api/analyze
        // - POST /api/ingest
        // - Todas las rutas /api/projects/*
        // - Todas las rutas /api/codes/*

        if (
          url.pathname.startsWith("/api/coding/") ||
          url.pathname.startsWith("/api/codes/") ||
          url.pathname.startsWith("/api/admin") ||
          url.pathname.startsWith("/api/maintenance") ||
          url.pathname.startsWith("/api/projects") ||
          url.pathname.startsWith("/api/fragments") ||
          url.pathname.startsWith("/api/interviews") ||
          url.pathname.startsWith("/api/analyze") ||
          url.pathname.startsWith("/api/ingest") ||
          url.pathname.startsWith("/api/graphrag") ||
          url.pathname.startsWith("/api/discovery") ||
          url.pathname.startsWith("/api/reports") ||
          url.pathname.startsWith("/api/link-prediction") ||
          url.pathname.startsWith("/api/health") ||
          url.pathname.startsWith("/api/auth") ||
          url.pathname.startsWith("/api/users") ||
          url.pathname.startsWith("/api/organizations") ||
          url.pathname.startsWith("/api/axial") ||
          url.pathname.startsWith("/api/search") ||
          url.pathname.startsWith("/api/neo4j") ||
          url.pathname.startsWith("/api/transcribe") ||
          url.pathname.startsWith("/api/export") ||
          url.pathname.startsWith("/api/analytics") ||
          url.pathname.startsWith("/api/familiarization")
        ) {
          // Pasar al proxy del backend (no manejar aquí)
          return next();
        }

        // Rutas no reconocidas por el middleware - pasan al proxy
        // o devuelven 404 si son /api/*
        if (url.pathname.startsWith("/api/")) {
          res.statusCode = 404;
          res.end(JSON.stringify({ error: "Ruta no disponible en middleware local." }));
          return;
        }

        // Cualquier otra ruta pasa al siguiente middleware
        return next();
      } catch (error) {
        res.statusCode = 500;
        res.end(
          JSON.stringify({
            error: error instanceof Error ? error.message : "Error inesperado"
          })
        );
      }
    });
  },
  configurePreviewServer(server) {
    if (typeof apiPlugin.configureServer === "function") {
      apiPlugin.configureServer(server);
    }
  }
};

const backendTarget = process.env.VITE_BACKEND_URL || "http://localhost:8000";
const enableBundleAnalysis = process.env.ANALYZE === "true";

export default defineConfig(({ mode }) => {
  // Ensure VITE_BACKEND_URL works from frontend/.env (not only from the shell)
  const env = loadEnv(mode, repoRoot, "");
  const backendTarget = env.VITE_BACKEND_URL || process.env.VITE_BACKEND_URL || "http://localhost:8000";
  const enableBundleAnalysis = (env.ANALYZE || process.env.ANALYZE) === "true";

  return {
    plugins: [react()],
    build: enableBundleAnalysis
      ? {
          rollupOptions: {
            plugins: [
              visualizer({
                filename: "bundle-stats.html",
                emitFile: true,
                gzipSize: true,
                brotliSize: true,
                open: false
              })
            ]
          }
        }
      : undefined,
    server: {
      fs: {
        allow: [repoRoot]
      },
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/healthz": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/neo4j": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/token": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/register": {
          target: backendTarget,
          changeOrigin: true,
        }
      }
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
      restoreMocks: true,
      coverage: {
        provider: "v8",
        reporter: ["text", "json-summary", "html"],
        exclude: [...configDefaults.coverage.exclude, "src/test/**"]
      }
    }
  };
});
