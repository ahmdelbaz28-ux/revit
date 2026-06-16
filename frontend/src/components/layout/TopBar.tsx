import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { Flame, Search, Settings, CircleHelp, ShieldCheck, AlertCircle, Languages } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useHealth } from '@/hooks/useApi';
import { useSmartHelp } from '@/hooks/useSmartHelp';
import { NAV_ITEMS } from '@/components/layout/Sidebar';

export function TopBar() {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { data: health, loading, connected, error } = useHealth();
  const { openHelp, openSearch } = useSmartHelp();
  const currentRoute = NAV_ITEMS.find((item) => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`));
  const isRtl = document.documentElement.dir === 'rtl' || i18n.language.startsWith('ar');

  const handleLanguageChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    i18n.changeLanguage(event.target.value);
  };

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-800 bg-slate-950/90 px-4 backdrop-blur">
      <div className="flex items-center gap-2 min-w-0">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-red-600 text-white shadow-lg shadow-red-950/30">
          <Flame className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-100">FireAI Digital Twin</div>
          <div className="truncate text-[11px] text-slate-500">
            {currentRoute ? t(currentRoute.labelKey) : t('help.unknownRoute')}
          </div>
        </div>
      </div>

      <div className="hidden min-w-0 flex-1 items-center gap-2 md:flex">
        <div className="flex min-w-0 items-center gap-2 rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1.5 text-xs text-slate-400">
          <ShieldCheck className="h-3.5 w-3.5 text-red-400" />
          <span className="truncate">{t('topBar.contextPlaceholder')}</span>
        </div>
      </div>

      <div className={isRtl ? 'ml-auto flex items-center gap-2' : 'ml-auto flex items-center gap-2'}>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          title={t('help.openSearchTooltip')}
          aria-label={t('help.openSearchTooltip')}
          onClick={() => openSearch()}
        >
          <Search className="h-4 w-4" />
        </Button>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          title={t('help.openHelpTooltip')}
          aria-label={t('help.openHelpTooltip')}
          onClick={() => openHelp()}
        >
          <CircleHelp className="h-4 w-4" />
        </Button>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          title={t('common.settings')}
          aria-label={t('common.settings')}
          onClick={() => navigate('/settings')}
        >
          <Settings className="h-4 w-4" />
        </Button>

        <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/70 px-2 py-1">
          {loading ? (
            <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
          ) : connected ? (
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
          ) : (
            <AlertCircle className="h-3.5 w-3.5 text-red-400" />
          )}
          <Badge
            variant={connected ? 'default' : error || !health ? 'destructive' : 'secondary'}
            className={connected ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20' : 'bg-red-500/10 text-red-300 border-red-500/20'}
          >
            {loading ? t('common.loading') : connected ? t('common.online') : t('common.offline')}
          </Badge>
        </div>

        <div className="relative">
          <Languages className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
          <select
            value={i18n.language}
            onChange={handleLanguageChange}
            className="h-8 rounded-full border border-slate-700 bg-slate-900 pl-7 pr-7 text-xs text-slate-200 outline-none focus:border-red-500/60"
            aria-label={t('settings.language')}
          >
            <option value="en">EN</option>
            <option value="ar">عربي</option>
          </select>
        </div>
      </div>
    </header>
  );
}
