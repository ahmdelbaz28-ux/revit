// NOSONAR
import React from "react";
import { ErrorRecoveryView, getErrorContextId } from "./ErrorRecoveryView";

export { ErrorRecoveryView, getErrorContextId };

export class ErrorRecovery extends React.Component<
	{
		children: React.ReactNode;
		onError?: (error: Error, info: React.ErrorInfo) => void;
		errorContextId?: string;
		reload?: () => void;
	},
	{ hasError: boolean; error: Error | null; errorInfo: React.ErrorInfo | null }
> {
	state = {
		hasError: false,
		error: null as Error | null,
		errorInfo: null as React.ErrorInfo | null,
	};

	static getDerivedStateFromError(error: Error) {
		return { hasError: true, error, errorInfo: null };
	}

	componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
		this.setState({ errorInfo });
		this.props.onError?.(error, errorInfo);
	}

	render() {
		if (this.state.hasError) {
			return (
				<ErrorRecoveryView
					error={this.state.error}
					errorInfo={this.state.errorInfo}
					errorContextId={getErrorContextId(
						this.state.error,
						this.state.errorInfo?.componentStack,
						this.props.errorContextId,
					)}
					reload={this.props.reload ?? (() => window.location.reload())}
				/>
			);
		}

		return this.props.children;
	}
}
