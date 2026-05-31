/**
 * ErrorBoundary.tsx - Application-level error boundary
 * Prevents white-screen crashes in the fire alarm engineering interface.
 * SAFETY-CRITICAL: Must never hide errors silently.
 */
import { Component, type ReactNode, type ErrorInfo } from 'react';

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

      const isDev = import.meta.env.DEV;

      return (
        <div className="flex-1 flex items-center justify-center p-8" style={{ backgroundColor: '#0f172a' }}>
          <div className="border rounded-lg p-8 max-w-lg w-full" style={{ backgroundColor: 'rgba(30,41,59,0.8)', borderColor: 'rgba(153,27,27,0.5)' }}>
            <div className="flex items-start gap-4">
              <div className="shrink-0 mt-1">
                <svg className="h-8 w-8" style={{ color: '#f87171' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-base font-semibold mb-1" style={{ color: '#f1f5f9' }}>
                  Component Error
                </h3>
                <p className="text-sm mb-4" style={{ color: '#94a3b8' }}>
                  A component failed to render. Other parts of the application remain functional.
                </p>

                {isDev && this.state.error && (
                  <pre className="text-xs p-3 rounded mb-4 overflow-auto max-h-40 font-mono" style={{ backgroundColor: '#0f172a', color: '#f87171' }}>
                    {this.state.error.message}
                    {this.state.errorInfo?.componentStack && (
                      '\n\nComponent Stack:' + this.state.errorInfo.componentStack
                    )}
                  </pre>
                )}

                <button
                  className="px-4 py-2 rounded text-sm text-white"
                  style={{ backgroundColor: '#dc2626' }}
                  onClick={this.handleReset}
                  onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#b91c1c')}
                  onMouseOut={(e) => (e.currentTarget.style.backgroundColor = '#dc2626')}
                >
                  Retry Component
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
