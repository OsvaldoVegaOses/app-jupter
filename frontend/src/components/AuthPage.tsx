/**
 * Página de Autenticación
 * 
 * Componente que muestra formularios de Login y Registro
 * con validación de formularios y feedback de errores.
 */

import { useState, FormEvent } from 'react';
import { useAuth } from '../context/AuthContext';
import './AuthPage.css';

interface AuthPageProps {
    onSuccess?: () => void;
}

export function AuthPage({ onSuccess }: AuthPageProps) {
    const [mode, setMode] = useState<'login' | 'register'>('login');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Form state
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [fullName, setFullName] = useState('');

    const { login, register } = useAuth();

    const clearForm = () => {
        setEmail('');
        setPassword('');
        setConfirmPassword('');
        setFullName('');
        setError(null);
    };

    const handleModeSwitch = () => {
        setMode(mode === 'login' ? 'register' : 'login');
        clearForm();
    };

    const validateForm = (): string | null => {
        if (!email.trim()) return 'Email es requerido';
        if (!password) return 'Password es requerido';

        if (mode === 'register') {
            if (password.length < 8) return 'Password debe tener al menos 8 caracteres';
            if (!/[A-Z]/.test(password)) return 'Password debe contener al menos una mayúscula';
            if (!/[a-z]/.test(password)) return 'Password debe contener al menos una minúscula';
            if (!/\d/.test(password)) return 'Password debe contener al menos un número';
            if (!/[@$!%*?&#]/.test(password)) return 'Password debe contener al menos un carácter especial (@$!%*?&#)';
            if (password !== confirmPassword) return 'Los passwords no coinciden';
        }

        return null;
    };

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setError(null);

        const validationError = validateForm();
        if (validationError) {
            setError(validationError);
            return;
        }

        setIsLoading(true);

        try {
            if (mode === 'login') {
                await login({ email, password });
            } else {
                await register({
                    email,
                    password,
                    name: fullName || undefined,
                });
            }
            onSuccess?.();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Error de autenticación');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="auth-page">
            <div className="auth-container">
                <div className="auth-header">
                    <div className="auth-logo">🔬</div>
                    <h1>Sistema de Análisis Cualitativo</h1>
                    <p className="auth-subtitle">
                        {mode === 'login'
                            ? 'Inicia sesión para continuar'
                            : 'Crea una cuenta nueva'}
                    </p>
                </div>

                <form onSubmit={handleSubmit} className="auth-form">
                    {error && (
                        <div className="auth-error">
                            <span className="error-icon">⚠️</span>
                            {error}
                        </div>
                    )}

                    {mode === 'register' && (
                        <div className="form-group">
                            <label htmlFor="fullName">Nombre Completo</label>
                            <input
                                id="fullName"
                                type="text"
                                value={fullName}
                                onChange={(e) => setFullName(e.target.value)}
                                placeholder="Tu nombre completo"
                                disabled={isLoading}
                            />
                        </div>
                    )}

                    <div className="form-group">
                        <label htmlFor="email">Email</label>
                        <input
                            id="email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="tu@email.com"
                            required
                            disabled={isLoading}
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="password">Password</label>
                        <input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="••••••••"
                            required
                            disabled={isLoading}
                        />
                        {mode === 'register' && (
                            <small className="password-hint">
                                Mínimo 8 caracteres, incluir mayúscula, número y carácter especial
                            </small>
                        )}
                    </div>

                    {mode === 'register' && (
                        <div className="form-group">
                            <label htmlFor="confirmPassword">Confirmar Password</label>
                            <input
                                id="confirmPassword"
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                placeholder="••••••••"
                                required
                                disabled={isLoading}
                            />
                        </div>
                    )}

                    <button
                        type="submit"
                        className="auth-submit-btn"
                        disabled={isLoading}
                    >
                        {isLoading ? (
                            <span className="loading-spinner">⏳</span>
                        ) : (
                            mode === 'login' ? 'Iniciar Sesión' : 'Crear Cuenta'
                        )}
                    </button>
                </form>

                <div className="auth-footer">
                    <p>
                        {mode === 'login' ? (
                            <>
                                ¿No tienes cuenta?{' '}
                                <button
                                    type="button"
                                    className="link-btn"
                                    onClick={handleModeSwitch}
                                >
                                    Regístrate aquí
                                </button>
                            </>
                        ) : (
                            <>
                                ¿Ya tienes cuenta?{' '}
                                <button
                                    type="button"
                                    className="link-btn"
                                    onClick={handleModeSwitch}
                                >
                                    Inicia sesión
                                </button>
                            </>
                        )}
                    </p>
                </div>
            </div>
        </div>
    );
}

export default AuthPage;
