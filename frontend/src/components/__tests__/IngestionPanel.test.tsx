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

// Mock crypto.randomUUID
const mockRandomUUID = vi.fn();
Object.defineProperty(global.crypto, "randomUUID", {
  value: mockRandomUUID,
  writable: true,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockRandomUUID.mockReturnValue("12345678-1234-1234-1234-123456789012");
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
    // New ingestion UI uses a dropzone file input; select it and upload a file
    const fileInput = screen.getByLabelText(/click para seleccionar|arrastra archivos/i) as HTMLInputElement;
    const submitButton = screen.getByRole("button", { name: /ejecutar ingesta|ingestar archivos|ingestar|📥 Ingestar Archivos/i });

    expect(submitButton).toBeDisabled();

    // Simulate file upload
    const file = new File(["dummy content"], "entrevista1.docx", { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    await user.upload(fileInput, file);

    // Now button should enable
    await waitFor(() => expect(submitButton).toBeEnabled());

    await user.click(submitButton);

    await waitFor(() => {
      expect(mockApiFetchJson).toHaveBeenCalledWith(
        "/api/ingest",
        expect.objectContaining({ method: "POST" })
      );
    });

    // Should show a success/result marker
    await waitFor(() => expect(screen.queryByText(/resultado/i)).not.toBeNull());
  });

  test("shows error when ingestion fails", async () => {
    const user = userEvent.setup();

    mockApiFetchJson.mockRejectedValueOnce(new Error("File not found"));

    render(<IngestionPanel {...defaultProps} />);

    const inputsField = screen.getByLabelText(/entradas/i);
    const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

    await user.type(inputsField, "missing.docx");
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/error en la ingesta/i)).toBeInTheDocument();
      expect(screen.getByText(/file not found/i)).toBeInTheDocument();
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
