/*
 * NotFoundPage.tsx — 404 fallback page
 * =====================================
 * P0.6 FIX: App.tsx had no `*` (catch-all) route, so any unrecognized URL
 * silently rendered a blank page inside the AppShell. This page gives the
 * user a clear 404 message with a link back to the dashboard.
 *
 * Safety rationale: a blank page in a fire-safety engineering tool could
 * mislead an engineer into thinking the system is working when a route is
 * misconfigured. A visible 404 makes the misconfiguration immediately
 * apparent.
 */
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Home, AlertCircle } from 'lucide-react';

export function NotFoundPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 px-6 text-center">
      <div className="flex items-center justify-center w-20 h-20 rounded-full bg-amber-500/10 border-2 border-amber-500/30">
        <AlertCircle className="w-10 h-10 text-amber-400" aria-hidden="true" />
      </div>
      <div className="space-y-2">
        <h1 className="text-5xl font-bold text-slate-100">404</h1>
        <p className="text-xl font-medium text-slate-300">
          {t('errors.pageNotFound', 'Page Not Found')}
        </p>
        <p className="text-sm text-slate-400 max-w-md">
          {t(
            'errors.pageNotFoundDescription',
            'The page you are looking for does not exist or has been moved. This may indicate a misconfigured route or a stale bookmark.'
          )}
        </p>
      </div>
      <Button
        onClick={() => navigate('/dashboard')}
        className="bg-slate-100 text-slate-900 hover:bg-slate-200"
      >
        <Home className="w-4 h-4 mr-2" aria-hidden="true" />
        {t('actions.backToDashboard', 'Back to Dashboard')}
      </Button>
    </div>
  );
}

export default NotFoundPage;
