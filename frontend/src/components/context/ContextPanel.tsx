import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, HelpCircle as CircleHelp, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useSmartHelp } from '@/hooks/useSmartHelp';
import type { HelpTopicId } from '@/help/types';

export type ContextPanelKind = 'device' | 'project';
export type ContextPanelStatus = 'normal' | 'active' | 'warning' | 'fault' | 'offline' | 'maintenance';
export type ContextPanelSeverity = 'info' | 'warning' | 'critical';

export interface ContextPanelProperty {
  label: string;
  value: string | number | boolean | null | undefined;
  helper?: string;
}

export interface ContextPanelWarning {
  id: string;
  severity: ContextPanelSeverity;
  title: string;
  message: string;
}

export interface ContextPanelSelection {
  type: ContextPanelKind;
  id: string;
  name: string;
  status: ContextPanelStatus;
  properties: ContextPanelProperty[];
  warnings?: ContextPanelWarning[];
  helpTopicId?: HelpTopicId | string;
}

export interface ContextPanelProps {
  open: boolean;
  selected: ContextPanelSelection | null;
  contextId?: HelpTopicId | string;
  className?: string;
  onClose: () => void;
  onCollapse?: (open: boolean) => void;
}

function getDocumentDirection(): 'ltr' | 'rtl' {
  if (typeof document === 'undefined') return 'ltr';
  return document.documentElement.dir === 'rtl' ? 'rtl' : 'ltr';
}

function getHelpContextId(
  selection: ContextPanelSelection | null,
  contextId?: HelpTopicId | string,
): HelpTopicId | string {
  if (selection?.helpTopicId) return selection.helpTopicId;
  if (contextId) return contextId;

  if (selection?.type === 'project') return 'projects.manage';
  return 'fire-alarm.detector-placement';
}

function formatValue(value: ContextPanelProperty['value']): string {
  if (typeof value === 'boolean') return value ? 'Enabled' : 'Disabled';
  if (value === null || value === undefined) return 'Not set';
  return String(value);
}

function getStatusClasses(status: ContextPanelStatus) {
  switch (status) {
    case 'normal':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
    case 'active':
      return 'border-sky-500/30 bg-sky-500/10 text-sky-300';
    case 'warning':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-300';
    case 'fault':
    case 'offline':
      return 'border-red-500/30 bg-red-500/10 text-red-300';
    case 'maintenance':
      return 'border-slate-500/30 bg-slate-500/10 text-slate-300';
  }
}

function getWarningClasses(severity: ContextPanelSeverity) {
  switch (severity) {
    case 'info':
      return 'border-sky-500/20 bg-sky-500/10 text-sky-200';
    case 'warning':
      return 'border-amber-500/25 bg-amber-500/10 text-amber-200';
    case 'critical':
      return 'border-red-500/30 bg-red-500/10 text-red-200';
  }
}

export function ContextPanel({
  open,
  selected,
  contextId,
  className = '',
  onClose,
  onCollapse,
}: ContextPanelProps) {
  const { openHelp } = useSmartHelp();
  const [documentDirection, setDocumentDirection] = useState<'ltr' | 'rtl'>(getDocumentDirection);
  const isRtl = documentDirection === 'rtl';
  const helpContextId = useMemo(() => getHelpContextId(selected, contextId), [selected, contextId]);
  const visible = open && Boolean(selected);

  useEffect(() => {
    if (!visible) return undefined;

    const updateDirection = () => setDocumentDirection(getDocumentDirection());
    const observer = new MutationObserver(updateDirection);

    updateDirection();
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['dir'] });

    return () => observer.disconnect();
  }, [visible]);

  const handleClose = () => {
    onCollapse?.(false);
    onClose();
  };

  const panelSideClasses = isRtl ? 'left-0 border-r border-slate-800' : 'right-0 border-l border-slate-800';
  const panelTransformClasses = isRtl
    ? visible ? 'translate-x-0' : '-translate-x-full'
    : visible ? 'translate-x-0' : 'translate-x-full';

  return (
    <div
      className={`fixed inset-0 z-[110] ${visible ? 'pointer-events-auto' : 'pointer-events-none'}`}
      dir={isRtl ? 'rtl' : 'ltr'}
      aria-hidden={!visible}
    >
      <div
        className={`absolute inset-0 bg-black/35 transition-opacity duration-300 ${visible ? 'opacity-100' : 'opacity-0'}`}
        onClick={handleClose}
      />

      <aside
        className={`fixed top-0 bottom-0 z-10 flex w-[min(26rem,94vw)] flex-col bg-slate-950/95 text-slate-100 shadow-2xl shadow-black/40 backdrop-blur-xl transition-transform duration-300 ${panelSideClasses} ${panelTransformClasses} ${className}`}
      >
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-800 p-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-xs font-medium uppercase tracking-[0.22em] text-slate-500">
                {selected?.type ?? 'Context'}
              </p>
              {selected && (
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${getStatusClasses(selected.status)}`}>
                  {selected.status}
                </span>
              )}
            </div>
            <h2 className="truncate text-base font-semibold text-slate-100">
              {selected?.name ?? 'No element selected'}
            </h2>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-9 w-9 shrink-0 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
            onClick={handleClose}
            aria-label="Close context panel"
          >
            <X className="h-4 w-4" />
          </Button>
        </header>

        <ScrollArea className="min-h-0 flex-1">
          <div className="space-y-4 p-4">
            {!selected ? (
              <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/50 p-5 text-center text-slate-400">
                <CircleHelp className="mx-auto mb-3 h-8 w-8 text-slate-600" />
                <p className="text-sm">Select a device or project element to inspect its engineering context.</p>
              </div>
            ) : (
              <>
                <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                  <div className="mb-4 flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Selected element</p>
                      <p className="mt-1 font-semibold text-slate-100">{selected.name}</p>
                      <p className="text-xs text-slate-500">{selected.id}</p>
                    </div>
                    <CheckCircle2 className={`mt-1 h-5 w-5 ${selected.status === 'normal' ? 'text-emerald-400' : 'text-red-400'}`} />
                  </div>

                  <div className="space-y-3">
                    {selected.properties.map((property) => (
                      <div key={property.label} className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-xs text-slate-500">{property.label}</span>
                          <span className="text-sm font-medium text-slate-100">{formatValue(property.value)}</span>
                        </div>
                        {property.helper && <p className="mt-1 text-xs text-slate-500">{property.helper}</p>}
                      </div>
                    ))}
                  </div>
                </section>

                <section className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold text-slate-100">Warnings</h3>
                    <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                      {selected.warnings?.length ?? 0}
                    </span>
                  </div>

                  {(selected.warnings?.length ?? 0) > 0 ? (
                    selected.warnings?.map((warning) => (
                      <div key={warning.id} className={`rounded-xl border p-3 ${getWarningClasses(warning.severity)}`}>
                        <div className="mb-1 flex items-center gap-2">
                          <AlertTriangle className="h-4 w-4" />
                          <span className="text-sm font-semibold">{warning.title}</span>
                        </div>
                        <p className="text-sm leading-5">{warning.message}</p>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-emerald-200">
                      No active warnings for this selection.
                    </div>
                  )}
                </section>

                <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                  <h3 className="mb-3 text-sm font-semibold text-slate-100">Related Help</h3>
                  <p className="mb-4 text-sm leading-6 text-slate-400">
                    Open Smart Help for the current {selected.type} context, including troubleshooting steps and safety warnings.
                  </p>
                  <Button
                    type="button"
                    className="w-full bg-red-600 text-white hover:bg-red-700"
                    onClick={() => openHelp(helpContextId)}
                  >
                    <CircleHelp className="h-4 w-4" />
                    Open related help
                  </Button>
                </section>
              </>
            )}
          </div>
        </ScrollArea>
      </aside>
    </div>
  );
}
