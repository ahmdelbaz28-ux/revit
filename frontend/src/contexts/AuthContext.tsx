
/**
 * AuthContext.tsx — Global authentication state for the entire app.
 *
 * V193 (R1): Provides a single source of truth for "is the user logged in?"
 * via React Context. The RouteGuard component reads this to decide whether
 * to render the protected page or redirect to /login.
 *
 * Design:
 *   - On mount, calls GET /api/v1/auth/me (which uses the HttpOnly cookie)
 *   - If 200, user is authenticated; exposes { role } via context
 *   - If 401, user is not authenticated
 *   - Provides login(apiKey) and logout() actions that update state
 *   - Re-checks auth on window focus (so logout in another tab is detected)
 *
 * The cookie is HttpOnly so JS cannot read it directly. The only way to know
 * "am I authenticated?" is to ask the backend via /auth/me.
 */
import {
        createContext,
        useCallback,
        useContext,
        useEffect,
        useState,
        type ReactNode,
} from "react";
import { getCurrentUser, login as apiLogin, logout as apiLogout } from "@/services/api";
import { prefetchCsrfToken, invalidateCsrfToken } from "@/services/csrf";

interface AuthState {
        isAuthenticated: boolean;
        role: string | null;
        loading: boolean; // true during initial /auth/me check
        error: string | null;
}

interface AuthContextValue extends AuthState {
        login: (apiKey: string) => Promise<{ role: string }>;
        logout: () => Promise<void>;
        refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
        const [state, setState] = useState<AuthState>({
                isAuthenticated: false,
                role: null,
                loading: true, // initial check on mount
                error: null,
        });

        const refresh = useCallback(async () => {
                try {
                        const user = await getCurrentUser();
                        if (user) {
                                setState({
                                        isAuthenticated: true,
                                        role: user.role,
                                        loading: false,
                                        error: null,
                                });
                        } else {
                                setState({
                                        isAuthenticated: false,
                                        role: null,
                                        loading: false,
                                        error: null,
                                });
                        }
                } catch {
                        setState({
                                isAuthenticated: false,
                                role: null,
                                loading: false,
                                error: "Session check failed",
                        });
                }
        }, []);

        // Initial check on mount
        useEffect(() => {
                refresh();
        }, [refresh]);

        // Re-check on window focus (catches logout in another tab)
        useEffect(() => {
                const onFocus = () => {
                        // Only re-check if we think we're authenticated (avoid spamming
                        // /auth/me when not logged in — LoginPage handles that flow)
                        if (state.isAuthenticated) {
                                refresh();
                        }
                };
                globalThis.addEventListener("focus", onFocus);
                return () => globalThis.removeEventListener("focus", onFocus);
        }, [state.isAuthenticated, refresh]);

        const login = useCallback(
                async (apiKey: string) => {
                        const result = await apiLogin(apiKey);
                        setState({
                                isAuthenticated: true,
                                role: result.role,
                                loading: false,
                                error: null,
                        });
                        // V193 (R5): Prefetch the CSRF token so it's ready for the first
                        // mutation. Fire-and-forget — we don't block login on this.
                        void prefetchCsrfToken();
                        return result;
                },
                [],
        );

        const logout = useCallback(async () => {
                try {
                        await apiLogout();
                } catch {
                        // Best-effort — even if the server call fails, clear local state
                }
                // Clear any legacy sessionStorage key
                try {
                        sessionStorage.removeItem("fireai_settings");
                } catch {
                        // ignore
                }
                // V193 (R5): Invalidate the cached CSRF token on logout
                invalidateCsrfToken();
                setState({
                        isAuthenticated: false,
                        role: null,
                        loading: false,
                        error: null,
                });
        }, []);

        return (
                <AuthContext.Provider value={{ ...state, login, logout, refresh }}>
                        {children}
                </AuthContext.Provider>
        );
}

export function useAuth(): AuthContextValue {
        const ctx = useContext(AuthContext);
        if (!ctx) {
                throw new Error("useAuth must be used within an AuthProvider");
        }
        return ctx;
}
