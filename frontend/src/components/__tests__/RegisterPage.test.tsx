import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { RegisterPage } from "../RegisterPage";

// Mock AuthContext
const mockRegister = vi.fn();

vi.mock("../../context/AuthContext", () => ({
    useAuth: () => ({
        register: mockRegister,
        login: vi.fn(),
        logout: vi.fn(),
        user: null,
        loading: false,
    }),
}));

// Mock onSwitchToLogin callback
const mockOnSwitchToLogin = vi.fn();

beforeEach(() => {
    vi.clearAllMocks();
    mockRegister.mockClear();
    mockOnSwitchToLogin.mockClear();
});

describe("RegisterPage", () => {
    test("renders registration form correctly", () => {
        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        expect(screen.getByLabelText(/nombre.*opcional/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/^contraseña$/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/confirmar contraseña/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/organización.*opcional/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /crear cuenta/i })).toBeInTheDocument();
    });

    test("renders header correctly", () => {
        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        expect(screen.getByText(/QUALY Dashboard/i)).toBeInTheDocument();
        // Use getByRole to specifically target the h2 heading, not the button
        expect(screen.getByRole("heading", { name: /crear cuenta/i, level: 2 })).toBeInTheDocument();
    });


    test("validates email and password are required", async () => {
        const user = userEvent.setup();
        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        const submitButton = screen.getByRole("button", { name: /crear cuenta/i });

        // Try to submit empty form
        await user.click(submitButton);

        // Should show validation error
        await waitFor(() => {
            expect(screen.getByText(/email y contraseña son requeridos/i)).toBeInTheDocument();
        });

        // Should not call register
        expect(mockRegister).not.toHaveBeenCalled();
    });

    test("validates passwords must match", async () => {
        const user = userEvent.setup();
        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        const emailInput = screen.getByLabelText(/^email$/i);
        const passwordInput = screen.getByLabelText(/^contraseña$/i);
        const confirmPasswordInput = screen.getByLabelText(/confirmar contraseña/i);
        const submitButton = screen.getByRole("button", { name: /crear cuenta/i });

        await user.type(emailInput, "test@example.com");
        await user.type(passwordInput, "password123");
        await user.type(confirmPasswordInput, "different123");
        await user.click(submitButton);

        // Should show password mismatch error
        await waitFor(() => {
            expect(screen.getByText(/las contraseñas no coinciden/i)).toBeInTheDocument();
        });

        // Should not call register
        expect(mockRegister).not.toHaveBeenCalled();
    });

    test("validates password minimum length", async () => {
        const user = userEvent.setup();
        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        const emailInput = screen.getByLabelText(/^email$/i);
        const passwordInput = screen.getByLabelText(/^contraseña$/i);
        const confirmPasswordInput = screen.getByLabelText(/confirmar contraseña/i);
        const submitButton = screen.getByRole("button", { name: /crear cuenta/i });

        await user.type(emailInput, "test@example.com");
        await user.type(passwordInput, "123"); // Too short
        await user.type(confirmPasswordInput, "123");
        await user.click(submitButton);

        // Should show password length error
        await waitFor(() => {
            expect(screen.getByText(/la contraseña debe tener al menos 4 caracteres/i)).toBeInTheDocument();
        });

        // Should not call register
        expect(mockRegister).not.toHaveBeenCalled();
    });

    test("shows error on registration failure", async () => {
        const user = userEvent.setup();

        // Mock registration failure
        mockRegister.mockResolvedValueOnce({
            success: false,
            error: "Email ya existe",
        });

        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        const emailInput = screen.getByLabelText(/^email$/i);
        const passwordInput = screen.getByLabelText(/^contraseña$/i);
        const confirmPasswordInput = screen.getByLabelText(/confirmar contraseña/i);
        const submitButton = screen.getByRole("button", { name: /crear cuenta/i });

        await user.type(emailInput, "existing@example.com");
        await user.type(passwordInput, "password123");
        await user.type(confirmPasswordInput, "password123");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockRegister).toHaveBeenCalledWith({
                email: "existing@example.com",
                password: "password123",
                name: undefined,
                organization_name: undefined,
            });
        });

        // Should show error message
        await waitFor(() => {
            expect(screen.getByText(/email ya existe/i)).toBeInTheDocument();
        });
    });

    test("calls register on successful form submission", async () => {
        const user = userEvent.setup();

        // Mock successful registration
        mockRegister.mockResolvedValueOnce({ success: true });

        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        const nameInput = screen.getByLabelText(/nombre.*opcional/i);
        const emailInput = screen.getByLabelText(/^email$/i);
        const passwordInput = screen.getByLabelText(/^contraseña$/i);
        const confirmPasswordInput = screen.getByLabelText(/confirmar contraseña/i);
        const orgInput = screen.getByLabelText(/organización.*opcional/i);
        const submitButton = screen.getByRole("button", { name: /crear cuenta/i });

        await user.type(nameInput, "Test User");
        await user.type(emailInput, "new@example.com");
        await user.type(passwordInput, "password123");
        await user.type(confirmPasswordInput, "password123");
        await user.type(orgInput, "Test Org");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockRegister).toHaveBeenCalledWith({
                email: "new@example.com",
                password: "password123",
                name: "Test User",
                organization_name: "Test Org",
            });
        });

        // Should not show error
        expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
    });

    test("calls register with minimal data (no optional fields)", async () => {
        const user = userEvent.setup();

        // Mock successful registration
        mockRegister.mockResolvedValueOnce({ success: true });

        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        const emailInput = screen.getByLabelText(/^email$/i);
        const passwordInput = screen.getByLabelText(/^contraseña$/i);
        const confirmPasswordInput = screen.getByLabelText(/confirmar contraseña/i);
        const submitButton = screen.getByRole("button", { name: /crear cuenta/i });

        await user.type(emailInput, "minimal@example.com");
        await user.type(passwordInput, "pass1234");
        await user.type(confirmPasswordInput, "pass1234");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockRegister).toHaveBeenCalledWith({
                email: "minimal@example.com",
                password: "pass1234",
                name: undefined,
                organization_name: undefined,
            });
        });
    });

    test("navigates to login page", async () => {
        const user = userEvent.setup();
        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        const loginButton = screen.getByRole("button", { name: /inicia sesión/i });
        await user.click(loginButton);

        // Should call the callback
        await waitFor(() => {
            expect(mockOnSwitchToLogin).toHaveBeenCalled();
        });
    });

    test("disables inputs and button while loading", async () => {
        const user = userEvent.setup();

        // Mock slow registration
        mockRegister.mockImplementationOnce(
            () => new Promise((resolve) => setTimeout(() => resolve({ success: true }), 100))
        );

        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        const nameInput = screen.getByLabelText(/nombre.*opcional/i);
        const emailInput = screen.getByLabelText(/^email$/i);
        const passwordInput = screen.getByLabelText(/^contraseña$/i);
        const confirmPasswordInput = screen.getByLabelText(/confirmar contraseña/i);
        const orgInput = screen.getByLabelText(/organización.*opcional/i);
        const submitButton = screen.getByRole("button", { name: /crear cuenta/i });

        await user.type(emailInput, "test@example.com");
        await user.type(passwordInput, "password123");
        await user.type(confirmPasswordInput, "password123");
        await user.click(submitButton);

        // All inputs and button should be disabled while loading
        await waitFor(() => {
            expect(nameInput).toBeDisabled();
            expect(emailInput).toBeDisabled();
            expect(passwordInput).toBeDisabled();
            expect(confirmPasswordInput).toBeDisabled();
            expect(orgInput).toBeDisabled();
            expect(submitButton).toBeDisabled();
        });

        // Should show loading text
        expect(screen.getByText(/registrando/i)).toBeInTheDocument();
    });

    test("trims email and optional fields whitespace", async () => {
        const user = userEvent.setup();
        mockRegister.mockResolvedValueOnce({ success: true });

        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        const nameInput = screen.getByLabelText(/nombre.*opcional/i);
        const emailInput = screen.getByLabelText(/^email$/i);
        const passwordInput = screen.getByLabelText(/^contraseña$/i);
        const confirmPasswordInput = screen.getByLabelText(/confirmar contraseña/i);
        const orgInput = screen.getByLabelText(/organización.*opcional/i);
        const submitButton = screen.getByRole("button", { name: /crear cuenta/i });

        await user.type(nameInput, "  John Doe  ");
        await user.type(emailInput, "  test@example.com  ");
        await user.type(passwordInput, "password");
        await user.type(confirmPasswordInput, "password");
        await user.type(orgInput, "  My Org  ");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockRegister).toHaveBeenCalledWith({
                email: "test@example.com", // Trimmed!
                password: "password",
                name: "John Doe", // Trimmed!
                organization_name: "My Org", // Trimmed!
            });
        });
    });

    test("shows hint for organization field", () => {
        render(<RegisterPage onSwitchToLogin={mockOnSwitchToLogin} />);

        expect(screen.getByText(/si no especificas, se creará automáticamente/i)).toBeInTheDocument();
    });
});
