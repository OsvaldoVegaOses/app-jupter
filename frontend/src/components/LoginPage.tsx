/**
 * @fileoverview Página de login con formulario y link a registro.
 */

import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import "./LoginPage.css";

interface LoginPageProps {
    onSwitchToRegister: () => void;
}

export function LoginPage({ onSwitchToRegister }: LoginPageProps) {
    const { login } = useAuth();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (!email.trim() || !password) {
            setError("Email y contraseña son requeridos");
            return;
        }

        setLoading(true);
        const success = await login({ email: email.trim(), password });
        setLoading(false);

        if (!success) {
            setError("Credenciales inválidas");
        }
    };

    return (
        <div className="login-page">
            <div className="login-card">
                <header className="login-header">
                    <h1>🔬 QUALY Dashboard</h1>
                    <p>Análisis Cualitativo con IA</p>
                </header>

                <form className="login-form" onSubmit={handleSubmit}>
                    <h2>Iniciar Sesión</h2>

                    {error && <div className="login-error">{error}</div>}

                    <div className="login-field">
                        <label htmlFor="email">Email</label>
                        <input
                            id="email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="tu@email.com"
                            autoComplete="email"
                            disabled={loading}
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="password">Contraseña</label>
                        <input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="••••••••"
                            autoComplete="current-password"
                            disabled={loading}
                        />
                    </div>

                    <button type="submit" className="login-submit" disabled={loading}>
                        {loading ? "Ingresando..." : "Ingresar"}
                    </button>
                </form>

                <footer className="login-footer">
                    <p>
                        ¿No tienes cuenta?{" "}
                        <button type="button" className="login-link" onClick={onSwitchToRegister}>
                            Regístrate aquí
                        </button>
                    </p>
                </footer>
            </div>
        </div>
    );
}
