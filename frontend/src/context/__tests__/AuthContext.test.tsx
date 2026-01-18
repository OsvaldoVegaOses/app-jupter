import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { AuthProvider, useAuth } from "../../context/AuthContext";
import { useContext } from "react";

// Test component that uses the auth context
function TestComponent() {
    const { user, isAuthenticated, login, register, logout, isLoading } = useAuth();

    return (
        <div>
            <div data-testid="loading">{isLoading ? "Loading" : "Ready"}</div>
            <div data-testid="authenticated">{isAuthenticated ? "Yes" : "No"}</div>
            <div data-testid="user-email">{user?.email || "No user"}</div>
            <div data-testid="user-name">{user?.name || "No name"}</div>
            <button onClick={() => login({ email: "test@example.com", password: "pass" })}>Login</button>
            <button onClick={() => register({ email: "new@example.com", password: "pass" })}>Register</button>
            <button onClick={logout}>Logout</button>
        </div>
    );
}

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock localStorage
const localStorageMock = (() => {
    let store: Record<string, string> = {};

    return {
        getItem: (key: string) => store[key] || null,
        setItem: (key: string, value: string) => {
            store[key] = value;
        },
        removeItem: (key: string) => {
            delete store[key];
        },
        clear: () => {
            store = {};
        },
    };
})();

Object.defineProperty(window, 'localStorage', {
    value: localStorageMock,
});

beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
});

describe("AuthContext", () => {
    test("initializes with no user", () => {
        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        expect(screen.getByTestId("authenticated")).toHaveTextContent("No");
        expect(screen.getByTestId("user-email")).toHaveTextContent("No user");
    });

    test("loads user from localStorage", async () => {
        // Set stored auth data
        localStorageMock.setItem("access_token", "stored-token-123");
        localStorageMock.setItem("qualy-auth-user", JSON.stringify({
            id: "user-1",
            email: "stored@example.com",
            name: "Stored User",
            org_id: "org-1"
        }));

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByTestId("authenticated")).toHaveTextContent("Yes");
            expect(screen.getByTestId("user-email")).toHaveTextContent("stored@example.com");
            expect(screen.getByTestId("user-name")).toHaveTextContent("Stored User");
        });
    });

    test("successful login stores token and user", async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                access_token: "new-token-456",
                user: {
                    id: "user-2",
                    email: "test@example.com",
                    name: "Test User",
                    org_id: "org-2"
                }
            })
        });

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        const loginButton = screen.getByText("Login");
        loginButton.click();

        await waitFor(() => {
            expect(screen.getByTestId("authenticated")).toHaveTextContent("Yes");
            expect(screen.getByTestId("user-email")).toHaveTextContent("test@example.com");
        });

        // Should store in localStorage
        expect(localStorageMock.getItem("access_token")).toBe("new-token-456");
        expect(localStorageMock.getItem("qualy-auth-user")).toContain("test@example.com");
    });

    test("failed login shows error and doesn't store data", async () => {
        mockFetch.mockResolvedValueOnce({
            ok: false,
            status: 401,
            json: async () => ({ detail: "Invalid credentials" })
        });

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        const loginButton = screen.getByText("Login");
        loginButton.click();

        await waitFor(() => {
            expect(screen.getByTestId("authenticated")).toHaveTextContent("No");
        });

        expect(localStorageMock.getItem("access_token")).toBeNull();
    });

    test("successful registration", async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                access_token: "reg-token-789",
                user: {
                    id: "user-3",
                    email: "new@example.com",
                    name: null,
                    org_id: "org-3"
                }
            })
        });

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        const registerButton = screen.getByText("Register");
        registerButton.click();

        await waitFor(() => {
            expect(screen.getByTestId("authenticated")).toHaveTextContent("Yes");
            expect(screen.getByTestId("user-email")).toHaveTextContent("new@example.com");
        });
    });

    test("logout clears user and token", async () => {
        // Start with authenticated user
        localStorageMock.setItem("access_token", "token-to-clear");
        localStorageMock.setItem("qualy-auth-user", JSON.stringify({
            id: "user-4",
            email: "logout@example.com",
            org_id: "org-4"
        }));

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        await waitFor(() => {
            expect(screen.getByTestId("authenticated")).toHaveTextContent("Yes");
        });

        const logoutButton = screen.getByText("Logout");
        logoutButton.click();

        await waitFor(() => {
            expect(screen.getByTestId("authenticated")).toHaveTextContent("No");
            expect(screen.getByTestId("user-email")).toHaveTextContent("No user");
        });

        expect(localStorageMock.getItem("access_token")).toBeNull();
        expect(localStorageMock.getItem("qualy-auth-user")).toBeNull();
    });

    test("handles corrupted localStorage data", () => {
        localStorageMock.setItem("access_token", "token");
        localStorageMock.setItem("qualy-auth-user", "invalid-json{");

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        // Should clear invalid data and not crash
        expect(screen.getByTestId("authenticated")).toHaveTextContent("No");
        expect(localStorageMock.getItem("access_token")).toBeNull();
    });

    test("handles network errors during login", async () => {
        mockFetch.mockRejectedValueOnce(new Error("Network error"));

        render(
            <AuthProvider>
                <TestComponent />
            </AuthProvider>
        );

        const loginButton = screen.getByText("Login");
        loginButton.click();

        await waitFor(() => {
            expect(screen.getByTestId("authenticated")).toHaveTextContent("No");
        });
    });
});
