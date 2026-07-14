/**
 * LoginPage.tsx — BAZSPARK Login (Redesigned with OpenCode Style Aesthetics)
 *
 * Design Concept:
 *   - Split screen layout (60% interactive dashboard preview, 40% premium glassmorphic login form)
 *   - Cyberpunk slate/void background with neon cyan and blue ambient glows
 *   - Interactive blueprint/CAD visual mockup panel showing FACP loop metrics, compliance passes, and live telemetry
 *   - High-end typography and fully-functional login card with custom focus glows and micro-animations
 */

import {
	Activity,
	AlertCircle,
	CheckCircle2,
	Cpu,
	Eye,
	EyeOff,
	FileText,
	KeyRound,
	Layers,
	Loader2,
	ShieldCheck,
	Terminal,
} from "lucide-react";
import { lazy, Suspense, useEffect, useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { BazSparkLogo, BazSparkWordmark } from "@/components/auth/BazSparkLogo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";

// Lazy-load the heavy background SVG to maintain high FCP/LCP scores
const EngineeringBackground = lazy(() =>
	import("@/components/auth/EngineeringBackground").then((m) => ({
		default: m.EngineeringBackground,
	})),
);

const APP_VERSION = "v1.55.0";

export function LoginPage() {
	const [searchParams] = useSearchParams();
	const { isAuthenticated, loading: ctxLoading, login } = useAuth();

	const [apiKey, setApiKey] = useState("");
	const [showKey, setShowKey] = useState(false);
	const [remember, setRemember] = useState(false);
	const [submitting, setSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	// Defer background loading until idle
	const [showBackground, setShowBackground] = useState(false);
	useEffect(() => {
		const hasRIC = typeof window !== "undefined" && "requestIdleCallback" in window;
		let handle: number;
		if (hasRIC) {
			const w = window as unknown as {
				requestIdleCallback: (cb: () => void) => number;
				cancelIdleCallback: (h: number) => void;
			};
			handle = w.requestIdleCallback(() => setShowBackground(true));
			return () => w.cancelIdleCallback(handle);
		}
		handle = window.setTimeout(() => setShowBackground(true), 200);
		return () => window.clearTimeout(handle);
	}, []);

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
					// sessionStorage might be unavailable
				}
			}
			await login(apiKey.trim());
			setSubmitting(false);
		} catch (err) {
			const msg = err instanceof Error ? err.message : "Login failed";
			if (msg.includes("429") || msg.includes("Too many")) {
				setError("Too many failed attempts. Please wait a few minutes.");
			} else if (msg.includes("401") || msg.includes("Invalid")) {
				setError("Invalid API key. Please verify and try again.");
			} else if (msg.includes("Failed to fetch") || msg.includes("Network")) {
				setError("Unable to reach the server. Check your connection.");
			} else {
				setError(msg);
			}
			setSubmitting(false);
		}
	};

	return (
		<div className="min-h-screen w-full flex flex-col md:flex-row bg-[#030712] text-[#f8fafc] font-sans selection:bg-cyan-500/30 overflow-hidden relative" role="main" aria-label="BAZSPARK Login">
			
			{/* Custom embedded animations for OpenCode styling */}
			<style dangerouslySetInnerHTML={{ __html: `
				@keyframes dash {
					to {
						stroke-dashoffset: -40;
					}
				}
				.animate-dash {
					stroke-dasharray: 4, 4;
					animation: dash 8s linear infinite;
				}
				.glow-effect:hover {
					box-shadow: 0 0 25px rgba(34, 211, 238, 0.15);
					border-color: rgba(34, 211, 238, 0.3);
				}
			` }} />

			{/* Background ambient lighting glows */}
			<div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-cyan-500/5 blur-[120px] pointer-events-none z-0" />
			<div className="absolute bottom-[-10%] right-[20%] w-[50%] h-[50%] rounded-full bg-blue-500/5 blur-[120px] pointer-events-none z-0" />

			{/* ═══════════════════════════════════════════════════════════════
				LEFT PANEL: Interactive Software Mockup & Brand Showcase
			   ═════════════════════════════════════════════════════════════════ */}
			<div className="hidden md:flex md:w-[55%] lg:w-[60%] relative overflow-hidden bg-gradient-to-tr from-[#050b14] via-[#081225] to-[#030712] border-r border-slate-900/60 p-12 lg:p-20 flex-col justify-between z-10">
				
				{/* Backing decorative 3D CAD/AI background */}
				<div className="absolute inset-0 z-0 opacity-[0.35] pointer-events-none">
					<Suspense fallback={null}>
						{showBackground && <EngineeringBackground />}
					</Suspense>
				</div>

				{/* Top Branding Section */}
				<div className="relative z-10 flex items-center gap-3">
					<div className="h-8 w-[2px] bg-cyan-400 rounded-full" />
					<div>
						<h4 className="text-[11px] font-bold uppercase tracking-[0.25em] text-cyan-400">PROJECT BAZSPARK</h4>
						<p className="text-[9px] text-slate-500 uppercase tracking-widest mt-0.5">FireAI Digital Twin Core</p>
					</div>
				</div>

				{/* Middle Typography & Live CAD Blueprint Mockup Container */}
				<div className="relative z-10 my-auto max-w-2xl space-y-8">
					<div className="space-y-4">
						<h1 className="text-4xl lg:text-5xl font-extrabold tracking-tight leading-[1.1] text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-100 to-slate-400">
							The Safety-Critical <br />
							<span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">Fire Alarm Engineering</span> <br />
							Digital Twin.
						</h1>
						<p className="text-slate-400 text-sm max-w-lg leading-relaxed">
							Design, analyze, and simulate FACP loop networks. Verify loop capacitance, NFPA 72 compliance guidelines, and trigger AI-assisted self-healing topologies in real-time.
						</p>
					</div>

					{/* Live System Mockup Container (Carbon Console design) */}
					<div className="border border-slate-800/80 bg-slate-950/70 rounded-xl shadow-2xl p-5 relative overflow-hidden backdrop-blur-md glow-effect transition-all duration-500">
						{/* Header of mockup */}
						<div className="flex items-center justify-between border-b border-slate-900 pb-3 mb-4">
							<div className="flex items-center gap-1.5">
								<span className="h-2.5 w-2.5 rounded-full bg-red-500/80" />
								<span className="h-2.5 w-2.5 rounded-full bg-yellow-500/80" />
								<span className="h-2.5 w-2.5 rounded-full bg-green-500/80" />
								<span className="text-[10px] font-mono text-slate-500 ml-2">FACP_CORE_INTEGRATOR // loop_01</span>
							</div>
							<div className="flex items-center gap-2">
								<span className="flex h-2 w-2 relative">
									<span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
									<span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
								</span>
								<span className="text-[9px] font-mono text-emerald-400 font-semibold uppercase tracking-wider">LIVE TELEMETRY</span>
							</div>
						</div>

						{/* Body: A grid of stats and a mini CAD drawing */}
						<div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
							{/* Stats list */}
							<div className="space-y-2.5 font-mono text-xs">
								<div className="flex justify-between items-center bg-slate-900/40 p-2.5 rounded border border-slate-900/60">
									<span className="text-slate-500 flex items-center gap-1.5">
										<CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
										NFPA 72 Compliance:
									</span>
									<span className="text-emerald-400 font-bold">PASS</span>
								</div>
								<div className="flex justify-between items-center bg-slate-900/40 p-2.5 rounded border border-slate-900/60">
									<span className="text-slate-500 flex items-center gap-1.5">
										<Layers className="h-3.5 w-3.5 text-cyan-400" />
										Loop Capacitance:
									</span>
									<span className="text-cyan-400 font-bold">1.84 µF</span>
								</div>
								<div className="flex justify-between items-center bg-slate-900/40 p-2.5 rounded border border-slate-900/60">
									<span className="text-slate-500 flex items-center gap-1.5">
										<Activity className="h-3.5 w-3.5 text-slate-400" />
										Active Sensors:
									</span>
									<span className="text-slate-200">1,482 Nodes</span>
								</div>
								<div className="flex justify-between items-center bg-slate-900/40 p-2.5 rounded border border-slate-900/60">
									<span className="text-slate-500 flex items-center gap-1.5">
										<Cpu className="h-3.5 w-3.5 text-indigo-400" />
										Self-Healing Status:
									</span>
									<span className="text-indigo-400 font-semibold">MONITORED</span>
								</div>
							</div>

							{/* Micro Floor Plan Preview */}
							<div className="border border-slate-900 bg-slate-950/80 rounded-lg p-3 relative h-36 flex items-center justify-center overflow-hidden">
								{/* CAD blueprint style grid lines */}
								<div className="absolute inset-0 bg-[linear-gradient(rgba(34,211,238,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.02)_1px,transparent_1px)] bg-[size:10px_10px]" />
								
								{/* Animated floor plan paths */}
								<svg className="w-full h-full text-slate-800 stroke-1 stroke-cyan-500/10 fill-none" viewBox="0 0 100 100">
									<rect x="10" y="10" width="80" height="80" rx="4" stroke="rgba(34,211,238,0.1)" />
									<line x1="10" y1="50" x2="90" y2="50" stroke="rgba(255,255,255,0.03)" />
									<line x1="50" y1="10" x2="50" y2="90" stroke="rgba(255,255,255,0.03)" />
									
									{/* Loop cable lines */}
									<path d="M 25 25 L 75 25 L 75 75 L 25 75 Z" stroke="#3b82f6" strokeWidth="1.2" className="animate-dash" />
									
									{/* Blinking detectors */}
									<circle cx="25" cy="25" r="2.5" fill="#22d3ee" className="animate-pulse" />
									<circle cx="75" cy="25" r="2.5" fill="#22d3ee" className="animate-pulse delay-70" />
									<circle cx="75" cy="75" r="3" fill="#34d399" className="animate-ping" />
									<circle cx="75" cy="75" r="2" fill="#34d399" />
									<circle cx="25" cy="75" r="2.5" fill="#22d3ee" className="animate-pulse delay-150" />
								</svg>
								
								{/* Floating label overlay */}
								<div className="absolute bottom-2 right-2 bg-slate-900/90 border border-slate-800/80 px-2 py-0.5 rounded text-[8px] font-mono text-cyan-400">
									AutoCAD / Revit Link OK
								</div>
							</div>
						</div>
					</div>
				</div>

				{/* Bottom Certifications & Info */}
				<div className="relative z-10 flex flex-wrap items-center gap-6 text-[10px] text-slate-500 font-mono">
					<span className="flex items-center gap-1.5">
						<span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
						NFPA 72 COMPLIANT
					</span>
					<span className="flex items-center gap-1.5">
						<span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
						EN 54 CERTIFIED
					</span>
					<span className="flex items-center gap-1.5">
						<span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
						SAFETY-CRITICAL SYSTEM
					</span>
				</div>
			</div>

			{/* ═══════════════════════════════════════════════════════════════
				RIGHT PANEL: Premium Login Card & Form
			   ═════════════════════════════════════════════════════════════════ */}
			<div className="w-full md:w-[45%] lg:w-[40%] flex items-center justify-center p-8 bg-[#05070f] border-t md:border-t-0 md:border-l border-slate-900/80 relative z-10">
				
				<div className="w-full max-w-[380px] flex flex-col py-8">
					{/* Logo & Header */}
					<div className="flex flex-col items-center mb-8 text-center">
						<BazSparkLogo size={76} animated className="drop-shadow-[0_0_25px_rgba(59,130,246,0.3)]" />
						<div className="mt-4">
							<BazSparkWordmark size="lg" />
						</div>
						<p className="text-[10px] mt-2 uppercase tracking-[0.25em] text-cyan-400 font-bold">
							Digital Twin Workspace
						</p>
						<p className="text-[11px] mt-1 text-slate-500 max-w-[280px]">
							Safety-Critical Fire Alarm Engineering Platform
						</p>
					</div>

					{/* Glassmorphism Login Card */}
					<div className="rounded-2xl p-7 border border-white/[0.05] bg-white/[0.02] backdrop-blur-md shadow-[0_20px_50px_rgba(0,0,0,0.6)]">
						<div className="mb-6">
							<h2 className="text-xl font-bold text-white tracking-tight">Welcome back</h2>
							<p className="text-slate-400 text-xs mt-1">Please enter your API Key to authenticate session.</p>
						</div>

						<form onSubmit={handleSubmit} className="space-y-5">
							{error && (
								<Alert variant="destructive" className="bg-red-500/10 border-red-500/20 text-red-400">
									<AlertCircle className="h-4 w-4 text-red-400" />
									<AlertTitle>Sign-in failed</AlertTitle>
									<AlertDescription>{error}</AlertDescription>
								</Alert>
							)}

							{/* API Key input field */}
							<div className="space-y-2">
								<Label htmlFor="api-key" className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
									API Key
								</Label>
								<div className="relative">
									<KeyRound className="absolute left-3.5 top-1/2 -translate-y-1/2 h-[16px] w-[16px] text-slate-500" />
									<Input
										id="api-key"
										type={showKey ? "text" : "password"}
										autoComplete="off"
										autoFocus
										placeholder="Enter your API key"
										value={apiKey}
										onChange={(e) => setApiKey(e.target.value)}
										disabled={submitting}
										className="pl-10 pr-10 font-mono text-sm bg-slate-950/80 border-slate-800 text-white rounded-lg h-10 transition-all duration-300 focus:border-cyan-400/80 focus:ring-1 focus:ring-cyan-400/20 focus:shadow-[0_0_15px_rgba(34,211,238,0.15)]"
									/>
									<button
										type="button"
										onClick={() => setShowKey(!showKey)}
										className="absolute right-3.5 top-1/2 -translate-y-1/2 p-1 text-slate-500 transition-colors hover:text-cyan-400"
										aria-label={showKey ? "Hide API key" : "Show API key"}
										tabIndex={-1}
									>
										{showKey ? (
											<EyeOff className="h-[16px] w-[16px]" />
										) : (
											<Eye className="h-[16px] w-[16px]" />
										)}
									</button>
								</div>
							</div>

							{/* Remember me */}
							<div className="flex items-center gap-2.5">
								<Checkbox
									id="remember"
									checked={remember}
									onCheckedChange={(v) => setRemember(v === true)}
									disabled={submitting}
									className="border-slate-800 data-[state=checked]:bg-cyan-500 data-[state=checked]:border-cyan-500"
								/>
								<Label htmlFor="remember" className="text-xs cursor-pointer select-none text-slate-400 hover:text-slate-300 transition-colors">
									Remember me
								</Label>
							</div>

							{/* Submit button */}
							<Button
								type="submit"
								className="w-full h-10 text-xs font-bold rounded-lg transition-all duration-300 bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white shadow-[0_4px_20px_rgba(37,99,235,0.25)] hover:shadow-[0_4px_25px_rgba(34,211,238,0.35)] disabled:opacity-50 disabled:pointer-events-none"
								disabled={submitting || !apiKey.trim()}
							>
								{submitting ? (
									<>
										<Loader2 className="h-4 w-4 animate-spin mr-2" />
										Signing in...
									</>
								) : (
									<>
										<ShieldCheck className="h-4 w-4 mr-2" />
										Sign In
									</>
								)}
							</Button>
						</form>
					</div>

					{/* Secured Status Badge Footer */}
					<div className="flex items-center justify-center gap-1.5 mt-8 text-[10px] text-slate-600 font-mono tracking-wider">
						<ShieldCheck className="h-3.5 w-3.5 text-cyan-400" />
						<span>SECURED PORTAL • {APP_VERSION}</span>
					</div>
				</div>

			</div>
		</div>
	);
}
