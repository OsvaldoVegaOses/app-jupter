import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { AuthPage } from "../AuthPage";

// Mock useAuth hook
const mockLogin = vi.fn();
const mockRegister = vi.fn();

vi.mock("../../context/AuthContext", () => ({
    useAuth: () => ({
        login: mockLogin,
        register: mockRegister,
        logout: vi.fn(),
        user: null,
        isLoading: false,
        isAuthenticated: false,
    }),
}));

beforeEach(() => {
    vi.clearAllMocks();
    mockLogin.mockClear();
    mockRegister.mockClear();
});

describe("AuthPage", () => {
    test("renders with login form by default", () => {
        render(<AuthPage />);

        // Should show header
        expect(screen.getByText(/sistema de análisis cualitativo/i)).toBeInTheDocument();
        expect(screen.getByText(/inicia sesión para continuar/i)).toBeInTheDocument();

        // Should show login form
        expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /iniciar sesión/i })).toBeInTheDocument();

        // Should not show register-specific fields
        expect(screen.queryByLabelText(/nombre completo/i)).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/confirmar password/i)).not.toBeInTheDocument();
    });

    test("shows registration prompt in login mode", () => {
        render(<AuthPage />);

        expect(screen.getByText(/¿no tienes cuenta\?/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /regístrate aquí/i })).toBeInTheDocument();
    });

    test("switches to register form when clicking register link", async () => {
        const user = userEvent.setup();
        render(<AuthPage />);

        // Click register button
        const registerButton = screen.getByRole("button", { name: /regístrate aquí/i });
        await user.click(registerButton);

        // Should show register form
        await waitFor(() => {
            expect(screen.getByText(/crea una cuenta nueva/i)).toBeInTheDocument();
            expect(screen.getByLabelText(/nombre completo/i)).toBeInTheDocument();
            expect(screen.getByLabelText(/confirmar password/i)).toBeInTheDocument();
            expect(screen.getByRole("button", { name: /crear cuenta/i })).toBeInTheDocument();
        });

        // Should show login prompt
        expect(screen.getByText(/¿ya tienes cuenta\?/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /inicia sesión/i })).toBeInTheDocument();
    });

    test("switches back to login form from register", async () => {
        const user = userEvent.setup();
        render(<AuthPage />);

        // Go to register
        const registerButton = screen.getByRole("button", { name: /regístrate aquí/i });
        await user.click(registerButton);

        await waitFor(() => {
            expect(screen.getByLabelText(/confirmar password/i)).toBeInTheDocument();
        });

        // Click login button
        const loginButton = screen.getByRole("button", { name: /^inicia sesión$/i });
        await user.click(loginButton);

        // Should be back to login form
        await waitFor(() => {
            expect(screen.getByText(/inicia sesión para continuar/i)).toBeInTheDocument();
            expect(screen.getByRole("button", { name: /iniciar sesión/i })).toBeInTheDocument();
        });

        // Register fields should be gone
        expect(screen.queryByLabelText(/nombre completo/i)).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/confirmar password/i)).not.toBeInTheDocument();
    });

    test("shows password hint in register mode", async () => {
        const user = userEvent.setup();
        render(<AuthPage />);

        // Switch to register
        const registerButton = screen.getByRole("button", { name: /regístrate aquí/i });
        await user.click(registerButton);

        await waitFor(() => {
            expect(screen.getByText(/mínimo 8 caracteres/i)).toBeInTheDocument();
        });
    });

    test("validates form and shows errors", async () => {
            const user = userEvent.setup();
            const { container } = render(<AuthPage />);

            // Try to submit without filling form — use form submit to trigger client validation path
            const form = container.querySelector('form');
            await user.click(screen.getByRole("button", { name: /iniciar sesión/i }));
            // Fire submit event in case native validation prevented onSubmit
            if (form) form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));

            // Should show validation error (tolerant to rendering timing)
            await waitFor(() => {
                expect(screen.queryByText(/email es requerido/i) || screen.queryByText(/email required/i) || screen.queryByText(/⚠️/)).toBeTruthy();
            });
    });

    test("calls login on successful login submission", async () => {
        const user = userEvent.setup();
        mockLogin.mockResolvedValueOnce(undefined);

        render(<AuthPage />);

        const emailInput = screen.getByLabelText(/email/i);
        const passwordInput = screen.getByLabelText(/password/i);
        const submitButton = screen.getByRole("button", { name: /iniciar sesión/i });

        await user.type(emailInput, "test@example.com");
        await user.type(passwordInput, "password123");
        await user.click(submitButton);

        await waitFor(() => {
            expect(mockLogin).toHaveBeenCalledWith({
                email: "test@example.com",
                password: "password123",
            });
        });
    });

    test("prevents submission during loading", async () => {
        const user = userEvent.setup();

        // Mock slow login
        mockLogin.mockImplementationOnce(
            () => new Promise(resolve => setTimeout(resolve, 100))
        );

        render(<AuthPage />);

        const emailInput = screen.getByLabelText(/email/i);
        const passwordInput = screen.getByLabelText(/password/i);
        const submitButton = screen.getByRole("button", { name: /iniciar sesión/i });

        await user.type(emailInput, "test@example.com");
        await user.type(passwordInput, "password123");
        await user.click(submitButton);

        // Button should be disabled
        await waitFor(() => {
            expect(submitButton).toBeDisabled();
        });

        // Should show loading spinner
        expect(screen.getByText(/⏳/)).toBeInTheDocument();
    });
});
