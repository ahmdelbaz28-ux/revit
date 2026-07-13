/**
 * LoginPage.tsx — BAZSPARK Login (V237 — Split-screen redesign)
 *
 * Layout:
 *   Left half:  EngineeringBackground (AutoCAD 2D + Revit 3D + bidirectional arrow)
 *   Right half: Login card (clean, high-contrast, no color overlap)
 *
 * Card design (V237 — fixed user feedback):
 *   - Label:    distinct color (#8a9bae — light slate)
 *   - Input:    dark bg (#141414), clear border, white text
 *   - Button:   solid blue (#3b82f6), white text
 *   - Headings: pure white
 *   - No color overlap / no overlay
 */

import {
        AlertCircle,
        Eye,
        EyeOff,
        KeyRound,
        Loader2,
        ShieldCheck,
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

// V242: Lazy-load the heavy EngineeringBackground SVG (990 lines, ~30kB).
// This keeps it off the critical render path so FCP/LCP on /login improve.
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

        // V242: Defer loading the EngineeringBackground until the browser is idle.
        // This prevents the 30kB SVG chunk from competing with the login card
        // for parse/compile time during the critical FCP/LCP window.
        const [showBackground, setShowBackground] = useState(false);
        useEffect(() => {
                // requestIdleCallback may not exist in older browsers — fall back to setTimeout.
                const hasRIC =
                        typeof window !== "undefined" && "requestIdleCallback" in window;
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
                <div
                        className="min-h-screen w-full relative overflow-hidden"
                        style={{ backgroundColor: "#0a0a0a" }}
                        role="main"
                        aria-label="BAZSPARK login"
                >
                        {/* Engineering CAD animated background (left half)
                            V242: Deferred via requestIdleCallback so the 30kB SVG chunk
                            loads AFTER the login card is interactive, keeping it off the
                            critical FCP/LCP path entirely. */}
                        {showBackground ? (
                                <Suspense
                                        fallback={
                                                <div
                                                        className="absolute inset-0"
                                                        style={{
                                                                background:
                                                                        "radial-gradient(ellipse at 30% 50%, #0a0f1a 0%, #050709 70%, #000000 100%)",
                                                        }}
                                                        aria-hidden="true"
                                                />
                                        }
                                >
                                        <EngineeringBackground />
                                </Suspense>
                        ) : (
                                <div
                                        className="absolute inset-0"
                                        style={{
                                                background:
                                                        "radial-gradient(ellipse at 30% 50%, #0a0f1a 0%, #050709 70%, #000000 100%)",
                                        }}
                                        aria-hidden="true"
                                />
                        )}

                        {/* ═══════════════════════════════════════════════════════════════
                            Right half: Login card
                           ═════════════════════════════════════════════════════════════════ */}
                        <div
                                className="absolute top-0 right-0 h-full flex items-center justify-center px-8"
                                style={{ width: "50%", zIndex: 20, pointerEvents: "auto" }}
                        >
                                <div className="w-full max-w-[400px] cad-login-enter" style={{ position: "relative", zIndex: 30 }}>
                                        {/* ── Brand header ────────────────────────────────────── */}
                                        <div className="flex flex-col items-center mb-8">
                                                <BazSparkLogo size={64} animated />
                                                <div className="mt-4">
                                                        <BazSparkWordmark size="md" />
                                                </div>
                                                <p
                                                        className="text-[11px] mt-2 uppercase tracking-wider"
                                                        style={{ color: "#6b7280" }}
                                                >
                                                        FireAI Digital Twin Platform
                                                </p>
                                                <p
                                                        className="text-[11px] mt-0.5 text-center"
                                                        style={{ color: "#4b5563" }}
                                                >
                                                        Safety-Critical Fire Alarm Engineering Platform
                                                </p>
                                        </div>

                                        {/* ── Login card ─────────────────────────────────────── */}
                                        <div
                                                className="rounded-xl p-7"
                                                style={{
                                                        backgroundColor: "rgba(18,18,18,0.85)",
                                                        border: "1px solid rgba(80,80,80,0.4)",
                                                        boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
                                                }}
                                        >
                                                {/* Heading */}
                                                <div className="mb-6">
                                                        <h2
                                                                className="text-[22px] font-medium"
                                                                style={{ color: "#ffffff", letterSpacing: "-0.02em" }}
                                                        >
                                                                Welcome back
                                                        </h2>
                                                        <p
                                                                className="text-[14px] mt-2"
                                                                style={{ color: "#6b7280" }}
                                                        >
                                                                Sign in to access your engineering workspace
                                                        </p>
                                                </div>

                                                <form onSubmit={handleSubmit} className="space-y-5">
                                                        {error && (
                                                                <Alert variant="destructive">
                                                                        <AlertCircle className="h-4 w-4" />
                                                                        <AlertTitle>Sign-in failed</AlertTitle>
                                                                        <AlertDescription>{error}</AlertDescription>
                                                                </Alert>
                                                        )}

                                                        {/* ── API Key field ─────────────────────────────── */}
                                                        <div className="space-y-2">
                                                                <Label
                                                                        htmlFor="api-key"
                                                                        className="text-[11px] font-medium uppercase tracking-wider"
                                                                        style={{ color: "#8a9bae" }}
                                                                >
                                                                        API Key
                                                                </Label>
                                                                <div className="relative">
                                                                        <KeyRound
                                                                                className="absolute left-3.5 top-1/2 -translate-y-1/2 h-[18px] w-[18px]"
                                                                                style={{ color: "#4b5563" }}
                                                                        />
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
                                                                                style={{
                                                                                        backgroundColor: "#141414",
                                                                                        border: "1px solid rgba(80,80,80,0.5)",
                                                                                        color: "#ffffff",
                                                                                }}
                                                                        />
                                                                        <button
                                                                                type="button"
                                                                                onClick={() => setShowKey(!showKey)}
                                                                                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 transition-colors"
                                                                                style={{ color: "#6b7280" }}
                                                                                onMouseEnter={(e) => (e.currentTarget.style.color = "#3b82f6")}
                                                                                onMouseLeave={(e) => (e.currentTarget.style.color = "#6b7280")}
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

                                                        {/* ── Remember me ───────────────────────────────── */}
                                                        <div className="flex items-center gap-2.5">
                                                                <Checkbox
                                                                        id="remember"
                                                                        checked={remember}
                                                                        onCheckedChange={(v) => setRemember(v === true)}
                                                                        disabled={submitting}
                                                                />
                                                                <Label
                                                                        htmlFor="remember"
                                                                        className="text-[13px] cursor-pointer select-none"
                                                                        style={{ color: "#8a9bae" }}
                                                                >
                                                                        Remember me
                                                                </Label>
                                                        </div>

                                                        {/* ── Sign In button ────────────────────────────── */}
                                                        <Button
                                                                type="submit"
                                                                className="w-full h-11 text-[14px] font-semibold"
                                                                disabled={submitting || !apiKey.trim()}
                                                                style={{
                                                                        backgroundColor: submitting || !apiKey.trim() ? "#1f2937" : "#3b82f6",
                                                                        color: submitting || !apiKey.trim() ? "#6b7280" : "#ffffff",
                                                                        border: "none",
                                                                }}
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

                                        {/* ── Footer ─────────────────────────────────────────── */}
                                        <div className="flex items-center justify-center gap-2 mt-6 text-[11px]" style={{ color: "#4b5563" }}>
                                                <ShieldCheck className="h-3 w-3" style={{ color: "#3b82f6" }} />
                                                <span className="uppercase tracking-wider">Secured • {APP_VERSION}</span>
                                        </div>
                                </div>
                        </div>
                </div>
        );
}
