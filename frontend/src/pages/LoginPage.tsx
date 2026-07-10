/**
 * LoginPage.tsx — Professional engineering login (V213 redesign).
 *
 * Clean, minimal, trustworthy. No sparkles, no gradients, no animations.
 * A licensed fire-protection engineer should feel this is a serious tool.
 */

import {
	AlertCircle,
	Eye,
	EyeOff,
	KeyRound,
	Loader2,
	LogIn,
	ShieldCheck,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardFooter,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";

const APP_VERSION = "v1.55.0";

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
					// sessionStorage might be unavailable (private mode)
				}
			}
			await login(apiKey.trim());
			setSubmitting(false);
		} catch (err) {
			const msg = err instanceof Error ? err.message : "Login failed";
			if (msg.includes("429") || msg.includes("Too many")) {
				setError("Too many failed attempts. Please wait 5 minutes.");
			} else if (msg.includes("401") || msg.includes("Invalid")) {
				setError("Invalid API key. Please check and try again.");
			} else if (msg.includes("Failed to fetch") || msg.includes("Network")) {
				setError("Cannot reach the server. Check your network connection.");
			} else {
				setError(msg);
			}
			setSubmitting(false);
		}
	};

	return (
		<div className="min-h-screen w-full flex items-center justify-center bg-background p-4">
			<div className="w-full max-w-md">
				{/* Brand header — flat, no gradient */}
				<div className="flex items-center justify-center gap-2 mb-6">
					<div className="h-8 w-8 rounded-md bg-primary flex items-center justify-center">
						<ShieldCheck className="h-4 w-4 text-primary-foreground" />
					</div>
					<span className="text-base font-semibold text-foreground tracking-tight">
						BAZSPARK
					</span>
				</div>

				<Card>
					<CardHeader className="space-y-1">
						<CardTitle>Sign In</CardTitle>
						<CardDescription>
							Enter your FireAI API key. Exchanged for a session cookie,
							never stored on disk.
						</CardDescription>
					</CardHeader>

					<form onSubmit={handleSubmit}>
						<CardContent className="space-y-3">
							{error && (
								<Alert variant="destructive">
									<AlertCircle className="h-4 w-4" />
									<AlertTitle>Authentication failed</AlertTitle>
									<AlertDescription>{error}</AlertDescription>
								</Alert>
							)}

							<div className="space-y-1.5">
								<Label
									htmlFor="api-key"
									className="text-xs font-medium text-muted-foreground"
								>
									API Key
								</Label>
								<div className="relative">
									<KeyRound className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
									<Input
										id="api-key"
										type={showKey ? "text" : "password"}
										autoComplete="off"
										autoFocus
										placeholder="Paste your FireAI API key"
										value={apiKey}
										onChange={(e) => setApiKey(e.target.value)}
										disabled={submitting}
										className="pl-9 pr-9 font-mono text-sm"
									/>
									<button
										type="button"
										onClick={() => setShowKey(!showKey)}
										className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors p-1"
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
								<p className="text-xs text-muted-foreground">
									Set via FIREAI_API_KEY environment variable on the backend.
								</p>
							</div>

							<div className="flex items-center gap-2">
								<Checkbox
									id="remember"
									checked={remember}
									onCheckedChange={(v) => setRemember(v === true)}
									disabled={submitting}
								/>
								<Label
									htmlFor="remember"
									className="text-xs text-muted-foreground cursor-pointer select-none"
								>
									Remember key on this device (sessionStorage)
								</Label>
							</div>
						</CardContent>

						<CardFooter className="flex flex-col gap-2">
							<Button
								type="submit"
								className="w-full"
								disabled={submitting || !apiKey.trim()}
							>
								{submitting ? (
									<>
										<Loader2 className="h-4 w-4 animate-spin" />
										Signing in...
									</>
								) : (
									<>
										<LogIn className="h-4 w-4" />
										Sign In
									</>
								)}
							</Button>
							<p className="text-[10px] text-muted-foreground text-center font-mono">
								NFPA 72 · AHJ Ready · {APP_VERSION}
							</p>
						</CardFooter>
					</form>
				</Card>

				<p className="text-center text-[10px] text-muted-foreground mt-4 font-mono">
					© 2026 BAZSPARK · Safety-Critical Engineering Platform
				</p>
			</div>
		</div>
	);
}
