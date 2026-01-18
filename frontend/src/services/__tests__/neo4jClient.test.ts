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
      "http://localhost:8080/neo4j/query",
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
    await runNeo4jQuery({ cypher: "RETURN 1", project: "demo" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/neo4j/query",
      expect.objectContaining({
        headers: expect.not.objectContaining({ "X-API-Key": expect.anything() }),
      })
    );
  });

  it("permite exportar en CSV", async () => {
    vi.stubEnv("VITE_NEO4J_API_URL", "http://localhost:8080/neo4j/query");
    vi.stubEnv("VITE_NEO4J_API_KEY", "secret");

    await exportNeo4jQuery({ cypher: "RETURN 1", project: "demo" }, "csv");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8080/neo4j/export",
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
