/**
 * FireAlarmPage.tsx - Wrapper for the FireAlarmDesigner component
 * Includes error boundary and fallback message
 */
import { Component, type ReactNode, Suspense, lazy } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Flame, AlertTriangle, ArrowLeft, Activity } from 'lucide-react';
import { NavLink } from 'react-router-dom';

// ============================================================================
// Lazy load the heavy FireAlarmDesigner
// ============================================================================

const FireAlarmDesigner = lazy(() =>
  import('@/components/mockups/engineering/FireAlarmDesigner').then(m => ({
    default: m.FireAlarmDesigner,
  }))
);

// ============================================================================
// Error Boundary
// ============================================================================

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class FireAlarmErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex items-center justify-center p-8">
          <Card className="border-slate-700 bg-slate-800/80 max-w-md w-full">
            <CardContent className="p-8 text-center">
              <AlertTriangle className="h-12 w-12 mx-auto mb-4 text-amber-400" />
              <h3 className="text-lg font-medium text-slate-200 mb-2">Designer Unavailable</h3>
              <p className="text-sm text-slate-400 mb-4">
                The Fire Alarm Designer component could not be loaded. This may be due to a
                missing dependency or a rendering error.
              </p>
              {this.state.error && (
                <p className="text-xs text-slate-500 font-mono bg-slate-900 p-2 rounded mb-4">
                  {this.state.error.message}
                </p>
              )}
              <div className="flex gap-2 justify-center">
                <NavLink to="/">
                  <Button variant="outline" className="border-slate-600 text-slate-300">
                    <ArrowLeft className="h-4 w-4 mr-1" /> Go to Dashboard
                  </Button>
                </NavLink>
                <Button
                  className="bg-red-600 hover:bg-red-700 text-white border-none"
                  onClick={() => this.setState({ hasError: false, error: null })}
                >
                  Try Again
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      );
    }

    return this.props.children;
  }
}

// ============================================================================
// Loading indicator for Suspense
// ============================================================================

function DesignerLoader() {
  return (
    <div className="flex-1 flex items-center justify-center h-screen bg-slate-900">
      <div className="flex flex-col items-center gap-3">
        <Flame className="h-8 w-8 text-red-400 animate-pulse" />
        <Activity className="h-5 w-5 text-slate-400 animate-pulse" />
        <span className="text-sm text-slate-400">Loading Fire Alarm Designer...</span>
      </div>
    </div>
  );
}

// ============================================================================
// FireAlarmPage Component
// ============================================================================

export function FireAlarmPage() {
  return (
    <FireAlarmErrorBoundary>
      <Suspense fallback={<DesignerLoader />}>
        <FireAlarmDesigner />
      </Suspense>
    </FireAlarmErrorBoundary>
  );
}
