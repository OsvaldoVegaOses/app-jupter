/**
 * Wrapper de autenticación (compatibilidad).
 *
 * Este módulo existe para evitar imports rotos en código legacy.
 * La fuente de verdad es `../context/AuthContext`.
 */

export { AuthProvider, useAuth } from "../context/AuthContext";
export type { AuthUser as User } from "../context/AuthContext";
