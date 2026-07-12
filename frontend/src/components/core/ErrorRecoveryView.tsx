
import { AlertTriangle, BookOpenText, RotateCcw } from "lucide-react";
import { useState } from "react";
import { SmartHelpDrawer } from "@/components/help/SmartHelpDrawer";
import { Button } from "@/components/ui/button";

export function hashString(value: string): string {
	let hash = 2166136261;
	for (let index = 0; index < value.length; index += 1) {
		hash ^= value.charCodeAt(index);  // NOSONAR: typescript:S7758
		hash = Math.imul(hash, 16777619);
	}
	return (hash >>> 0).toString(16).padStart(8, "0");
}

export function getErrorContextId(
	error: Error | null,
	componentStack: string | null | undefined,
	fallback?: string,
) {
	if (fallback) return fallback;

	const source = `${error?.name ?? "Error"}:${error?.message ?? "unknown"}:${componentStack ?? ""}`;
	return `ERR-${hashString(source).toUpperCase()}`;
}

export function ErrorRecoveryView({
	error,
	errorInfo,
	errorContextId,
	reload,
}: {
	error: Error | null;
	errorInfo: React.ErrorInfo | null;
	errorContextId: string;
	reload?: () => void;
}) {
	const [helpOpen, setHelpOpen] = useState(false);
	const details = errorInfo?.componentStack ?? "";
	const message = error?.message ?? "Unknown component error";
	const name = error?.name ?? "Error";

	return (
		<div className="flex min-h-screen flex-1 items-center justify-center bg-background p-6">
			<div className="w-full max-w-3xl rounded-3xl border border-danger/30 bg-background/90 p-6 shadow-2xl shadow-black/40">
				<div className="flex items-start gap-4">
					<div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-danger/30 bg-red-500/10 text-danger">
						<AlertTriangle className="h-6 w-6" />
					</div>
					<div className="min-w-0 flex-1">
						<p className="text-xs font-semibold uppercase tracking-[0.22em] text-danger">
							Error Recovery
						</p>
						<h1 className="mt-2 text-xl font-semibold text-foreground">
							A component failed to render
						</h1>
						<p className="mt-2 text-sm leading-6 text-muted-foreground">
							The application kept running, but this screen needs attention
							before engineering work continues.
						</p>

						<div className="mt-5 grid gap-3 sm:grid-cols-2">
							<div className="rounded-md border border-slate-800 bg-card p-4">
								<p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
									Error context ID
								</p>
								<p className="mt-2 break-all font-mono text-sm text-foreground">
									{errorContextId}
								</p>
							</div>
							<div className="rounded-md border border-slate-800 bg-card p-4">
								<p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
									Error type
								</p>
								<p className="mt-2 font-mono text-sm text-foreground">{name}</p>
							</div>
						</div>

						<div className="mt-4 rounded-md border border-red-500/20 bg-red-500/10 p-4">
							<p className="text-xs uppercase tracking-[0.18em] text-red-300">
								Error details
							</p>
							<pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-5 text-red-200">
								{message}
							</pre>
						</div>

						{details && (
							<details className="mt-4 rounded-md border border-slate-800 bg-muted/50 p-4">
								<summary className="cursor-pointer text-sm font-medium text-foreground">
									Component stack
								</summary>
								<pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-5 text-muted-foreground">
									{details}
								</pre>
							</details>
						)}

						<div className="mt-6 flex flex-col gap-3 sm:flex-row">
							<Button
								type="button"
								className="flex-1 bg-danger text-white hover:bg-danger/90"
								onClick={() => setHelpOpen(true)}
							>
								<BookOpenText className="h-4 w-4" />
								Get Help
							</Button>
							<Button
								type="button"
								variant="outline"
								className="flex-1 border-border text-foreground hover:bg-card hover:text-foreground"
								onClick={reload ?? (() => window.location.reload())}
							>
								<RotateCcw className="h-4 w-4" />
								{reload ? "Retry Component" : "Reload Application"}
							</Button>
						</div>
					</div>
				</div>
			</div>

			<SmartHelpDrawer
				open={helpOpen}
				onOpenChange={setHelpOpen}
				initialContextId="troubleshooting.app-crash"
				initialSearch={message}
			/>
		</div>
	);
}
