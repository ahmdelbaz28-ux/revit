/**
 * LoginPage.tsx — BAZSPARK Login (Awwwards Identity).
 *
 * Deep navy + cyan + glassmorphism. Premium educator feel.
 */

import {
        AlertCircle,
        Eye,
        EyeOff,
        KeyRound,
        Loader2,
        ShieldCheck,
        Zap,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
                <div className="min-h-screen w-full flex items-center justify-center bg-background p-4 relative overflow-hidden">
                        {/* WebGL-style gradient background (CSS fallback) */}
                        <div
                                className="absolute inset-0 pointer-events-none"
                                style={{
                                        background:
                                                "radial-gradient(ellipse at 30% 20%, rgba(6,182,212,0.08) 0%, transparent 50%), radial-gradient(ellipse at 70% 80%, rgba(6,182,212,0.05) 0%, transparent 50%)",
                                }}
                        />
                        {/* Noise texture overlay */}
                        <div
                                className="absolute inset-0 pointer-events-none opacity-30"
                                style={{
                                        backgroundImage:
                                                "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E\")",
                                }}
                        />

                        <div className="w-full max-w-[440px] relative z-10">
                                {/* Brand header */}
                                <div className="flex flex-col items-center mb-10">
                                        <div className="h-14 w-14 rounded-xl flex items-center justify-center mb-5 bg-cyan-400/10 border border-cyan-400/20 backdrop-blur-[20px] shadow-md shadow-cyan-500/10">
                                                <Zap className="h-7 w-7 text-cyan-300" fill="currentColor" />
                                        </div>
                                        <h1
                                                className="text-[28px] font-semibold text-foreground tracking-tight"
                                                style={{ letterSpacing: "-0.04em" }}
                                        >
                                                BAZSPARK
                                        </h1>
                                        <p className="text-[13px] text-muted-foreground mt-2 uppercase tracking-wider">
                                                FireAI Digital Twin Platform
                                        </p>
                                </div>

                                {/* Login card — glassmorphism */}
                                <div className="glass rounded-xl p-8 shadow-xl">
                                        <div className="mb-8">
                                                <h2
                                                        className="text-[24px] font-medium text-foreground"
                                                        style={{ letterSpacing: "-0.02em", lineHeight: 1.2 }}
                                                >
                                                        Welcome back
                                                </h2>
                                                <p className="text-[15px] text-muted-foreground mt-2.5 leading-relaxed" style={{ maxWidth: "65ch" }}>
                                                        Sign in to access your engineering workspace
                                                </p>
                                        </div>

                                        <form onSubmit={handleSubmit} className="space-y-6">
                                                {error && (
                                                        <Alert variant="destructive">
                                                                <AlertCircle className="h-4 w-4" />
                                                                <AlertTitle>Sign-in failed</AlertTitle>
                                                                <AlertDescription>{error}</AlertDescription>
                                                        </Alert>
                                                )}

                                                <div className="space-y-2.5">
                                                        <Label
                                                                htmlFor="api-key"
                                                                className="text-[12px] font-medium text-muted-foreground uppercase tracking-wider"
                                                        >
                                                                API Key
                                                        </Label>
                                                        <div className="relative">
                                                                <KeyRound className="absolute left-4 top-1/2 -translate-y-1/2 h-[18px] w-[18px] text-muted-foreground" />
                                                                <Input
                                                                        id="api-key"
                                                                        type={showKey ? "text" : "password"}
                                                                        autoComplete="off"
                                                                        autoFocus
                                                                        placeholder="Enter your API key"
                                                                        value={apiKey}
                                                                        onChange={(e) => setApiKey(e.target.value)}
                                                                        disabled={submitting}
                                                                        className="pl-11 pr-11 font-mono text-[14px]"
                                                                />
                                                                <button
                                                                        type="button"
                                                                        onClick={() => setShowKey(!showKey)}
                                                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-cyan-300 transition-colors p-1"
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
                                                </div>

                                                <div className="flex items-center gap-2.5 pt-1">
                                                        <Checkbox
                                                                id="remember"
                                                                checked={remember}
                                                                onCheckedChange={(v) => setRemember(v === true)}
                                                                disabled={submitting}
                                                        />
                                                        <Label
                                                                htmlFor="remember"
                                                                className="text-[13px] text-muted-foreground cursor-pointer select-none"
                                                        >
                                                                Remember me
                                                        </Label>
                                                </div>

                                                <Button
                                                        type="submit"
                                                        className="w-full h-12 text-[15px] font-semibold mt-2"
                                                        disabled={submitting || !apiKey.trim()}
                                                >
                                                        {submitting ? (
                                                                <>
                                                                        <Loader2 className="h-4 w-4 animate-spin" />
                                                                        Signing in...
                                                                </>
                                                        ) : (
                                                                <>
                                                                        <ShieldCheck className="h-4 w-4" />
                                                                        Sign In
                                                                </>
                                                        )}
                                                </Button>
                                        </form>
                                </div>

                                {/* Footer */}
                                <div className="flex items-center justify-center gap-2 mt-8 text-[12px] text-muted-foreground">
                                        <ShieldCheck className="h-3 w-3 text-cyan-300" />
                                        <span className="uppercase tracking-wider">Secured • {APP_VERSION}</span>
                                </div>
                        </div>
                </div>
        );
}
