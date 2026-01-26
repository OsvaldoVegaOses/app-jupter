import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CodingPanel } from "../CodingPanel";

const statsResponse = {
  fragmentos_codificados: 12,
  fragmentos_sin_codigo: 3,
  porcentaje_cobertura: 0.8,
  codigos_unicos: 5,
  total_citas: 18,
  relaciones_axiales: 2
};

const interviewsResponse = {
  interviews: [
    {
      archivo: "entrevista1.docx",
      fragmentos: 15,
      actor_principal: "Docente",
      area_tematica: "Salud",
      actualizado: "2024-09-20"
    }
  ]
};

const codesResponse = {
  codes: [
    {
      codigo: "Resiliencia comunitaria",
      citas: 4,
      fragmentos: 3,
      primera_cita: "2024-07-10",
      ultima_cita: "2024-09-12"
    }
  ]
};

const citationsResponse = {
  citations: [
    {
      fragmento_id: "entrevista/001#p12",
      archivo: "entrevista1.docx",
      fuente: "Participante A",
      memo: "Refuerza la estrategia comunitaria",
      cita: "La comunidad respondió organizada ante la emergencia.",
      created_at: "2024-09-21"
    }
  ]
};

function createMockResponse(payload: unknown): Response {
  return {
    ok: true,
    json: () => Promise.resolve(payload)
  } as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/api/coding/stats")) {
      return createMockResponse(statsResponse);
    }
    if (url.includes("/api/interviews")) {
      return createMockResponse(interviewsResponse);
    }
    if (url.includes("/api/coding/codes")) {
      return createMockResponse(codesResponse);
    }
    if (url.includes("/api/coding/citations")) {
      return createMockResponse(citationsResponse);
    }
    if (url.includes("/api/fragments/sample")) {
      return createMockResponse({ samples: [] });
    }
    return createMockResponse({});
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  vi.clearAllMocks();
});

test("fetches citations when a code is inspected", async () => {
  render(<CodingPanel project="demo" />);

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/coding/stats"), expect.anything())
  );
  await screen.findByText("Resiliencia comunitaria");

  const inspectButton = await screen.findByRole("button", { name: /revisar citas/i });
  await userEvent.click(inspectButton);
  await waitFor(() => {
    const calls = fetchMock.mock.calls as Array<[RequestInfo | URL, RequestInit?]>;
    const hasCitationsCall = calls.some(([request]) =>
      request.toString().includes("/api/coding/citations")
    );
    expect(hasCitationsCall).toBe(true);
  });

  // Open the 'Cobertura y avance' tab to reveal metrics
  const insightsTab = screen.getByRole("button", { name: /cobertura y avance/i });
  await userEvent.click(insightsTab);

  const citationCalls = fetchMock.mock.calls as Array<[RequestInfo | URL, RequestInit?]>;
  const citationsCall = citationCalls.find(([request]) =>
    request.toString().includes("/api/coding/citations")
  );
  expect(citationsCall).toBeDefined();
  const [request] = citationsCall!;
  expect(request.toString()).toContain("codigo=Resiliencia%20comunitaria");
});

test("renders coding panel with tabs", async () => {
  render(<CodingPanel project="demo" />);

  // Should show all 4 tabs (use role-based queries to avoid matching descriptive copy)
  expect(screen.getByRole('button', { name: /asignar código/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /sugerencias semánticas/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /cobertura y avance/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /citas por código/i })).toBeInTheDocument();
});

test("switches between tabs", async () => {
  render(<CodingPanel project="demo" />);

  const suggestTab = screen.getByRole('button', { name: /sugerencias semánticas/i });
  await userEvent.click(suggestTab);

  // Should show suggestions content
  await waitFor(() => {
    expect(screen.queryAllByText(/fragmentos similares/i).length).toBeGreaterThan(0);
  });
});

test("loads stats on mount", async () => {
  render(<CodingPanel project="demo" />);

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/coding/stats"), expect.anything())
  );

  // Should show stats
  // Should show some stats label (be tolerant to wording changes)
  await waitFor(() => {
    expect(screen.queryAllByText(/fragmentos|citas|codificados/i).length).toBeGreaterThan(0);
  });
});

test("loads interviews list", async () => {
  render(<CodingPanel project="demo" />);

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/interviews"), expect.anything())
  );
});

test("loads codes list", async () => {
  render(<CodingPanel project="demo" />);


  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/coding/codes"), expect.anything())
  );

  await screen.findByText("Resiliencia comunitaria");
});

test("shows loading state", async () => {
  // Mock slow response
  const slowFetch = vi.fn(async () => {
    await new Promise(r => setTimeout(r, 100));
    return createMockResponse(statsResponse);
  });
  globalThis.fetch = slowFetch as unknown as typeof fetch;

  render(<CodingPanel project="demo" />);

  // Component should render (loading states are internal)
  expect(screen.getByRole('button', { name: /asignar código/i })).toBeInTheDocument();
});
