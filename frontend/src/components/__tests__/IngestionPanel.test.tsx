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
Object.defineProperty(global.crypto, 'randomUUID', {
    value: mockRandomUUID,
    writable: true,
});

beforeEach(() => {
    vi.clearAllMocks();
    mockRandomUUID.mockReturnValue('12345678-1234-1234-1234-123456789012');
});

describe("IngestionPanel", () => {
    const defaultProps = {
        project: "test-project",
    };

    test("renders ingestion form correctly", () => {
        render(<IngestionPanel {...defaultProps} />);

        // Should show title
        expect(screen.getByText(/etapa 1.*ingesta/i)).toBeInTheDocument();

        // Should show inputs field
        expect(screen.getByLabelText(/entradas.*ruta.*patron/i)).toBeInTheDocument();

        // Should show submit button
        expect(screen.getByRole("button", { name: /ejecutar ingesta/i })).toBeInTheDocument();
    });

    test("shows fragmentation parameters", () => {
        render(<IngestionPanel {...defaultProps} />);

        // Should show fragmentation fieldset
        expect(screen.getByText(/parametros de fragmentacion/i)).toBeInTheDocument();

        // Should have batch size, min chars, max chars inputs
        const batchInput = screen.getByDisplayValue("64"); // default batch size
        const minCharsInput = screen.getByDisplayValue("200"); // default min chars
        const maxCharsInput = screen.getByDisplayValue("1200"); // default max chars

        expect(batchInput).toBeInTheDocument();
        expect(minCharsInput).toBeInTheDocument();
        expect(maxCharsInput).toBeInTheDocument();
    });

    test("validate inputs are required", async () => {
        render(<IngestionPanel {...defaultProps} />);

        const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

        // Button should be disabled when inputs are empty
        expect(submitButton).toBeDisabled();
    });

    test("enables submit when inputs are provided", async () => {
        const user = userEvent.setup();
        render(<IngestionPanel {...defaultProps} />);

        const inputsField = screen.getByLabelText(/entradas.*ruta.*patron/i);
        const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

        // Type something
        await user.type(inputsField, "entrevistas/*.docx");

        // Button should now be enabled
        expect(submitButton).not.toBeDisabled();
    });

    test("performs ingestion", async () => {
        const user = userEvent.setup();

        mockApiFetchJson.mockResolvedValueOnce({
            project: "test-project",
            exit_code: 0,
            files: ["entrevista1.docx", "entrevista2.docx"],
            result: { fragments: 25 },
        });

        render(<IngestionPanel {...defaultProps} />);

        const inputsField = screen.getByLabelText(/entradas.*ruta.*patron/i);
        const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

        await user.type(inputsField, "data/*.docx");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockApiFetchJson).toHaveBeenCalledWith("/api/ingest", expect.objectContaining({
                method: "POST",
                body: expect.stringContaining("data/*.docx"),
            }));
        });

        // Should show result
        await waitFor(() => {
            expect(screen.getByText(/resultado/i)).toBeInTheDocument();
        });
    });

    test("sends correct parameters", async () => {
        const user = userEvent.setup();

        mockApiFetchJson.mockResolvedValueOnce({
            project: "test-project",
            exit_code: 0,
        });

        render(<IngestionPanel {...defaultProps} />);

        const inputsField = screen.getByLabelText(/entradas.*ruta.*patron/i);
        const batchSizeField = screen.getByLabelText(/batch size/i);
        const minCharsField = screen.getByLabelText(/min chars/i);
        const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

        await user.clear(batchSizeField);
        await user.type(batchSizeField, "32");
        await user.clear(minCharsField);
        await user.type(minCharsField, "300");
        await user.type(inputsField, "test.docx");
        await user.click(submitButton);

        await waitFor(() => {
            const call = mockApiFetchJson.mock.calls[0];
            const body = call?.[1]?.body;
            expect(body).toBeDefined();
            const parsed = JSON.parse(body as string);

            expect(parsed.batch_size).toBe(32);
            expect(parsed.min_chars).toBe(300);
        });
    });

    test("shows loading state during ingestion", async () => {
        const user = userEvent.setup();

        // Mock slow ingestion
        mockApiFetchJson.mockImplementationOnce(
            () => new Promise(resolve => setTimeout(() => resolve({
                project: "test-project",
                exit_code: 0,
            }), 100))
        );

        render(<IngestionPanel {...defaultProps} />);

        const inputsField = screen.getByLabelText(/entradas.*ruta.*patron/i);
        const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

        await user.type(inputsField, "test.docx");
        await user.click(submitButton);

        // Should show loading text
        await waitFor(() => {
            expect(screen.getByText(/procesando/i)).toBeInTheDocument();
        });

        // Button should be disabled
        expect(submitButton).toBeDisabled();
    });

    test("handles ingestion error", async () => {
        const user = userEvent.setup();

        mockApiFetchJson.mockRejectedValueOnce(new Error("File not found"));

        render(<IngestionPanel {...defaultProps} />);

        const inputsField = screen.getByLabelText(/entradas.*ruta.*patron/i);
        const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

        await user.type(inputsField, "missing.docx");
        await user.click(submitButton);

        // Should show error message
        await waitFor(() => {
            expect(screen.getByText(/error en la ingesta/i)).toBeInTheDocument();
            expect(screen.getByText(/file not found/i)).toBeInTheDocument();
        });
    });

    test("allows generating new run_id", async () => {
        const user = userEvent.setup();

        render(<IngestionPanel {...defaultProps} />);

        const newRunIdButton = screen.getByRole("button", { name: /nuevo run_id/i });
        const runIdField = screen.getByLabelText(/run_id.*opcional/i);

        // Should have initial run_id
        expect(runIdField).toHaveValue('12345678123412341234123456789012');

        // Generate new one
        mockRandomUUID.mockReturnValueOnce('87654321-4321-4321-4321-210987654321');
        await user.click(newRunIdButton);

        // Should update
        await waitFor(() => {
            expect(runIdField).toHaveValue('87654321432143214321210987654321');
        });
    });

    test("allows optional metadata JSON", async () => {
        const user = userEvent.setup();

        mockApiFetchJson.mockResolvedValueOnce({
            project: "test-project",
            exit_code: 0,
        });

        render(<IngestionPanel {...defaultProps} />);

        const inputsField = screen.getByLabelText(/entradas.*ruta.*patron/i);
        const metaField = screen.getByLabelText(/metadata json.*opcional/i);
        const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

        await user.type(inputsField, "test.docx");
        await user.type(metaField, "meta.json");
        await user.click(submitButton);

        await waitFor(() => {
            const call = mockApiFetchJson.mock.calls[0];
            const body = call?.[1]?.body;
            expect(body).toBeDefined();
            const parsed = JSON.parse(body as string);

            expect(parsed.meta_json).toBe("meta.json");
        });
    });

    test("disables form when disabled prop is true", () => {
        render(<IngestionPanel {...defaultProps} disabled={true} />);

        const inputsField = screen.getByLabelText(/entradas.*ruta.*patron/i);
        const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

        expect(inputsField).toBeDisabled();
        expect(submitButton).toBeDisabled();
    });

    test("calls onCompleted callback after successful ingestion", async () => {
        const user = userEvent.setup();
        const onCompleted = vi.fn();

        const result = {
            project: "test-project",
            exit_code: 0,
            files: ["test.docx"],
        };

        mockApiFetchJson.mockResolvedValueOnce(result);

        render(<IngestionPanel {...defaultProps} onCompleted={onCompleted} />);

        const inputsField = screen.getByLabelText(/entradas.*ruta.*patron/i);
        const submitButton = screen.getByRole("button", { name: /ejecutar ingesta/i });

        await user.type(inputsField, "test.docx");
        await user.click(submitButton);

        await waitFor(() => {
            expect(onCompleted).toHaveBeenCalledWith(result);
        });
    });
});
