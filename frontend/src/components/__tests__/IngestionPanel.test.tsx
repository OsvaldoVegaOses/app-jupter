import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { IngestionPanel } from "../IngestionPanel";
import * as api from "../../services/api";

// Mock API module
vi.mock("../../services/api", () => ({
  apiFetchJson: vi.fn(),
}));

const mockApiFetchJson = vi.mocked(api.apiFetchJson);

// Provide a global fetch mock for the upload-and-ingest flow used by the component
let fetchMock: ReturnType<typeof vi.fn>;

// Mock crypto.randomUUID
const mockRandomUUID = vi.fn();
Object.defineProperty(global.crypto, "randomUUID", {
  value: mockRandomUUID,
  writable: true,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockRandomUUID.mockReturnValue("12345678-1234-1234-1234-123456789012");
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/api/upload-and-ingest")) {
      return {
        ok: true,
        json: async () => ({ project: "test-project", exit_code: 0, files: ["entrevista1.docx"] })
      } as unknown as Response;
    }
    return { ok: true, json: async () => ({}) } as unknown as Response;
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

describe("IngestionPanel", () => {
  const defaultProps = { project: "test-project" };

  test("renders ingestion form correctly", () => {
    render(<IngestionPanel {...defaultProps} />);

    // Should show title
    expect(screen.getByRole('heading', { level: 2, name: /ingesta de documentos/i })).toBeInTheDocument();

    // Dropzone label should be present and associated to the file input
    expect(screen.getByLabelText(/click para seleccionar|arrastra archivos/i)).toBeInTheDocument();

    // Should show submit button
    expect(screen.getByRole("button", { name: /ingestar archivos|ingestar/i })).toBeInTheDocument();
  });

  test("enables submit when inputs are provided and performs ingestion", async () => {
    const user = userEvent.setup();

    mockApiFetchJson.mockResolvedValueOnce({
      project: "test-project",
      exit_code: 0,
      files: ["entrevista1.docx"],
    });

    render(<IngestionPanel {...defaultProps} />);

    // accept several possible label forms (legacy or updated wording)
    // New ingestion UI uses a dropzone file input; prefer data-testid, fallback to label
    const fileInput =
      screen.queryByTestId("ingestion-file-input") ??
      (screen.getByLabelText(/click para seleccionar|arrastra archivos/i) as HTMLInputElement);
    const submitButton = screen.getByRole("button", { name: /ejecutar ingesta|ingestar archivos|ingestar|📥 Ingestar Archivos/i });

    expect(submitButton).toBeDisabled();

    // Simulate file upload
    const file = new File(["dummy content"], "entrevista1.docx", { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    await user.upload(fileInput, file);

    // Now button should enable
    await waitFor(() => expect(submitButton).toBeEnabled());

    await user.click(submitButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
      // Should have called the upload-and-ingest endpoint
      expect(fetchMock.mock.calls.some(([req]) => req.toString().includes('/api/upload-and-ingest'))).toBe(true);
    });

    // Should show the uploaded file in the queue and a completed stat
    await waitFor(() => {
      expect(screen.getByText(/entrevista1.docx/i)).toBeInTheDocument();
      expect(screen.getByText(/ingestados/i)).toBeInTheDocument();
    });
  });

  test("shows error when ingestion fails", async () => {
    const user = userEvent.setup();

    // Simulate a network error for the upload endpoint
    fetchMock.mockRejectedValueOnce(new Error("File not found"));

    render(<IngestionPanel {...defaultProps} />);

    // Simulate uploading a file but the API fails
    const fileInput =
      screen.queryByTestId("ingestion-file-input") ??
      (screen.getByLabelText(/click para seleccionar|arrastra archivos/i) as HTMLInputElement);
    const submitButton = screen.getByRole("button", { name: /ejecutar ingesta|ingestar archivos|ingestar|📥 Ingestar Archivos/i });

    const file = new File(["dummy"], "missing.docx", { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    await user.upload(fileInput, file);
    await waitFor(() => expect(submitButton).toBeEnabled());
    await user.click(submitButton);

    await waitFor(() => {
      // The UI shows the file in the queue with an error badge
      expect(screen.getByText(/missing.docx/i)).toBeInTheDocument();
      expect(screen.getByText(/file not found|failed to parse url/i)).toBeInTheDocument();
    });
  });

  test("toggles advanced options and updates batch size", async () => {
    const user = userEvent.setup();

    render(<IngestionPanel {...defaultProps} />);

    const toggle = screen.getByRole('button', { name: /opciones avanzadas/i });
    expect(toggle).toBeInTheDocument();

    await user.click(toggle);

    const batchInput = screen.getByLabelText(/batch size/i);
    expect(batchInput).toBeInTheDocument();

    await user.clear(batchInput);
    await user.type(batchInput, '32');
    expect(batchInput).toHaveValue(32);
  });
});
