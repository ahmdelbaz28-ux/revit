/**
 * RouteGuard.tsx — Protects routes that require authentication.
 *
 * V193 (R1): Wraps any page that needs a logged-in user. If the user is not
 * authenticated, redirects to /login?from=<original-path> so the user
 * returns to their intended page after login.
 *
 * Usage in App.tsx:
 *   <Route
 *     path="/dashboard"
 *     element={
 *       <RouteGuard>
 *         <DashboardPage />
 *       </RouteGuard>
 *     }
 *   />
 *
 * The guard shows a minimal spinner while the AuthContext is performing its
 * initial /auth/me check (state.loading === true). Once the check completes,
 * it either renders the children (authenticated) or redirects (not).
 */
import { Loader2 } from "lucide-react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import type { ReactNode } from "react";

interface RouteGuardProps {
	children: ReactNode;
}

export function RouteGuard({ children }: RouteGuardProps) {  // NOSONAR - typescript:S6759
	const { isAuthenticated, loading } = useAuth();
	const location = useLocation();

	if (loading) {
		return (
			<div className="min-h-screen flex items-center justify-center bg-slate-950">
				<div className="flex flex-col items-center gap-3">
					<Loader2 className="h-8 w-8 animate-spin text-orange-500" />
					<p className="text-sm text-slate-400">Verifying session...</p>
				</div>
			</div>
		);
	}

	if (!isAuthenticated) {
		// Preserve the original path so we can return after login
		const from = encodeURIComponent(location.pathname + location.search);
		return <Navigate to={`/login?from=${from}`} replace />;
	}

	return <>{children}</>;
}
