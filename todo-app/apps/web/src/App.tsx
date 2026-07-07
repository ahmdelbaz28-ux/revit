import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./contexts/AuthContext";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Signup from "./pages/Signup";

function ProtectedRoute({ children }: { children: React.ReactNode }) {  // NOSONAR - typescript:S6759
	const { user } = useAuth();
	if (!user) return <Navigate to="/login" replace />;
	return <>{children}</>;
}

function PublicRoute({ children }: { children: React.ReactNode }) {  // NOSONAR - typescript:S6759
	const { user } = useAuth();
	if (user) return <Navigate to="/" replace />;
	return <>{children}</>;
}

export default function App() {
	return (
		<Routes>
			<Route
				path="/login"
				element={
					<PublicRoute>
						<Login />
					</PublicRoute>
				}
			/>
			<Route
				path="/signup"
				element={
					<PublicRoute>
						<Signup />
					</PublicRoute>
				}
			/>
			<Route
				path="/"
				element={
					<ProtectedRoute>
						<Dashboard />
					</ProtectedRoute>
				}
			/>
		</Routes>
	);
}
