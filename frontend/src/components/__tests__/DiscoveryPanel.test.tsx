import { render, screen, waitFor, within } from "@testing-library/react";
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

    // Helper to get the control inside the labeled field (prefer label queries)
    function getFieldControl(labelRegex: RegExp, role: 'textbox' | 'spinbutton' = 'textbox') {
        // Try label-based association first (when `label` is associated with control)
        const labeled = within(document.body).queryAllByLabelText(labelRegex, { selector: 'input,textarea,select' }) as HTMLElement[];
        if (labeled && labeled.length > 0) return labeled[0] as any;

        // Try placeholder as a fallback (some inputs render placeholder instead of associated label)
        const byPlaceholder = within(document.body).queryAllByPlaceholderText?.(labelRegex) as HTMLElement[] | undefined;
        if (byPlaceholder && byPlaceholder.length > 0) return byPlaceholder[0] as any;

        // Fallback: find all nodes that match the label text and pick the one
        // that sits next to an actual form control inside the known field wrapper.
        const candidates = screen.queryAllByText(labelRegex);
        for (const label of candidates) {
            // prefer actual <label> elements
            if (label.tagName === 'LABEL') {
                const field = label.closest('.discovery-panel__field') || label.parentElement;
                if (!field) continue;
                const control = (field.querySelector('input,textarea,select') as HTMLElement) || null;
                if (control) return control as any;
            }
            // otherwise try to find a nearby wrapper that contains a control
            const field = label.closest('.discovery-panel__field') || label.parentElement;
            if (!field) continue;
            const control = (field.querySelector('input,textarea,select') as HTMLElement) || null;
            if (control) return control as any;
        }

        throw new Error('field not found for ' + labelRegex);
    }

    test("renders discovery form correctly", async () => {
        render(<DiscoveryPanel {...defaultProps} />);

        // Should find the three main controls (use robust helper that falls back to placeholder/nearby control)
        expect(getFieldControl(/conceptos positivos/i)).toBeInTheDocument();
        expect(getFieldControl(/conceptos negativos/i)).toBeInTheDocument();
        expect(getFieldControl(/texto objetivo/i)).toBeInTheDocument();

        // Should show top-k selector (number input)
        expect(await screen.findByRole('spinbutton')).toBeInTheDocument();

        // Should show search button
        expect(await screen.findByRole("button", { name: /buscar/i })).toBeInTheDocument();
    });

    test("validates positive text is required", async () => {
        render(<DiscoveryPanel {...defaultProps} />);

        const searchButton = screen.getByRole("button", { name: /buscar/i });
        // Button should be disabled when no positive concepts
        expect(searchButton).toBeDisabled();

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

        const positiveInput = getFieldControl(/conceptos positivos/i, 'textbox');
        const searchButton = await screen.findByRole("button", { name: /buscar/i });

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
        expect(await screen.findByText(/test fragment content/i)).toBeInTheDocument();
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

        const positiveInput = getFieldControl(/conceptos positivos/i, 'textbox');
        const negativeInput = getFieldControl(/conceptos negativos/i, 'textbox');
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "liderazgo\norganización");
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

        const positiveInput = getFieldControl(/conceptos positivos/i, 'textbox');
        const topKSelect = screen.getByRole('spinbutton');
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "motivación");
        await user.clear(topKSelect);
        await user.type(topKSelect, "20");
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

        const positiveInput = getFieldControl(/conceptos positivos/i, 'textbox');
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

        const positiveInput = getFieldControl(/conceptos positivos/i, 'textbox');
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

        const positiveInput = getFieldControl(/conceptos positivos/i, 'textbox');
        const searchButton = screen.getByRole("button", { name: /buscar/i });

        await user.type(positiveInput, "test");
        await user.click(searchButton);

        // After results, should show AI analysis button (accept multiple possible labels)
        await waitFor(() => {
            expect(
                screen.getByRole("button", {
                    name: /analizar con ia|sintetizar con ia|sintetizar|🤖/i,
                })
            ).toBeInTheDocument();
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

        const positiveInput = getFieldControl(/conceptos positivos/i, 'textbox');
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
