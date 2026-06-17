import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  BookOpenText,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  Search,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  getCategoryLabel,
  getHelpCategories,
  getRelatedTopics,
  getTopicText,
} from '@/help/contextRegistry';
import type { SmartHelpDrawerProps } from '@/help/types';
import { useSmartHelp } from '@/hooks/useSmartHelp';

interface DrawerLabels {
  title: string;
  searchPlaceholder: string;
  allCategories: string;
  clearFilters: string;
  results: string;
  noResults: string;
  steps: string;
  warnings: string;
  relatedTopics: string;
  openPage: string;
  navigationAvailable: string;
  emptyState: string;
  close: string;
}

const DRAWER_LABELS = {
  en: {
    title: 'Smart Help',
    searchPlaceholder: 'Search help topics...',
    allCategories: 'All',
    clearFilters: 'Clear filters',
    results: 'results',
    noResults: 'No help topics matched your search.',
    steps: 'Steps',
    warnings: 'Warnings',
    relatedTopics: 'Related topics',
    openPage: 'Open page',
    navigationAvailable: 'Navigation available',
    emptyState: 'Select a help topic to view guidance.',
    close: 'Close',
  },
  ar: {
    title: 'المساعدة الذكية',
    searchPlaceholder: 'ابحث في مواضيع المساعدة...',
    allCategories: 'الكل',
    clearFilters: 'مسح الفلاتر',
    results: 'نتيجة',
    noResults: 'لا توجد مواضيع مساعدة مطابقة لبحثك.',
    steps: 'الخطوات',
    warnings: 'تحذيرات',
    relatedTopics: 'مواضيع ذات صلة',
    openPage: 'فتح الصفحة',
    navigationAvailable: 'تنقل متاح',
    emptyState: 'اختر موضوع مساعدة لعرض الإرشاد.',
    close: 'إغلاق',
  },
} as const satisfies Record<'en' | 'ar', DrawerLabels>;

function getDocumentDirection(): 'ltr' | 'rtl' {
  if (typeof document === 'undefined') return 'ltr';
  return document.documentElement.dir === 'rtl' ? 'rtl' : 'ltr';
}

export function SmartHelpDrawer({
  open,
  onOpenChange,
  initialContextId,
  initialSearch = '',
}: SmartHelpDrawerProps) {
  const navigate = useNavigate();
  const {
    openHelp,
    closeHelp,
    selectedTopic,
    searchQuery,
    setSearchQuery,
    category,
    setCategory,
    results,
  } = useSmartHelp();
  const [documentDirection, setDocumentDirection] = useState<'ltr' | 'rtl'>(getDocumentDirection);
  const isRtl = documentDirection === 'rtl';
  const labels = isRtl ? DRAWER_LABELS.ar : DRAWER_LABELS.en;
  const categories = useMemo(() => getHelpCategories(), []);
  const displayedTopic = selectedTopic ?? results[0]?.topic ?? null;
  const topicText = displayedTopic ? getTopicText(displayedTopic, isRtl ? 'rtl' : 'ltr') : null;
  const relatedTopics = displayedTopic ? getRelatedTopics(displayedTopic) : [];
  const handleClose = useCallback(() => {
    closeHelp();
    onOpenChange(false);
  }, [closeHelp, onOpenChange]);

  useEffect(() => {
    if (!open) {
      closeHelp();
      return;
    }

    if (initialContextId) {
      openHelp(initialContextId, initialSearch);
      return;
    }

    if (initialSearch) {
      setSearchQuery(initialSearch);
    }
  }, [initialContextId, initialSearch, open, openHelp, setSearchQuery, closeHelp]);

  useEffect(() => {
    if (typeof document === 'undefined') return undefined;

    const updateDirection = () => setDocumentDirection(getDocumentDirection());
    const observer = new MutationObserver(updateDirection);

    updateDirection();
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['dir'] });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        handleClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleClose]);

  const handleNavigate = () => {
    if (!displayedTopic?.navigateTo) return;
    navigate(displayedTopic.navigateTo);
    handleClose();
  };

  const panelSideClasses = isRtl ? 'left-0 border-r border-slate-800' : 'right-0 border-l border-slate-800';
  const panelTransformClasses = isRtl
    ? open ? 'translate-x-0' : '-translate-x-full'
    : open ? 'translate-x-0' : 'translate-x-full';

  return (
    <div
      className={`fixed inset-0 z-[120] ${open ? 'pointer-events-auto' : 'pointer-events-none'}`}
      dir={isRtl ? 'rtl' : 'ltr'}
      aria-hidden={!open}
    >
      <div
        className={`absolute inset-0 bg-black/60 transition-opacity duration-300 ${open ? 'opacity-100' : 'opacity-0'}`}
        onClick={handleClose}
      />

<aside
        role="dialog"
        aria-modal="true"
        aria-label={labels.title}
        className={`fixed top-0 bottom-0 z-10 flex w-[min(58rem,94vw)] flex-col text-slate-100 shadow-2xl transition-transform duration-500 ease-out ${panelSideClasses} ${panelTransformClasses} bg-slate-950/90 backdrop-blur-2xl border-slate-700/50`}
      >
        <header className="flex shrink-0 items-center gap-3 border-b border-slate-700/50 p-4 bg-slate-900/50 backdrop-blur-lg">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-500/10 text-red-400 shadow-lg shadow-red-500/10">
            <BookOpenText className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold">{labels.title}</h2>
            <p className="text-xs text-slate-400">{displayedTopic?.id ?? ''}</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-slate-400 hover:bg-slate-800/60 hover:text-slate-100 transition-all duration-200 hover:rotate-90"
            onClick={handleClose}
            aria-label={labels.close}
          >
            <X className="h-4 w-4" />
          </Button>
        </header>

        <div className="space-y-3 border-b border-slate-800 p-4">
          <div className="relative">
            <Search className={`absolute top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 ${isRtl ? 'right-3' : 'left-3'}`} />
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={labels.searchPlaceholder}
              className={`bg-slate-900 border-slate-700 text-slate-100 placeholder:text-slate-500 focus-visible:ring-red-500/40 ${isRtl ? 'pr-10' : 'pl-10'}`}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant={category === 'all' ? 'secondary' : 'outline'}
              size="sm"
              className="h-7 border-slate-700 text-xs"
              onClick={() => setCategory('all')}
            >
              {labels.allCategories}
            </Button>
            {categories.map((categoryName) => (
              <Button
                key={categoryName}
                type="button"
                variant={category === categoryName ? 'secondary' : 'outline'}
                size="sm"
                className="h-7 border-slate-700 text-xs"
                onClick={() => setCategory(categoryName)}
              >
                {getCategoryLabel(categoryName, isRtl ? 'rtl' : 'ltr')}
              </Button>
            ))}
          </div>

          {(searchQuery || category !== 'all') && (
            <button
              type="button"
              className="text-xs text-red-300 hover:text-red-200"
              onClick={() => {
                setSearchQuery('');
                setCategory('all');
              }}
            >
              {labels.clearFilters}
            </button>
          )}
        </div>

        <div className="min-h-0 flex-1 grid grid-cols-[18rem_minmax(0,1fr)]">
          <nav className={`min-h-0 overflow-y-auto border-slate-800 p-3 ${isRtl ? 'border-l' : 'border-r'}`}>
            <div className="mb-3 flex items-center justify-between gap-2 px-2">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                {results.length} {labels.results}
              </span>
              {displayedTopic && (
                <span className="truncate text-xs text-slate-500" title={displayedTopic.id}>
                  {displayedTopic.id}
                </span>
              )}
            </div>

{results.length === 0 ? (
               <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-200 backdrop-blur-sm">
                 <AlertTriangle className="mb-2 h-4 w-4" />
                 {labels.noResults}
               </div>
             ) : (
               <div className="space-y-2">
                 {results.map(({ topic, matchedKeywords }) => {
                   const text = getTopicText(topic, isRtl ? 'rtl' : 'ltr');

                   return (
                     <button
                       key={topic.id}
                       type="button"
                       className={`w-full rounded-xl border p-3 text-left transition-all duration-200 ${
                         displayedTopic?.id === topic.id
                           ? 'border-red-500/60 bg-red-500/10 shadow-md shadow-red-500/10'
                           : 'border-slate-800/50 bg-slate-900/60 hover:border-slate-600/50 hover:bg-slate-900/80 hover:translate-x-1'
                       }`}
                       onClick={() => openHelp(topic.id)}
                     >
                       <div className="flex items-start justify-between gap-2">
                         <span className="font-medium text-slate-100">{text.title}</span>
                         <ChevronRight className={`mt-0.5 h-4 w-4 shrink-0 text-slate-500 transition-transform duration-200 rtl:rotate-180 ${displayedTopic?.id === topic.id ? 'text-red-400' : ''}`} />
                       </div>
                       <p className="mt-1 line-clamp-2 text-xs text-slate-400">{text.description}</p>
                       {matchedKeywords.length > 0 && (
                         <div className="mt-2 flex flex-wrap gap-1">
                           {matchedKeywords.slice(0, 3).map((keyword) => (
                             <span
                               key={keyword}
                               className="rounded-full bg-slate-800/70 px-2 py-0.5 text-[10px] text-slate-300"
                             >
                               {keyword}
                             </span>
                           ))}
                         </div>
                       )}
                     </button>
                   );
                 })}
               </div>
             )}
          </nav>

          <section className="min-h-0 overflow-y-auto p-5">
            {displayedTopic && topicText ? (
              <article className="space-y-5 animate-in slide-in-from-right-4 duration-500">
                <div className="rounded-2xl border border-slate-700/50 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/20">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-300 shadow-sm shadow-red-500/10">
                          {getCategoryLabel(displayedTopic.category, isRtl ? 'rtl' : 'ltr')}
                        </span>
                        {displayedTopic.navigateTo && (
                          <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300 shadow-sm shadow-emerald-500/10">
                            {labels.navigationAvailable}
                          </span>
                        )}
                      </div>
                      <h3 className="text-xl font-semibold">{topicText.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-slate-300">{topicText.description}</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-700/50 bg-slate-900/50 p-5 shadow-lg shadow-slate-950/10">
                  <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    {labels.steps}
                  </h4>
                  <ol className="space-y-3">
                    {topicText.steps.map((step, index) => (
                      <li key={step} className="flex gap-3 text-sm text-slate-300">
                        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-800 text-xs font-semibold text-red-300">
                          {index + 1}
                        </span>
                        <span>{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>

                {topicText.warnings.length > 0 && (
                  <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-5 shadow-lg shadow-amber-950/10">
                    <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-100">
                      <AlertTriangle className="h-4 w-4" />
                      {labels.warnings}
                    </h4>
                    <ul className="space-y-2 text-sm text-amber-100">
                      {topicText.warnings.map((warning) => (
                        <li key={warning} className="flex gap-2">
                          <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 rtl:rotate-180" />
                          <span>{warning}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {relatedTopics.length > 0 && (
                  <div className="rounded-2xl border border-slate-700/50 bg-slate-900/50 p-5 shadow-lg shadow-slate-950/10">
                    <h4 className="mb-3 text-sm font-semibold">{labels.relatedTopics}</h4>
                    <div className="flex flex-wrap gap-2">
                      {relatedTopics.map((topic) => {
                        const relatedText = getTopicText(topic, isRtl ? 'rtl' : 'ltr');

                        return (
                          <button
                            key={topic.id}
                            type="button"
                            className="rounded-lg border border-slate-700/50 bg-slate-950/60 px-3 py-2 text-left text-xs text-slate-300 transition-all duration-200 hover:border-red-500/50 hover:bg-red-500/5 hover:text-slate-100 hover:scale-105"
                            onClick={() => openHelp(topic.id)}
                          >
                            {relatedText.title}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  {displayedTopic.navigateTo && (
                    <Button
                      type="button"
                      className="bg-red-600 text-white hover:bg-red-700 shadow-lg shadow-red-500/20 transition-all duration-200 hover:shadow-red-500/30"
                      onClick={handleNavigate}
                    >
                      <ExternalLink className="h-4 w-4" />
                      {labels.openPage}
                    </Button>
                  )}
                </div>
              </article>
            ) : (
              <div className="flex h-full flex-col items-center justify-center text-center text-slate-400 animate-in fade-in duration-300">
                <BookOpenText className="mb-3 h-10 w-10 text-slate-600" />
                <p className="text-sm">{labels.emptyState}</p>
              </div>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
}
