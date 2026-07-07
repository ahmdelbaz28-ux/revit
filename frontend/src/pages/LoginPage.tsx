/**
 * LoginPage.tsx — API-key based login with session cookie.
 *
 * V201 (UI Overhaul): Restored a polished, branded login experience.
 *   - Two-column layout on desktop: brand panel + form panel
 *   - Subtle gradient + fire-themed decorative elements
 *   - Clear visual hierarchy with feature highlights
 *   - RTL-aware (mirrors layout when document.dir === "rtl")
 *   - Mobile-first: stacks vertically on small screens
 *
 * Why API key (not username/password)?
 *   The backend auth model is API-key based (backend/routers/auth.py).
 *   API keys are issued by an admin and stored as bcrypt hashes. The login
 *   endpoint accepts {api_key: "..."} and returns {role: "admin|engineer|viewer"}.
 *   There is no username/password table.
 *
 * UX:
 *   - Single password-style input (the API key)
 *   - Show/Hide toggle (API keys are sensitive)
 *   - Inline error messages for 401 / 429 / network errors
 *   - "Remember this key on this device" checkbox (stores in sessionStorage
 *     as a convenience for dev — the cookie is the real auth token)
 *   - Redirect to /dashboard on success
 *   - Redirect to original ?from= URL if present
 */
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardFooter,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
	Eye,
	EyeOff,
	KeyRound,
	Loader2,
	LogIn,
	AlertCircle,
	Flame,
	ShieldCheck,
	Zap,
	FileCheck,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { useSearchParams, Navigate } from "react-router-dom";
import { login } from "@/services/api";
import { useAuth } from "@/contexts/AuthContext";

const APP_VERSION = "v1.55.0";

const FEATURES: Array<{
	icon: typeof ShieldCheck;
	title: string;
	description: string;
}> = [
	{
		icon: ShieldCheck,
		title: "Safety-Critical Compliance",
		description: "NFPA 72 + AHJ ready, with full audit trails.",
	},
	{
		icon: Zap,
		title: "Real-Time Engineering",
		description: "Live device placement, voltage drop, and conduit fill.",
	},
	{
		icon: FileCheck,
		title: "Submittal-Grade Reports",
		description: "Generate compliance documents in one click.",
	},
];

export function LoginPage() {
	const [searchParams] = useSearchParams();
	const { isAuthenticated, loading: ctxLoading } = useAuth();

	const [apiKey, setApiKey] = useState("");
	const [showKey, setShowKey] = useState(false);
	const [remember, setRemember] = useState(false);
	const [submitting, setSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// If already authenticated, redirect to dashboard (or ?from=)
	if (!ctxLoading && isAuthenticated) {
		const from = searchParams.get("from") || "/dashboard";
		return <Navigate to={from} replace />;
	}

	const handleSubmit = async (e: FormEvent) => {
		e.preventDefault();
		setError(null);

		if (!apiKey.trim()) {
			setError("Please enter your API key.");
			return;
		}

		setSubmitting(true);
		try {
			if (remember) {
				try {
					sessionStorage.setItem(
						"fireai_settings",
						JSON.stringify({ apiKey: apiKey.trim() }),
					);
				} catch {
					// sessionStorage might be unavailable (private mode) — ignore
				}
			}

			await login(apiKey.trim());
			setSubmitting(false);
		} catch (err) {
			const msg = err instanceof Error ? err.message : "Login failed";
			if (msg.includes("429") || msg.includes("Too many")) {
				setError(
					"Too many failed login attempts. Please wait 5 minutes and try again.",
				);
			} else if (msg.includes("401") || msg.includes("Invalid")) {
				setError("Invalid API key. Please check and try again.");
			} else if (msg.includes("Failed to fetch") || msg.includes("Network")) {
				setError(
					"Cannot reach the server. Please check your network connection and try again.",
				);
			} else {
				setError(msg);
			}
			setSubmitting(false);
		}
	};

	return (
		<div className="min-h-screen w-full flex items-stretch justify-center bg-slate-950 relative overflow-hidden">
			{/* Decorative background: subtle radial gradient + grid pattern */}
			<div
				className="absolute inset-0 pointer-events-none opacity-60"
				style={{
					background:
						"radial-gradient(ellipse at 20% 30%, rgba(249, 115, 22, 0.15), transparent 60%), radial-gradient(ellipse at 80% 70%, rgba(220, 38, 38, 0.10), transparent 60%)",
				}}
			/>
			<div
				className="absolute inset-0 pointer-events-none opacity-[0.04]"
				style={{
					backgroundImage:
						"linear-gradient(rgba(148, 163, 184, 1) 1px, transparent 1px), linear-gradient(90deg, rgba(148, 163, 184, 1) 1px, transparent 1px)",
					backgroundSize: "32px 32px",
				}}
			/>

			{/* Two-column container */}
			<div className="relative w-full max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-0 lg:gap-8 p-4 sm:p-6 lg:p-8 items-center">
				{/* LEFT: Brand / marketing panel (hidden on small screens) */}
				<div className="hidden lg:flex flex-col justify-center pr-8">
					<div className="flex items-center gap-3 mb-8">
						<div className="h-14 w-14 rounded-xl bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center shadow-lg shadow-orange-500/30">
							<Flame className="h-8 w-8 text-white" />
						</div>
						<div>
							<h1 className="text-3xl font-bold text-slate-50 tracking-tight">
								BAZSPARK
							</h1>
							<p className="text-xs text-slate-400 mt-0.5">
								Safety-Critical Fire Alarm Engineering Platform
							</p>
						</div>
					</div>

					<h2 className="text-4xl font-bold text-slate-50 leading-tight mb-4">
						Design, validate, and
						<br />
						<span className="bg-gradient-to-r from-orange-400 to-red-500 bg-clip-text text-transparent">
							certify fire alarm systems
						</span>
						<br />
						with engineering precision.
					</h2>

					<p className="text-slate-400 text-base leading-relaxed mb-10 max-w-md">
						BAZSPARK is the digital twin platform for fire protection engineers —
						combining deterministic code compliance with real-time collaboration
						across BIM, CAD, and Revit workflows.
					</p>

					<div className="space-y-4 max-w-md">
						{FEATURES.map((feature) => (
							<div key={feature.title} className="flex items-start gap-3">
								<div className="h-9 w-9 rounded-lg bg-slate-800/80 border border-slate-700/50 flex items-center justify-center shrink-0">
									<feature.icon className="h-5 w-5 text-orange-400" />
								</div>
								<div>
									<h3 className="text-sm font-semibold text-slate-100">
										{feature.title}
									</h3>
									<p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
										{feature.description}
									</p>
								</div>
							</div>
						))}
					</div>
				</div>

				{/* RIGHT: Login form panel */}
				<div className="w-full max-w-md mx-auto lg:ml-auto">
					{/* Mobile brand header (visible only on small screens) */}
					<div className="lg:hidden text-center mb-6">
						<div className="inline-flex items-center gap-2 mb-2">
							<div className="h-10 w-10 rounded-lg bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center shadow-lg shadow-orange-500/30">
								<Flame className="h-6 w-6 text-white" />
							</div>
							<span className="text-2xl font-bold text-slate-50">BAZSPARK</span>
						</div>
						<p className="text-sm text-slate-400">
							Safety-Critical Fire Alarm Engineering Platform
						</p>
					</div>

					<Card className="bg-slate-900/80 backdrop-blur-sm border-slate-700/70 shadow-2xl shadow-black/40">
						<CardHeader className="space-y-1">
							<CardTitle className="text-slate-50 flex items-center gap-2 text-xl">
								<LogIn className="h-5 w-5 text-orange-500" />
								Sign In
							</CardTitle>
							<CardDescription className="text-slate-400">
								Enter your FireAI API key to access the platform. Your key is
								exchanged for a secure session cookie and never stored on disk.
							</CardDescription>
						</CardHeader>

						<form onSubmit={handleSubmit}>
							<CardContent className="space-y-4">
								{error && (
									<Alert variant="destructive">
										<AlertCircle className="h-4 w-4" />
										<AlertTitle>Authentication failed</AlertTitle>
										<AlertDescription>{error}</AlertDescription>
									</Alert>
								)}

								<div className="space-y-2">
									<Label htmlFor="api-key" className="text-slate-200">
										API Key
									</Label>
									<div className="relative">
										<KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
										<Input
											id="api-key"
											type={showKey ? "text" : "password"}
											autoComplete="off"
											autoFocus
											placeholder="Paste your FireAI API key here"
											value={apiKey}
											onChange={(e) => setApiKey(e.target.value)}
											disabled={submitting}
											className="bg-slate-800/80 border-slate-600 text-slate-100 pl-10 pr-10 font-mono focus-visible:ring-orange-500/50 focus-visible:border-orange-500/50"
											aria-describedby="api-key-help"
										/>
										<button
											type="button"
											onClick={() => setShowKey(!showKey)}
											className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 transition-colors p-1 rounded"
											aria-label={showKey ? "Hide API key" : "Show API key"}
											tabIndex={-1}
										>
											{showKey ? (
												<EyeOff className="h-4 w-4" />
											) : (
												<Eye className="h-4 w-4" />
											)}
										</button>
									</div>
									<p id="api-key-help" className="text-xs text-slate-500">
										Your API key is set by the FIREAI_API_KEY environment variable
										on the backend at first startup.
									</p>
								</div>

								<div className="flex items-center space-x-2">
									<Checkbox
										id="remember"
										checked={remember}
										onCheckedChange={(v) => setRemember(v === true)}
										disabled={submitting}
									/>
									<Label
										htmlFor="remember"
										className="text-sm text-slate-300 cursor-pointer select-none"
									>
										Remember key on this device (sessionStorage)
									</Label>
								</div>
							</CardContent>

							<CardFooter className="flex flex-col gap-3">
								<Button
									type="submit"
									className="w-full bg-gradient-to-r from-orange-500 to-red-600 hover:from-orange-600 hover:to-red-700 text-white shadow-lg shadow-orange-500/30 transition-all"
									disabled={submitting || !apiKey.trim()}
								>
									{submitting ? (
										<>
											<Loader2 className="h-4 w-4 mr-2 animate-spin" />
											Signing in...
										</>
									) : (
										<>
											<LogIn className="h-4 w-4 mr-2" />
											Sign In
										</>
									)}
								</Button>
								<p className="text-xs text-slate-500 text-center leading-relaxed">
									By signing in, you agree to use this safety-critical system
									responsibly per NFPA 72 and local AHJ requirements.
								</p>
							</CardFooter>
						</form>
					</Card>

					<p className="text-center text-xs text-slate-600 mt-6">
						BAZSPARK {APP_VERSION} · FireAI Digital Twin · © 2026
					</p>
				</div>
			</div>
		</div>
	);
}
