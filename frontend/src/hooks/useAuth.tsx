/**
 * Hook de Autenticación
 * 
 * Gestiona el estado de autenticación del usuario:
 * - Login/Logout
 * - Registro
 * - Refresh automático de tokens
 * - Persistencia en localStorage
 */

import { useState, useEffect, useCallback, createContext, useContext, ReactNode } from 'react';

// =============================================================================
// TIPOS
// =============================================================================

export interface User {
    id: string;
    email: string;
    full_name?: string;
    organization_id: string;
    /**
     * Wrapper de autenticación (compatibilidad).
     *
     * Unifica el flujo con el AuthContext principal para evitar sesiones duplicadas.
     * Mantiene una API de login/register que lanza errores (usada por AuthPage).
     */

    import { AuthProvider as CoreAuthProvider, useAuth as useCoreAuth } from "../context/AuthContext";

    export interface LoginCredentials {
        email: string;
        password: string;
    }

    export interface RegisterData {
        email: string;
        password: string;
        full_name?: string;
        organization_id?: string;
    }

    export function AuthProvider({ children }: { children: React.ReactNode }) {
        return <CoreAuthProvider>{children}</CoreAuthProvider>;
    }

    export function useAuth() {
        const { login, register, logout, ...state } = useCoreAuth();

        const loginStrict = async (credentials: LoginCredentials) => {
            const ok = await login(credentials);
            if (!ok) {
                throw new Error("Error de autenticación");
            }
        };

        const registerStrict = async (data: RegisterData) => {
            const result = await register({
                email: data.email,
                password: data.password,
                name: data.full_name,
                organization_id: data.organization_id,
            });
            if (!result.success) {
                throw new Error(result.error || "Error de registro");
            }
        };

        return {
            ...state,
            login: loginStrict,
            register: registerStrict,
            logout,
        };
    }

    export default useAuth;
    return context;
