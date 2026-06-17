/**
 * ErrorBoundary.tsx - Application-level error boundary
 * Prevents white-screen crashes in the fire alarm engineering interface.
 * SAFETY-CRITICAL: Must never hide errors silently.
 */
import { Component, type ReactNode, type ErrorInfo } from 'react';
import { ErrorRecoveryView, getErrorContextId } from './ErrorRecoveryView';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log to console — never suppress errors silently
    console.error('[FireAI ErrorBoundary] Caught error:', error, errorInfo);
    this.setState({ errorInfo });
    // Forward to parent error handler if provided
    this.props.onError?.(error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <ErrorRecoveryView
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          errorContextId={getErrorContextId(this.state.error, this.state.errorInfo?.componentStack)}
          reload={this.handleReset}
        />
      );
    }

    return this.props.children;
  }
}
