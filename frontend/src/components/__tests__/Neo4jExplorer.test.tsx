import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { Neo4jExplorer } from "../Neo4jExplorer";
import type { Neo4jQueryResult } from "../../services/neo4jClient";

vi.mock("../../services/neo4jClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/neo4jClient")>();
  return {
    ...actual,
    runNeo4jQuery: vi.fn(),
    exportNeo4jQuery: vi.fn()
  };
});

const mockedRunQuery = vi.mocked(
  await import("../../services/neo4jClient").then((module) => module.runNeo4jQuery)
);

const mockedExportQuery = vi.mocked(
  await import("../../services/neo4jClient").then((module) => module.exportNeo4jQuery)
);

const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;
const originalAnchorClick = HTMLAnchorElement.prototype.click;

function setup() {
  mockedRunQuery.mockResolvedValue({
    data: { raw: [{ n: 1 }] },
    durationMs: 25.4
  } as Neo4jQueryResult);
  mockedExportQuery.mockResolvedValue({ blob: new Blob(), durationMs: 12 });
  render(<Neo4jExplorer project="demo" />);
}

describe("Neo4jExplorer", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    HTMLAnchorElement.prototype.click = vi.fn();
    URL.createObjectURL = vi.fn(() => "blob://download") as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL;
  });

  it("ejecuta la consulta y muestra la pestaña RAW por defecto", async () => {
    setup();

    fireEvent.click(screen.getByRole("button", { name: /ejecutar consulta/i }));

    await waitFor(() => expect(mockedRunQuery).toHaveBeenCalled());

    expect(mockedRunQuery.mock.calls[0][0]).toMatchObject({
      cypher: expect.stringContaining("MATCH"),
      formats: ["raw", "table"],
      project: "demo"
    });

    expect(screen.getByRole("button", { name: /RAW/i })).toBeInTheDocument();
    expect(screen.getByText(/\{\s+"n":\s+1\s+\}/)).toBeInTheDocument();
    expect(screen.getByText(/25\.40 ms/)).toBeInTheDocument();
  });

  it("muestra error cuando la API responde con fallo", async () => {
    mockedRunQuery.mockRejectedValueOnce(new Error("Boom"));
    render(<Neo4jExplorer project="demo" />);

    fireEvent.change(screen.getByLabelText(/Parámetros/i), {
      target: { value: "limit=10" }
    });
    fireEvent.click(screen.getByRole("button", { name: /ejecutar consulta/i }));

    await waitFor(() => expect(screen.getByText(/Boom/)).toBeInTheDocument());
  });

  it("permite exportar CSV", async () => {
    setup();

    fireEvent.click(screen.getByRole("button", { name: /exportar csv/i }));

    await waitFor(() =>
      expect(mockedExportQuery).toHaveBeenCalledWith(
        expect.objectContaining({ cypher: expect.any(String), project: "demo" }),
        "csv"
      )
    );
    expect(screen.getByText(/Exportación CSV generada correctamente/i)).toBeInTheDocument();
  });
});

afterAll(() => {
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
  HTMLAnchorElement.prototype.click = originalAnchorClick;
});
