/**
 * UserMenu.tsx — Dropdown showing the current user's role + logout button.
 *
 * V193 (R1): Surfaces the authentication state in the TopBar. Shows the
 * user's role (admin / engineer / viewer) and provides a logout action that
 * clears the session cookie and redirects to /login.
 */
import { LogOut, ShieldCheck, User } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/contexts/AuthContext";

const ROLE_LABELS: Record<string, string> = {
	admin: "Administrator",
	engineer: "Engineer",
	viewer: "Viewer (read-only)",
};

const ROLE_BADGE_COLORS: Record<string, string> = {
	admin: "bg-slate-500/15 text-slate-400 border-danger/30",
	engineer: "bg-primary/15 text-orange-300 border-primary/30",
	viewer: "bg-slate-500/15 text-foreground/90 border-border/30",
};

export function UserMenu() {
	const { role, logout, isAuthenticated } = useAuth();
	const navigate = useNavigate();

	if (!isAuthenticated) {
		return (
			<Button
				variant="outline"
				size="sm"
				onClick={() => navigate("/login")}
				className="border-border text-foreground/90 hover:bg-card"
			>
				Sign In
			</Button>
		);
	}

	const handleLogout = async () => {
		await logout();
		navigate("/login", { replace: true });
	};

	const roleLabel = role ? ROLE_LABELS[role] || role : "Unknown";
	const roleBadgeClass = role
		? ROLE_BADGE_COLORS[role] || ROLE_BADGE_COLORS.viewer
		: ROLE_BADGE_COLORS.viewer;

	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<Button
					variant="ghost"
					size="sm"
					className="gap-2 text-foreground/90 hover:bg-card"
					aria-label="User menu"
				>
					<User className="h-4 w-4" />
					<span className="hidden sm:inline">{roleLabel.split(" ")[0]}</span>
				</Button>
			</DropdownMenuTrigger>
			<DropdownMenuContent align="end" className="w-56">
				<DropdownMenuLabel className="flex items-center gap-2">
					<ShieldCheck className="h-4 w-4 text-primary" />
					<div className="flex flex-col">
						<span className="text-sm font-medium">Signed in</span>
						<span
							className={`text-xs px-2 py-0.5 rounded-full border inline-block w-fit mt-0.5 ${roleBadgeClass}`}
						>
							{roleLabel}
						</span>
					</div>
				</DropdownMenuLabel>
				<DropdownMenuSeparator />
				<DropdownMenuItem
					onClick={handleLogout}
					className="text-danger focus:text-slate-400 focus:bg-slate-500/10 cursor-pointer"
				>
					<LogOut className="h-4 w-4 mr-2" />
					Sign out
				</DropdownMenuItem>
			</DropdownMenuContent>
		</DropdownMenu>
	);
}
