/**
 * PageErrorBoundary.tsx - Page-level error boundary
 * Catches errors in individual page routes so that one broken page
 * does NOT crash the entire application. Shows a page-level error
 * message with a "Retry" button that resets the boundary.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
	children: ReactNode;
	pageName?: string;
}

interface State {
	hasError: boolean;
	error: Error | null;
}

export class PageErrorBoundary extends Component<Props, State> {
	constructor(props: Props) {
		super(props);
		this.state = { hasError: false, error: null };
	}

	static getDerivedStateFromError(error: Error): State {
		return { hasError: true, error };
	}

	componentDidCatch(error: Error, errorInfo: ErrorInfo) {
		// Log the error for debugging — never suppress silently
		console.error(
			`[BAZSPARK PageErrorBoundary] Error in page "${this.props.pageName || "unknown"}":`,
			error,
			errorInfo,
		);
	}

	handleRetry = () => {
		this.setState({ hasError: false, error: null });
	};

	render() {
		if (this.state.hasError) {
			const pageLabel = this.props.pageName || "This page";

			return (
				<div
					className="flex-1 flex items-center justify-center p-8"
					style={{ backgroundColor: "#0f172a" }}
				>
					<div
						className="border rounded-lg p-8 max-w-lg w-full"
						style={{
							backgroundColor: "rgba(30,41,59,0.8)",
							borderColor: "rgba(153,27,27,0.5)",
						}}
					>
						<div className="flex items-start gap-4">
							<div className="shrink-0 mt-1">
								<svg
									className="h-8 w-8"
									style={{ color: "#f87171" }}
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
								>
									<path
										strokeLinecap="round"
										strokeLinejoin="round"
										strokeWidth={2}
										d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
									/>
								</svg>
							</div>
							<div className="flex-1 min-w-0">
								<h3
									className="text-base font-semibold mb-1"
									style={{ color: "#f1f5f9" }}
								>
									{pageLabel} Error
								</h3>
								<p className="text-sm mb-4" style={{ color: "#94a3b8" }}>
									{pageLabel} encountered an error and could not render. Other
									pages remain functional.
								</p>

								{import.meta.env.DEV && this.state.error && (
									<pre
										className="text-xs p-3 rounded mb-4 overflow-auto max-h-40 font-mono"
										style={{ backgroundColor: "#0f172a", color: "#f87171" }}
									>
										{this.state.error.message}
									</pre>
								)}

								<button
									className="px-4 py-2 rounded text-sm text-white"
									style={{ backgroundColor: "#ea580c" }}
									onClick={{this.handleRetry onKeyDown={(e) => e.key === "Enter" && {this.handleRetry}									onMouseOver={(e) =>
										(e.currentTarget.style.backgroundColor = "#c2410c")
									}
									onMouseOut={(e) =>
										(e.currentTarget.style.backgroundColor = "#ea580c")
									}
								>
									Retry
								</button>
							</div>
						</div>
					</div>
				</div>
			);
		}

		return this.props.children;
	}
}
