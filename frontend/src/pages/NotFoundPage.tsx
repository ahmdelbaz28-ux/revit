/**
 * NotFoundPage.tsx — 404 page for unknown routes.
 *
 * V201 (UI Polish): Restored a branded, helpful 404 page with a clear visual
 * hierarchy and obvious next-step CTAs. Uses the BAZSPARK brand gradient
 * to maintain visual consistency with the login page.
 */
import { Button } from "@/components/ui/button";
import { Home, Compass, ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";

export function NotFoundPage() {
	const navigate = useNavigate();
	return (
		<div className="min-h-[60vh] flex items-center justify-center p-4">
			<div className="text-center max-w-lg">
				<div className="inline-flex items-center justify-center h-20 w-20 rounded-md bg-gradient-to-br from-primary to-primary mb-6 shadow-lg shadow-primary/20">
					<Compass className="h-10 w-10 text-white" />
				</div>
				<h1 className="text-7xl font-bold text-primary bg-clip-text text-transparent mb-3">
					404
				</h1>
				<h2 className="text-xl font-semibold text-foreground mb-3">
					Page not found
				</h2>
				<p className="text-sm text-muted-foreground mb-8 leading-relaxed">
					The page you're looking for doesn't exist or has been moved.
					If you reached this page from a bookmark, the link may be outdated.
					Use the buttons below to get back on track.
				</p>
				<div className="flex flex-wrap gap-3 justify-center">
					<Button
						onClick={() => navigate("/dashboard")}
						className="bg-gradient-to-r from-primary to-primary hover:from-orange-600 hover:to-red-700 text-white shadow-lg shadow-orange-500/20"
					>
						<Home className="h-4 w-4 mr-2" />
						Back to Dashboard
					</Button>
					<Button
						variant="outline"
						onClick={() => navigate(-1)}
						className="border-border text-foreground/90 hover:bg-card"
					>
						<ArrowLeft className="h-4 w-4 mr-2" />
						Go Back
					</Button>
				</div>
			</div>
		</div>
	);
}
