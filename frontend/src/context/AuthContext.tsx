/**
 * @fileoverview Contexto de autenticación para multi-tenancy.
 *
 * Provee estado global de autenticación y funciones para:
 * - Login con email/password
 * - Registro de nuevos usuarios
 * - Logout
 * - Persistencia de sesión en localStorage
 *
 * @example
 * import { useAuth } from './context/AuthContext';
 * const { user, login, logout, isAuthenticated } = useAuth();
 */

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

// =============================================================================
// Types
// =============================================================================

export interface AuthUser {
    id: string;
    email: string;
    name?: string | null;
    org_id: string;
    role: string;  // admin, analyst, viewer
    roles?: string[];
}

interface AuthState {
    user: AuthUser | null;
    token: string | null;
    isAuthenticated: boolean;
    isLoading: boolean;
}

interface LoginCredentials {
    email: string;
    password: string;
}

interface RegisterData {
    email: string;
    password: string;
    name?: string;
    organization_name?: string;
    organization_id?: string;
}

interface AuthContextType extends AuthState {
    login: (credentials: LoginCredentials) => Promise<boolean>;
    register: (data: RegisterData) => Promise<{ success: boolean; error?: string }>;
    logout: () => void;
}

// =============================================================================
// Constants
// =============================================================================

const AUTH_STORAGE_KEY = "access_token";
const USER_STORAGE_KEY = "qualy-auth-user";
// IMPORTANTE: VITE_BACKEND_URL es para el proxy de Vite (server-side), NO para el navegador.
// API_BASE puede estar vacío (usa proxy) o ser una URL absoluta (llamada directa al backend).
const API_BASE = import.meta.env.VITE_API_BASE || "";

// =============================================================================
// Context
// =============================================================================

const AuthContext = createContext<AuthContextType | null>(null);

// =============================================================================
// Provider Component
// =============================================================================

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [state, setState] = useState<AuthState>({
        user: null,
        token: null,
        isAuthenticated: false,
        isLoading: true,
    });

    // Load session from localStorage on mount
    useEffect(() => {
        const storedToken = localStorage.getItem(AUTH_STORAGE_KEY);
        const storedUser = localStorage.getItem(USER_STORAGE_KEY);

        if (storedToken && storedUser) {
            try {
                const user = JSON.parse(storedUser) as AuthUser;
                if (!user.roles || !user.roles.length) {
                    user.roles = user.role ? [user.role] : [];
                }
                setState({
                    user,
                    token: storedToken,
                    isAuthenticated: true,
                    isLoading: false,
                });
            } catch {
                // Invalid stored data, clear it
                localStorage.removeItem(AUTH_STORAGE_KEY);
                localStorage.removeItem(USER_STORAGE_KEY);
                setState((prev) => ({ ...prev, isLoading: false }));
            }
        } else {
            setState((prev) => ({ ...prev, isLoading: false }));
        }
    }, []);

    const login = useCallback(async (credentials: LoginCredentials): Promise<boolean> => {
        try {
            // Usar nuevo endpoint /api/auth/login
            const response = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    email: credentials.email,
                    password: credentials.password,
                }),
            });

            if (!response.ok) {
                let errorBody: unknown = null;
                try {
                    errorBody = await response.json();
                } catch {
                    try {
                        errorBody = await response.text();
                    } catch {
                        errorBody = null;
                    }
                }
                console.error("Login error response", {
                    status: response.status,
                    statusText: response.statusText,
                    url: response.url,
                    body: errorBody,
                });
                return false;
            }

            const data = await response.json();
            const user: AuthUser = {
                id: data.user.id,
                email: data.user.email,
                name: data.user.full_name,
                org_id: data.user.organization_id,
                role: data.user.role || 'viewer',
                roles: data.user.roles && Array.isArray(data.user.roles) ? data.user.roles : [data.user.role || 'viewer'],
            };

            // Save to localStorage
            localStorage.setItem(AUTH_STORAGE_KEY, data.access_token);
            localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
            // Guardar refresh token para renovación
            if (data.refresh_token) {
                localStorage.setItem("refresh_token", data.refresh_token);
            }

            setState({
                user,
                token: data.access_token,
                isAuthenticated: true,
                isLoading: false,
            });

            return true;
        } catch (error) {
            console.error("Login error:", error);
            return false;
        }
    }, []);

    const register = useCallback(
        async (data: RegisterData): Promise<{ success: boolean; error?: string }> => {
            try {
                // Usar nuevo endpoint /api/auth/register
                const response = await fetch(`${API_BASE}/api/auth/register`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        email: data.email,
                        password: data.password,
                        full_name: data.name,
                        organization_id: data.organization_id || "default_org",
                    }),
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    return {
                        success: false,
                        error: errorData.detail || `Error ${response.status}`,
                    };
                }

                // El registro ya devuelve tokens, no necesita auto-login
                const responseData = await response.json();
                const user: AuthUser = {
                    id: responseData.user.id,
                    email: responseData.user.email,
                    name: responseData.user.full_name,
                    org_id: responseData.user.organization_id,
                    role: responseData.user.role || 'viewer',
                    roles: responseData.user.roles && Array.isArray(responseData.user.roles)
                        ? responseData.user.roles
                        : [responseData.user.role || 'viewer'],
                };

                localStorage.setItem(AUTH_STORAGE_KEY, responseData.access_token);
                localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
                if (responseData.refresh_token) {
                    localStorage.setItem("refresh_token", responseData.refresh_token);
                }

                setState({
                    user,
                    token: responseData.access_token,
                    isAuthenticated: true,
                    isLoading: false,
                });

                return { success: true };
            } catch (error) {
                console.error("Register error:", error);
                return {
                    success: false,
                    error: error instanceof Error ? error.message : "Error de conexión",
                };
            }
        },
        []
    );

    const logout = useCallback(() => {
        localStorage.removeItem(AUTH_STORAGE_KEY);
        localStorage.removeItem(USER_STORAGE_KEY);
        setState({
            user: null,
            token: null,
            isAuthenticated: false,
            isLoading: false,
        });
    }, []);

    const value: AuthContextType = {
        ...state,
        login,
        register,
        logout,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// =============================================================================
// Hook
// =============================================================================

export function useAuth(): AuthContextType {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
}

// =============================================================================
// Helper: Get token for API calls
// =============================================================================

export function getAuthToken(): string | null {
    return localStorage.getItem(AUTH_STORAGE_KEY);
}
