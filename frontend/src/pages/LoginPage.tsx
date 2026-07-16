/**
 * LoginPage.tsx — BAZSPARK Login (Redesigned to match image 1 exactly)
 *
 * Design Concept:
 *   - 50/50 Split layout (Left: Product Showcase and Brand Details; Right: System Access Sign-In Card)
 *   - Dynamic 3D perspective grid animation in the background scrolling forward
 *   - Coral-red flame branding and solid coral-red submit button
 *   - Fully functional with original API authentication, key visibility toggle, and remember-me state
 */

import {
	AlertCircle,
	Brain,
	Compass,
	Eye,
	EyeOff,
	KeyRound,
	Loader2,
	Settings,
	ShieldCheck,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { BazSparkLogo, BazSparkWordmark } from "@/components/auth/BazSparkLogo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";

export function LoginPage() {
	const [searchParams] = useSearchParams();
	const { isAuthenticated, loading: ctxLoading, login } = useAuth();

	const [apiKey, setApiKey] = useState("");
	const [showKey, setShowKey] = useState(false);
	const [remember, setRemember] = useState(false);
	const [submitting, setSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	if (!ctxLoading && isAuthenticated) {
		const from = searchParams.get("from") || "/dashboard";
		return <Navigate to={from} replace />;
	}

	const handleSubmit = async (e: FormEvent) => {
		e.preventDefault();
		setError(null);

		if (!apiKey.trim()) {
			setError("Please enter your authorization key.");
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
				setError("Invalid Authorization key. Please verify and try again.");
			} else if (msg.includes("Failed to fetch") || msg.includes("Network")) {
				setError("Unable to reach the server. Check your connection.");
			} else {
				setError(msg);
			}
			setSubmitting(false);
		}
	};

	return (
		<div className="min-h-screen w-full flex flex-col md:flex-row bg-[#05070f] text-[#f8fafc] font-sans selection:bg-rose-500/30 overflow-hidden relative" role="main" aria-label="BAZSPARK Login">
			
			{/* Custom CSS for the 3D grid and premium micro-interactions */}
			<style dangerouslySetInnerHTML={{ __html: `
				.grid-3d-bg {
					position: absolute;
					inset: 0;
					z-index: 0;
					overflow: hidden;
					background-color: #05070f;
					perspective: 280px;
				}
				.grid-3d-grid {
					position: absolute;
					top: -60%;
					left: -50%;
					right: -50%;
					bottom: -50%;
					width: 200%;
					height: 220%;
					background-image: 
						linear-gradient(rgba(239, 68, 68, 0.035) 1px, transparent 1px),
						linear-gradient(90deg, rgba(239, 68, 68, 0.035) 1px, transparent 1px);
					background-size: 50px 50px;
					transform: rotateX(60deg) translateY(0);
					transform-origin: center center;
					animation: gridScroll 18s linear infinite;
				}
				@keyframes gridScroll {
					0% {
						transform: rotateX(60deg) translateY(0);
					}
					100% {
						transform: rotateX(60deg) translateY(50px);
					}
				}
				.grid-3d-overlay {
					position: absolute;
					inset: 0;
					background: radial-gradient(circle at 50% 40%, transparent 10%, #05070f 85%);
					pointer-events: none;
				}
				.feature-icon-box {
					transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.3s ease;
				}
				.feature-row:hover .feature-icon-box {
					transform: scale(1.08) rotate(3deg);
				}
			` }} />

			{/* 3D perspective grid background */}
			<div className="grid-3d-bg pointer-events-none">
				<div className="grid-3d-grid" />
				<div className="grid-3d-overlay" />
				{/* Glowing orbs for depth */}
				<div className="absolute top-[10%] left-[10%] w-[50%] h-[50%] rounded-full bg-rose-500/[0.03] blur-[130px]" />
				<div className="absolute bottom-[10%] right-[10%] w-[50%] h-[50%] rounded-full bg-cyan-500/[0.02] blur-[130px]" />
			</div>

			{/* ═══════════════════════════════════════════════════════════════
				LEFT PANEL: Brand Identity, Logo and Feature List (50% Width)
			   ═════════════════════════════════════════════════════════════════ */}
			<div className="w-full md:w-1/2 relative flex flex-col justify-between p-10 lg:p-16 xl:p-20 z-10 border-b md:border-b-0 md:border-r border-slate-900/60">
				
				{/* Top Branding Section */}
				<div className="flex items-center gap-4">
					<BazSparkLogo size={42} animated className="flex-shrink-0" />
					<BazSparkWordmark size="md" />
				</div>

				{/* Headline and Features List */}
				<div className="my-auto max-w-lg space-y-10 py-10">
					<h1 className="text-3xl lg:text-4xl font-extrabold tracking-tight text-white leading-tight">
						Mission Critical Engineering <br />Systems
					</h1>

					<div className="space-y-6">
						{/* Feature 1 */}
						<div className="flex gap-4 feature-row group">
							<div className="feature-icon-box h-10 w-10 rounded-lg flex items-center justify-center shrink-0 bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 group-hover:shadow-[0_0_15px_rgba(34,211,238,0.2)]">
								<Compass className="h-5 w-5" />
							</div>
							<div className="space-y-1">
								<h3 className="font-bold text-white text-[15px] tracking-wide">
									Advanced CAD Integration
								</h3>
								<p className="text-slate-400 text-xs leading-relaxed">
									Precision routing and 3D modeling for fire detection and compliance systems.
								</p>
							</div>
						</div>

						{/* Feature 2 */}
						<div className="flex gap-4 feature-row group">
							<div className="feature-icon-box h-10 w-10 rounded-lg flex items-center justify-center shrink-0 bg-orange-500/10 border border-orange-500/20 text-orange-400 group-hover:shadow-[0_0_15px_rgba(249,115,22,0.2)]">
								<Settings className="h-5 w-5" />
							</div>
							<div className="space-y-1">
								<h3 className="font-bold text-white text-[15px] tracking-wide">
									NFPA & SOLAS Compliance
								</h3>
								<p className="text-slate-400 text-xs leading-relaxed">
									Automated regulatory checks and real-time status validation.
								</p>
							</div>
						</div>

						{/* Feature 3 */}
						<div className="flex gap-4 feature-row group">
							<div className="feature-icon-box h-10 w-10 rounded-lg flex items-center justify-center shrink-0 bg-purple-500/10 border border-purple-500/20 text-purple-400 group-hover:shadow-[0_0_15px_rgba(168,85,247,0.2)]">
								<Brain className="h-5 w-5" />
							</div>
							<div className="space-y-1">
								<h3 className="font-bold text-white text-[15px] tracking-wide">
									AI-Powered Insights
								</h3>
								<p className="text-slate-400 text-xs leading-relaxed">
									Intelligent route suggestion and predictive maintenance analysis.
								</p>
							</div>
						</div>
					</div>
				</div>

				{/* Bottom Quote & Log Section */}
				<div className="w-full">
					<div className="h-px bg-slate-800/80 mb-6 w-full" />
					<div className="flex items-center gap-4">
						{/* Micro dashboard layout preview square */}
						<div className="w-10 h-10 rounded border border-slate-800 bg-slate-950/90 flex-shrink-0 relative overflow-hidden flex items-center justify-center">
							<div className="absolute inset-0 opacity-[0.15] bg-[linear-gradient(rgba(239,68,68,0.5)_1px,transparent_1px),linear-gradient(90deg,rgba(239,68,68,0.5)_1px,transparent_1px)] bg-[size:4px_4px]" />
							<div className="w-4 h-4 rounded-full border-2 border-rose-500/40 border-t-rose-500 animate-spin" />
						</div>
						<div className="space-y-0.5">
							<p className="text-slate-200 text-xs font-semibold tracking-wide">
								&ldquo;Absolute reliability for high-stakes environments.&rdquo;
							</p>
							<p className="text-[9px] font-mono text-slate-500 tracking-widest uppercase">
								SYSTEM LOG :: SECURE INITIATION
							</p>
						</div>
					</div>
				</div>

			</div>

			{/* ═══════════════════════════════════════════════════════════════
				RIGHT PANEL: System Access Form Panel (50% Width)
			   ═════════════════════════════════════════════════════════════════ */}
			<div className="w-full md:w-1/2 flex items-center justify-center p-8 z-10 relative">
				
				<div className="w-full max-w-[420px] flex flex-col py-8">
					{/* Header */}
					<div className="mb-8">
						<h2 className="text-3xl font-bold text-white tracking-tight">
							System Access
						</h2>
						<p className="text-slate-400 text-sm mt-2">
							Enter your engineering key to authenticate secure session.
						</p>
					</div>

					{/* Login Form Container */}
					<div className="space-y-6">
						<form onSubmit={handleSubmit} className="space-y-5">
							{error && (
								<Alert variant="destructive" className="bg-red-500/10 border-red-500/20 text-red-400 py-3 rounded-lg">
									<AlertCircle className="h-4 w-4 text-red-400" />
									<AlertTitle className="text-xs font-bold uppercase tracking-wider">Sign-in failed</AlertTitle>
									<AlertDescription className="text-xs mt-0.5">{error}</AlertDescription>
								</Alert>
							)}

							{/* API Key input field */}
							<div className="space-y-2.5">
								<div className="flex justify-between items-center">
									<Label htmlFor="api-key" className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
										AUTHORIZATION KEY
									</Label>
									<button
										type="button"
										className="text-[11px] font-bold uppercase tracking-wider text-cyan-400 hover:text-cyan-300 transition-colors hover:underline"
										onClick={() => alert("Please contact BAZSPARK Support for credential questions.")}
									>
										SUPPORT
									</button>
								</div>
								<div className="relative">
									<KeyRound className="absolute left-3.5 top-1/2 -translate-y-1/2 h-[18px] w-[18px] text-slate-500" />
									<Input
										id="api-key"
										type={showKey ? "text" : "password"}
										autoComplete="off"
										autoFocus
										placeholder="BS-XXXX-XXXX-XXXX-XXXX"
										value={apiKey}
										onChange={(e) => setApiKey(e.target.value)}
										disabled={submitting}
										className="pl-11 pr-11 font-mono text-sm tracking-widest bg-slate-950/80 border-slate-800 text-white rounded-lg h-12 transition-all duration-300 focus:border-rose-500/80 focus:ring-1 focus:ring-rose-500/20 focus:shadow-[0_0_15px_rgba(239,68,68,0.15)]"
									/>
									<button
										type="button"
										onClick={() => setShowKey(!showKey)}
										className="absolute right-3.5 top-1/2 -translate-y-1/2 p-1 text-slate-500 transition-colors hover:text-rose-400"
										aria-label={showKey ? "Hide API key" : "Show API key"}
										tabIndex={-1}
									>
										{showKey ? (
											<EyeOff className="h-[18px] w-[18px]" />
										) : (
											<Eye className="h-[18px] w-[18px]" />
										)}
									</button>
								</div>
								<p className="text-[10px] text-slate-500 tracking-normal mt-1 leading-normal">
									Required for terminal access and CAD synchronization.
								</p>
							</div>

							{/* Remember me */}
							<div className="flex items-center gap-2.5 pt-1">
								<Checkbox
									id="remember"
									checked={remember}
									onCheckedChange={(v) => setRemember(v === true)}
									disabled={submitting}
									className="border-slate-800 h-4 w-4 data-[state=checked]:bg-rose-600 data-[state=checked]:border-rose-600"
								/>
								<Label htmlFor="remember" className="text-xs cursor-pointer select-none text-slate-400 hover:text-slate-300 transition-colors">
									Maintain persistent secure connection
								</Label>
							</div>

							{/* Submit button */}
							<Button
								type="submit"
								className="w-full h-12 text-xs font-bold tracking-wider rounded-lg transition-all duration-300 bg-rose-600 hover:bg-rose-500 text-white shadow-lg hover:shadow-rose-600/20 disabled:opacity-50 disabled:pointer-events-none mt-2"
								disabled={submitting || !apiKey.trim()}
							>
								{submitting ? (
									<>
										<Loader2 className="h-4 w-4 animate-spin mr-2" />
										INITIALIZING SESSION...
									</>
								) : (
									<>
										<ShieldCheck className="h-4 w-4 mr-2" />
										INITIALIZE SESSION
									</>
								)}
							</Button>
						</form>
					</div>
				</div>

			</div>
		</div>
	);
}

