/**
 * @fileoverview Página de registro con formulario para crear cuenta.
 */

import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import "./LoginPage.css"; // Reutiliza los mismos estilos

interface RegisterPageProps {
    onSwitchToLogin: () => void;
}

export function RegisterPage({ onSwitchToLogin }: RegisterPageProps) {
    const { register } = useAuth();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [name, setName] = useState("");
    const [organizationName, setOrganizationName] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (!email.trim() || !password) {
            setError("Email y contraseña son requeridos");
            return;
        }

        if (password !== confirmPassword) {
            setError("Las contraseñas no coinciden");
            return;
        }

        if (password.length < 4) {
            setError("La contraseña debe tener al menos 4 caracteres");
            return;
        }

        setLoading(true);
        const result = await register({
            email: email.trim(),
            password,
            name: name.trim() || undefined,
            organization_name: organizationName.trim() || undefined,
        });
        setLoading(false);

        if (!result.success) {
            setError(result.error || "Error al registrar");
        }
    };

    return (
        <div className="login-page">
            <div className="login-card login-card--register">
                <header className="login-header">
                    <h1>🔬 QUALY Dashboard</h1>
                    <p>Análisis Cualitativo con IA</p>
                </header>

                <form className="login-form" onSubmit={handleSubmit}>
                    <h2>Crear Cuenta</h2>

                    {error && <div className="login-error">{error}</div>}

                    <div className="login-field">
                        <label htmlFor="name">Nombre (opcional)</label>
                        <input
                            id="name"
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Tu nombre"
                            disabled={loading}
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="reg-email">Email</label>
                        <input
                            id="reg-email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="tu@email.com"
                            autoComplete="email"
                            disabled={loading}
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="reg-password">Contraseña</label>
                        <input
                            id="reg-password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="••••••••"
                            autoComplete="new-password"
                            disabled={loading}
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="confirm-password">Confirmar Contraseña</label>
                        <input
                            id="confirm-password"
                            type="password"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            placeholder="••••••••"
                            autoComplete="new-password"
                            disabled={loading}
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="org-name">Organización (opcional)</label>
                        <input
                            id="org-name"
                            type="text"
                            value={organizationName}
                            onChange={(e) => setOrganizationName(e.target.value)}
                            placeholder="Nombre de tu organización"
                            disabled={loading}
                        />
                        <small className="login-hint">
                            Si no especificas, se creará automáticamente
                        </small>
                    </div>

                    <button type="submit" className="login-submit" disabled={loading}>
                        {loading ? "Registrando..." : "Crear Cuenta"}
                    </button>
                </form>

                <footer className="login-footer">
                    <p>
                        ¿Ya tienes cuenta?{" "}
                        <button type="button" className="login-link" onClick={onSwitchToLogin}>
                            Inicia sesión
                        </button>
                    </p>
                </footer>
            </div>
        </div>
    );
}
