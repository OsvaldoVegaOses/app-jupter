import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { LoginPage } from "../LoginPage";

// Mock AuthContext
const mockLogin = vi.fn();

vi.mock("../../context/AuthContext", () => ({
    useAuth: () => ({
        login: mockLogin,
        logout: vi.fn(),
        user: null,
        loading: false,
    }),
}));


// Mock onSwitchToRegister callback
const mockOnSwitchToRegister = vi.fn();

beforeEach(() => {
    vi.clearAllMocks();
    mockLogin.mockClear();
    mockOnSwitchToRegister.mockClear();
});

describe("LoginPage", () => {
    test("renders login form correctly", () => {
        render(<LoginPage onSwitchToRegister={mockOnSwitchToRegister} />);

        expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/contraseña|password/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /ingresar/i })).toBeInTheDocument();
        expect(screen.getByText(/no tienes cuenta/i)).toBeInTheDocument();
    });

    test("renders header correctly", () => {
        render(<LoginPage onSwitchToRegister={mockOnSwitchToRegister} />);

        expect(screen.getByText(/QUALY Dashboard/i)).toBeInTheDocument();
        expect(screen.getByText(/iniciar sesión/i)).toBeInTheDocument();
    });

    test("validates email and password are required", async () => {
        const user = userEvent.setup();
        render(<LoginPage onSwitchToRegister={mockOnSwitchToRegister} />);

        const submitButton = screen.getByRole("button", { name: /ingresar/i });

        // Try to submit empty form
        await user.click(submitButton);

        // Should show validation error
        await waitFor(() => {
            expect(screen.getByText(/email y contraseña son requeridos/i)).toBeInTheDocument();
        });

        // Should not call login
        expect(mockLogin).not.toHaveBeenCalled();
    });

    test("shows error on invalid credentials", async () => {
        const user = userEvent.setup();

        // Mock login failure
        mockLogin.mockResolvedValueOnce(false);

        render(<LoginPage onSwitchToRegister={mockOnSwitchToRegister} />);

        const emailInput = screen.getByLabelText(/email/i);
        const passwordInput = screen.getByLabelText(/contraseña/i);
        const submitButton = screen.getByRole("button", { name: /ingresar/i });

        await user.type(emailInput, "test@example.com");
        await user.type(passwordInput, "wrongpassword");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockLogin).toHaveBeenCalledWith({
                email: "test@example.com",
                password: "wrongpassword",
            });
        });

        // Should show error message
        await waitFor(() => {
            expect(screen.getByText(/credenciales inválidas/i)).toBeInTheDocument();
        });
    });

    test("calls login on successful form submission", async () => {
        const user = userEvent.setup();

        // Mock successful login
        mockLogin.mockResolvedValueOnce(true);

        render(<LoginPage onSwitchToRegister={mockOnSwitchToRegister} />);

        const emailInput = screen.getByLabelText(/email/i);
        const passwordInput = screen.getByLabelText(/contraseña/i);
        const submitButton = screen.getByRole("button", { name: /ingresar/i });

        await user.type(emailInput, "test@example.com");
        await user.type(passwordInput, "correctpassword");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockLogin).toHaveBeenCalledWith({
                email: "test@example.com",
                password: "correctpassword",
            });
        });

        // Should not show error
        expect(screen.queryByText(/credenciales inválidas/i)).not.toBeInTheDocument();
    });

    test("navigates to register page", async () => {
        const user = userEvent.setup();
        render(<LoginPage onSwitchToRegister={mockOnSwitchToRegister} />);

        const registerButton = screen.getByRole("button", { name: /regístrate aquí/i });
        await user.click(registerButton);

        // Should call the callback
        await waitFor(() => {
            expect(mockOnSwitchToRegister).toHaveBeenCalled();
        });
    });

    test("disables inputs and button while loading", async () => {
        const user = userEvent.setup();

        // Mock slow login
        mockLogin.mockImplementationOnce(
            () => new Promise((resolve) => setTimeout(() => resolve(true), 100))
        );

        render(<LoginPage onSwitchToRegister={mockOnSwitchToRegister} />);

        const emailInput = screen.getByLabelText(/email/i);
        const passwordInput = screen.getByLabelText(/contraseña/i);
        const submitButton = screen.getByRole("button", { name: /ingresar/i });

        await user.type(emailInput, "test@example.com");
        await user.type(passwordInput, "password123");
        await user.click(submitButton);

        // Inputs and button should be disabled while loading
        await waitFor(() => {
            expect(emailInput).toBeDisabled();
            expect(passwordInput).toBeDisabled();
            expect(submitButton).toBeDisabled();
        });

        // Should show loading text
        expect(screen.getByText(/ingresando/i)).toBeInTheDocument();
    });

    test("trims email whitespace", async () => {
        const user = userEvent.setup();
        mockLogin.mockResolvedValueOnce(true);

        render(<LoginPage onSwitchToRegister={mockOnSwitchToRegister} />);

        const emailInput = screen.getByLabelText(/email/i);
        const passwordInput = screen.getByLabelText(/contraseña/i);
        const submitButton = screen.getByRole("button", { name: /ingresar/i });

        await user.type(emailInput, "  test@example.com  ");
        await user.type(passwordInput, "password");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockLogin).toHaveBeenCalledWith({
                email: "test@example.com", // Trimmed!
                password: "password",
            });
        });
    });
});
