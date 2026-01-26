import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { GraphRAGPanel } from "../GraphRAGPanel";
import * as api from "../../services/api";

// Mock API module
vi.mock("../../services/api", () => ({
    graphragQuery: vi.fn(),
    saveGraphRAGReport: vi.fn(),
    submitCandidate: vi.fn(),
    checkBatchCodes: vi.fn(),
}));

const mockGraphragQuery = vi.mocked(api.graphragQuery);
const mockSaveGraphRAGReport = vi.mocked(api.saveGraphRAGReport);
const mockCheckBatchCodes = vi.mocked(api.checkBatchCodes);

beforeEach(() => {
    vi.clearAllMocks();
});

describe("GraphRAGPanel", () => {
    const defaultProps = {
        project: "test-project",
    };

    test("renders graph RAG form correctly", () => {
        render(<GraphRAGPanel {...defaultProps} />);

        // Should show title
        expect(screen.getByText(/graphrag - chat con contexto de grafo/i)).toBeInTheDocument();

        // Should show query textarea
        expect(screen.getByPlaceholderText(/haz una pregunta/i)).toBeInTheDocument();

        // Should show chain of thought checkbox
        expect(screen.getByText(/razonamiento paso a paso/i)).toBeInTheDocument();

        // Should show submit button
        expect(screen.getByRole("button", { name: /preguntar/i })).toBeInTheDocument();
    });

    test("validates query is required", async () => {
        const user = userEvent.setup();
        render(<GraphRAGPanel {...defaultProps} />);

        const submitButton = screen.getByRole("button", { name: /preguntar/i });

        // Button should be disabled when query is empty
        expect(submitButton).toBeDisabled();

        // Type something
        const textarea = screen.getByPlaceholderText(/haz una pregunta/i);
        await user.type(textarea, "test");

        // Button should now be enabled
        expect(submitButton).not.toBeDisabled();
    });

    test("performs GraphRAG query", async () => {
        const user = userEvent.setup();

        mockGraphragQuery.mockResolvedValueOnce({
            query: "¿Qué factores causan inseguridad?",
            answer: "Los principales factores son económicos y sociales.",
            context: "Mock context",
            nodes: [
                { id: "Inseguridad", type: "Codigo", label: "Inseguridad" },
                { id: "Economia", type: "Codigo", label: "Economía" },
            ],
            relationships: [
                { from: "Economia", to: "Inseguridad", type: "CAUSA" },
            ],
            fragments: [],
        });

        render(<GraphRAGPanel {...defaultProps} />);

        const textarea = screen.getByPlaceholderText(/haz una pregunta/i);
        const submitButton = screen.getByRole("button", { name: /preguntar/i });

        await user.type(textarea, "¿Qué factores causan inseguridad?");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockGraphragQuery).toHaveBeenCalledWith({
                query: "¿Qué factores causan inseguridad?",
                project: "test-project",
                include_fragments: true,
                chain_of_thought: false,
            });
        });

        // Should show answer
        await waitFor(() => {
            expect(screen.getByText(/los principales factores son económicos y sociales/i)).toBeInTheDocument();
        });
    });

    test("enables chain of thought", async () => {
        const user = userEvent.setup();

        mockGraphragQuery.mockResolvedValueOnce({
            query: "test",
            answer: "answer with reasoning",
            context: "",
            nodes: [],
            relationships: [],
            fragments: [],
        });

        render(<GraphRAGPanel {...defaultProps} />);

        const textarea = screen.getByPlaceholderText(/haz una pregunta/i);
        const checkbox = screen.getByRole("checkbox");
        const submitButton = screen.getByRole("button", { name: /preguntar/i });

        await user.type(textarea, "test question");
        await user.click(checkbox);
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockGraphragQuery).toHaveBeenCalledWith(
                expect.objectContaining({
                    chain_of_thought: true,
                })
            );
        });
    });

    test("shows loading state during query", async () => {
        const user = userEvent.setup();

        // Mock slow query
        mockGraphragQuery.mockImplementationOnce(
            () => new Promise(resolve => setTimeout(() => resolve({
                query: "test",
                answer: "answer",
                context: "",
                nodes: [],
                relationships: [],
                fragments: [],
            }), 100))
        );

        render(<GraphRAGPanel {...defaultProps} />);

        const textarea = screen.getByPlaceholderText(/haz una pregunta/i);
        const submitButton = screen.getByRole("button", { name: /preguntar/i });

        await user.type(textarea, "test");
        await user.click(submitButton);

        // Should show loading text
        await waitFor(() => {
            expect(screen.getByText(/consultando/i)).toBeInTheDocument();
        });

        // Button should be disabled
        expect(submitButton).toBeDisabled();
    });

    test("handles query error", async () => {
        const user = userEvent.setup();

        mockGraphragQuery.mockRejectedValueOnce(new Error("Network error"));

        render(<GraphRAGPanel {...defaultProps} />);

        const textarea = screen.getByPlaceholderText(/haz una pregunta/i);
        const submitButton = screen.getByRole("button", { name: /preguntar/i });

        await user.type(textarea, "test");
        await user.click(submitButton);

        // Should show error message (check the specific message)
        await waitFor(() => {
            expect(screen.getByText(/network error/i)).toBeInTheDocument();
        });
    });

    test("shows save report button after successful query", async () => {
        const user = userEvent.setup();

        mockGraphragQuery.mockResolvedValueOnce({
            query: "test",
            answer: "test answer",
            context: "context",
            nodes: [],
            relationships: [],
            fragments: [],
        });

        render(<GraphRAGPanel {...defaultProps} />);

        const textarea = screen.getByPlaceholderText(/haz una pregunta/i);
        const submitButton = screen.getByRole("button", { name: /preguntar/i });

        await user.type(textarea, "test");
        await user.click(submitButton);

        // Wait for response
        await waitFor(() => {
            expect(screen.getByText(/test answer/i)).toBeInTheDocument();
        });

        // Should show save button
        expect(screen.getByRole("button", { name: /guardar informe/i })).toBeInTheDocument();
    });

    test("shows graph context when available", async () => {
        const user = userEvent.setup();

        mockGraphragQuery.mockResolvedValueOnce({
            query: "test",
            answer: "answer",
            context: "Node: Codigo1\nRelationship: A -> B",
            nodes: [
                { id: "A", type: "Codigo", label: "Code A" },
                { id: "B", type: "Codigo", label: "Code B" },
            ],
            relationships: [
                { from: "A", to: "B", type: "RELATED" },
            ],
            fragments: [],
        });

        render(<GraphRAGPanel {...defaultProps} />);

        const textarea = screen.getByPlaceholderText(/haz una pregunta/i);
        await user.type(textarea, "test");
        await user.click(screen.getByRole("button", { name: /preguntar/i }));

        await waitFor(() => {
            expect(screen.getByText(/contexto del grafo \(2 nodos\)/i)).toBeInTheDocument();
        });
    });

    test("shows fragments when available", async () => {
        const user = userEvent.setup();

        mockGraphragQuery.mockResolvedValueOnce({
            query: "test",
            answer: "answer",
            context: "",
            nodes: [],
            relationships: [],
            fragments: [
                {
                    fragmento_id: "frag1",
                    fragmento: "Este es un fragmento de evidencia relevante para la consulta.",
                    archivo: "documento.docx",
                    score: 0.92,
                },
            ],
        });

        render(<GraphRAGPanel {...defaultProps} />);

        const textarea = screen.getByPlaceholderText(/haz una pregunta/i);
        await user.type(textarea, "test");
        await user.click(screen.getByRole("button", { name: /preguntar/i }));

        await waitFor(() => {
            expect(screen.getByText(/fragmentos de evidencia \(1\)/i)).toBeInTheDocument();
            expect(screen.getByText(/documento\.docx/i)).toBeInTheDocument();
        });
    });

    test("shows send codes button when codes are extracted", async () => {
        const user = userEvent.setup();

        mockGraphragQuery.mockResolvedValueOnce({
            query: "test",
            answer: "answer",
            context: "",
            nodes: [
                { id: "Codigo1", type: "Codigo", label: "Código 1" },
                { id: "Codigo2", type: "Code", label: "Código 2" },
                { id: "OtherNode", type: "Concept", label: "Not a code" },
            ],
            relationships: [],
            fragments: [],
        });

        render(<GraphRAGPanel {...defaultProps} />);

        const textarea = screen.getByPlaceholderText(/haz una pregunta/i);
        await user.type(textarea, "test");
        await user.click(screen.getByRole("button", { name: /preguntar/i }));

        // Should show button for sending 2 codes
        await waitFor(() => {
            expect(screen.getByRole("button", { name: /enviar 2 códigos/i })).toBeInTheDocument();
        });
    });
});
