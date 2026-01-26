import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { exportNeo4jQuery, runNeo4jQuery } from "../neo4jClient";

const originalFetch = global.fetch;

describe("neo4jClient", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: vi.fn(() => "12.5") },
      json: async () => ({ raw: [] }),
      blob: async () => new Blob([], { type: "text/csv" }),
    }) as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("envia la API key cuando está configurada", async () => {
    vi.stubEnv("VITE_NEO4J_API_URL", "http://localhost:8080/neo4j/query");
    vi.stubEnv("VITE_NEO4J_API_KEY", "secret");

    const result = await runNeo4jQuery({ cypher: "RETURN 1", project: "demo" });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/neo4j/query'),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "content-type": "application/json",
          "X-API-Key": "secret",
        }),
      })
    );
    expect(result.durationMs).toBeCloseTo(12.5, 1);
  });

  it("omite el header cuando no hay API key", async () => {
    vi.stubEnv("VITE_NEO4J_API_URL", "");
    // Ensure API key is not present in env for this case
    vi.stubEnv("VITE_NEO4J_API_KEY", "");
    await runNeo4jQuery({ cypher: "RETURN 1", project: "demo" });
    // Fetch should be called against the neo4j endpoint; header presence is conditional
    expect(global.fetch).toHaveBeenCalled();
    const call = (global.fetch as unknown as any).mock.calls[0];
    const options = call[1] || {};
    // headers can be a Headers instance or plain object
    const headers = options.headers;
    if (headers && typeof headers.get === 'function') {
      expect(headers.get('content-type') || headers.get('Content-Type')).toBeTruthy();
      expect(headers.get('X-API-Key')).toBeFalsy();
    } else {
      expect((headers && (headers['content-type'] || headers['Content-Type']))).toBeTruthy();
      expect(!(headers && (headers['X-API-Key'] || headers['x-api-key']))).toBeTruthy();
    }
  });

  it("permite exportar en CSV", async () => {
    vi.stubEnv("VITE_NEO4J_API_URL", "http://localhost:8080/neo4j/query");
    vi.stubEnv("VITE_NEO4J_API_KEY", "secret");

    await exportNeo4jQuery({ cypher: "RETURN 1", project: "demo" }, "csv");

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/neo4j/export'),
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-API-Key": "secret" }),
      })
    );
  });
});

afterAll(() => {
  global.fetch = originalFetch;
});
