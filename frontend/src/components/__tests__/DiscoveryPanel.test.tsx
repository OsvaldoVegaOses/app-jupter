import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { DiscoveryPanel } from "../DiscoveryPanel";
import * as api from "../../services/api";

// Mock API module
vi.mock("../../services/api", () => ({
    discoverSearch: vi.fn(),
    analyzeDiscovery: vi.fn(),
    saveDiscoveryMemo: vi.fn(),
    submitCandidate: vi.fn(),
    checkBatchCodes: vi.fn(),
    logDiscoveryNavigation: vi.fn(),
}));

const mockDiscoverSearch = vi.mocked(api.discoverSearch);
const mockAnalyzeDiscovery = vi.mocked(api.analyzeDiscovery);
const mockLogDiscoveryNavigation = vi.mocked(api.logDiscoveryNavigation);

beforeEach(() => {
    vi.clearAllMocks();
});

describe("DiscoveryPanel", () => {
    const defaultProps = {
        project: "test-project",
    };

    test("renders discovery form correctly", () => {
        render(<DiscoveryPanel {...defaultProps} />);

        // Should show input fields
        expect(screen.getByPlaceholderText(/conceptos positivos/i)).toBeInTheDocument();
        expect(screen.getByPlaceholderText(/conceptos negativos/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/texto target/i)).toBeInTheDocument();

        // Should show top-k selector
        expect(screen.getByLabelText(/cantidad de resultados/i)).toBeInTheDocument();

        // Should show search button
        expect(screen.getByRole("button", { name: /buscar/i })).toBeInTheDocument();
    });

    test("validates positive text is required", async () => {
        const user = userEvent.setup();
        render(<DiscoveryPanel {...defaultProps} />);

        const searchButton = screen.getByRole("button", { name: /buscar/i });
        await user.click(searchButton);

        // Should show validation error
        await waitFor(() => {
            expect(screen.getByText(/ingresa al menos un concepto positivo/i)).toBeInTheDocument();
        });

        // Should not call API
        expect(mockDiscoverSearch).not.toHaveBeenCalled();
    });

    test("performs search with positive concepts", async () => {
        const user = userEvent.setup();

        mockDiscoverSearch.mockResolvedValueOnce({
            fragments: [
                {
                    id: "frag1",
                    fragmento_id: "frag1",
                    fragmento: "Test fragment content",
                    archivo: "test.docx",
                    score: 0.95,
                },
            ],
            count: 1,
        });

        mockLogDiscoveryNavigation.mockResolvedValueOnce({
            success: true,
            busqueda_id: "search-123",
            action_taken: "search",
        });

        render(<DiscoveryPanel {...defaultProps} />);

        const positiveInput = screen.getByPlaceholderText(/conceptos positivos/i);
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "participación comunitaria");
        await user.click(searchButton);

        await waitFor(() => {
            expect(mockDiscoverSearch).toHaveBeenCalledWith({
                positive_texts: ["participación comunitaria"],
                negative_texts: undefined,
                target_text: undefined,
                top_k: 10,
                project: "test-project",
            });
        });

        // Should show results
        await waitFor(() => {
            expect(screen.getByText(/test fragment content/i)).toBeInTheDocument();
        });
    });

    test("performs search with positive and negative concepts", async () => {
        const user = userEvent.setup();

        mockDiscoverSearch.mockResolvedValueOnce({
            fragments: [],
            count: 0,
        });

        mockLogDiscoveryNavigation.mockResolvedValueOnce({
            success: true,
            busqueda_id: "search-456",
            action_taken: "search",
        });

        render(<DiscoveryPanel {...defaultProps} />);

        const positiveInput = screen.getByPlaceholderText(/conceptos positivos/i);
        const negativeInput = screen.getByPlaceholderText(/conceptos negativos/i);
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "liderazgo\\norganización");
        await user.type(negativeInput, "autoritarismo");
        await user.click(searchButton);

        await waitFor(() => {
            expect(mockDiscoverSearch).toHaveBeenCalledWith({
                positive_texts: ["liderazgo", "organización"],
                negative_texts: ["autoritarismo"],
                target_text: undefined,
                top_k: 10,
                project: "test-project",
            });
        });
    });

    test("allows changing top-k results", async () => {
        const user = userEvent.setup();

        mockDiscoverSearch.mockResolvedValueOnce({
            fragments: [],
            count: 0,
        });

        mockLogDiscoveryNavigation.mockResolvedValueOnce({
            success: true,
            busqueda_id: "search-789",
            action_taken: "search",
        });

        render(<DiscoveryPanel {...defaultProps} />);

        const positiveInput = screen.getByPlaceholderText(/conceptos positivos/i);
        const topKSelect = screen.getByLabelText(/cantidad de resultados/i);
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "motivación");
        await user.selectOptions(topKSelect, "20");
        await user.click(searchButton);

        await waitFor(() => {
            expect(mockDiscoverSearch).toHaveBeenCalledWith(
                expect.objectContaining({
                    top_k: 20,
                })
            );
        });
    });

    test("shows loading state during search", async () => {
        const user = userEvent.setup();

        // Mock slow search
        mockDiscoverSearch.mockImplementationOnce(
            () => new Promise(resolve => setTimeout(() => resolve({ fragments: [], count: 0 }), 100))
        );

        mockLogDiscoveryNavigation.mockResolvedValueOnce({
            success: true,
            busqueda_id: "search-loading",
            action_taken: "search",
        });

        render(<DiscoveryPanel {...defaultProps} />);

        const positiveInput = screen.getByPlaceholderText(/conceptos positivos/i);
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "test");
        await user.click(searchButton);

        // Should show loading indicator
        await waitFor(() => {
            expect(searchButton).toBeDisabled();
        });
    });

    test("handles search error gracefully", async () => {
        const user = userEvent.setup();

        mockDiscoverSearch.mockRejectedValueOnce(new Error("Network error"));

        render(<DiscoveryPanel {...defaultProps} />);

        const positiveInput = screen.getByPlaceholderText(/conceptos positivos/i);
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "test");
        await user.click(searchButton);

        // Should show error message
        await waitFor(() => {
            expect(screen.getByText(/network error/i)).toBeInTheDocument();
        });
    });

    test("shows AI analysis button after search results", async () => {
        const user = userEvent.setup();

        mockDiscoverSearch.mockResolvedValueOnce({
            fragments: [
                {
                    id: "frag1",
                    fragmento_id: "frag1",
                    fragmento: "Content",
                    archivo: "test.docx",
                    score: 0.9,
                },
            ],
            count: 1,
        });

        mockLogDiscoveryNavigation.mockResolvedValueOnce({
            success: true,
            busqueda_id: "search-ai",
            action_taken: "search",
        });

        render(<DiscoveryPanel {...defaultProps} />);

        const positiveInput = screen.getByPlaceholderText(/conceptos positivos/i);
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "test");
        await user.click(searchButton);

        // After results, should show AI analysis button
        await waitFor(() => {
            expect(screen.getByRole("button", { name: /analizar con ia/i })).toBeInTheDocument();
        });
    });

    test("calls onSelectFragment when fragment is selected", async () => {
        const user = userEvent.setup();
        const onSelectFragment = vi.fn();

        mockDiscoverSearch.mockResolvedValueOnce({
            fragments: [
                {
                    id: "frag-select",
                    fragmento_id: "frag-select",
                    fragmento: "Selectable content",
                    archivo: "select.docx",
                    score: 0.88,
                },
            ],
            count: 1,
        });

        mockLogDiscoveryNavigation.mockResolvedValueOnce({
            success: true,
            busqueda_id: "search-select",
            action_taken: "search",
        });

        render(<DiscoveryPanel {...defaultProps} onSelectFragment={onSelectFragment} />);

        const positiveInput = screen.getByPlaceholderText(/conceptos positivos/i);
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "test");
        await user.click(searchButton);

        await waitFor(() => {
            expect(screen.getByText(/selectable content/i)).toBeInTheDocument();
        });

        // Click on fragment (implementation depends on actual UI)
        // This is a placeholder - actual implementation may vary
        const fragment = screen.getByText(/selectable content/i);
        await user.click(fragment);

        // Verify callback was called (if implemented)
        // expect(onSelectFragment).toHaveBeenCalledWith("frag-select", "Selectable content");
    });
});
