/**
 * GlobalHelpDrawer.tsx — Full help tree + user guide
 *
 * Opens from the TopBar help button. Shows a tree of all help categories
 * with expandable sections. Each topic shows bilingual content (EN/AR).
 * Also serves as the Magic Help target (F1 key opens this with the
 * contextual topic for the current page).
 */
import { useState, useEffect, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronDown, ChevronRight, BookOpen, AlertTriangle, CheckCircle2, Lightbulb } from 'lucide-react';
import { HELP_TREE, ROUTE_HELP_MAP } from '@/help/types';
import { HELP_TOPICS } from '@/help/helpTopics';
import type { HelpTopic, HelpTopicId, HelpTreeNode } from '@/help/types';

interface GlobalHelpDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional topic to show directly (from Magic Help / contextual button) */
  initialTopicId?: HelpTopicId | null;
}

export function GlobalHelpDrawer({ open, onOpenChange, initialTopicId }: GlobalHelpDrawerProps) {
  const location = useLocation();
  const { i18n } = useTranslation();
  const isAr = i18n.language === 'ar';
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [selectedTopicId, setSelectedTopicId] = useState<HelpTopicId | null>(null);

  // When opened with initialTopicId (magic help), select that topic
  useEffect(() => {
    if (initialTopicId) {
      setSelectedTopicId(initialTopicId);
      // Expand the category containing this topic
      const topic = HELP_TOPICS[initialTopicId];
      if (topic) {
        setExpandedCategories((prev) => new Set([...prev, topic.category]));
      }
    } else if (open) {
      // Auto-select topic based on current route
      const routeTopic = ROUTE_HELP_MAP[location.pathname];
      if (routeTopic) {
        setSelectedTopicId(routeTopic);
        const topic = HELP_TOPICS[routeTopic];
        if (topic) {
          setExpandedCategories((prev) => new Set([...prev, topic.category]));
        }
      }
    }
  }, [initialTopicId, open, location.pathname]);

  // Listen for magic help event (F1)
  useEffect(() => {
    const handleMagicHelp = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.topicId) {
        setSelectedTopicId(detail.topicId);
        onOpenChange(true);
      } else {
        // Find topic for current route
        const routeTopic = ROUTE_HELP_MAP[location.pathname];
        if (routeTopic) {
          setSelectedTopicId(routeTopic);
        }
        onOpenChange(true);
      }
    };
    window.addEventListener('fireai:open-help', handleMagicHelp);
    return () => window.removeEventListener('fireai:open-help', handleMagicHelp);
  }, [location.pathname, onOpenChange]);

  const toggleCategory = (cat: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) {
        next.delete(cat);
      } else {
        next.add(cat);
      }
      return next;
    });
  };

  const selectedTopic: HelpTopic | null = selectedTopicId
    ? HELP_TOPICS[selectedTopicId] || null
    : null;

  const totalTopics = useMemo(() => Object.keys(HELP_TOPICS).length, []);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={isAr ? 'left' : 'right'}
        className="w-full sm:w-[600px] bg-slate-900 border-slate-700 p-0 flex flex-col"
      >
        <SheetHeader className="px-6 py-4 border-b border-slate-700 shrink-0">
          <SheetTitle className="flex items-center gap-2 text-slate-100">
            <BookOpen className="h-5 w-5 text-orange-400" />
            {isAr ? 'دليل المستخدم الكامل' : 'Complete User Guide'}
          </SheetTitle>
          <SheetDescription className="text-slate-400">
            {isAr
              ? `${totalTopics} موضوع مساعدة — ثنائي اللغة (عربي/إنجليزي)`
              : `${totalTopics} help topics — bilingual (Arabic/English)`}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 flex overflow-hidden">
          {/* Tree sidebar */}
          <div className="w-56 shrink-0 border-r border-slate-700 overflow-y-auto bg-slate-950/50">
            <ScrollArea className="h-full">
              <div className="p-2 space-y-1">
                {HELP_TREE.map((node) => (
                  <div key={node.category}>
                    <button
                      onClick={() => toggleCategory(node.category)}
                      className="w-full flex items-center gap-1 px-2 py-1.5 rounded text-sm text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
                    >
                      {expandedCategories.has(node.category) ? (
                        <ChevronDown className="h-3 w-3 shrink-0" />
                      ) : (
                        <ChevronRight className="h-3 w-3 shrink-0" />
                      )}
                      <span className="text-base">{node.icon}</span>
                      <span className="truncate">{isAr ? node.labelAr : node.labelEn}</span>
                    </button>
                    {expandedCategories.has(node.category) && (
                      <div className="ml-6 space-y-0.5">
                        {node.topics.map((topicId) => {
                          const topic = HELP_TOPICS[topicId];
                          if (!topic) return null;
                          return (
                            <button
                              key={topicId}
                              onClick={() => setSelectedTopicId(topicId)}
                              className={`w-full text-left px-2 py-1 rounded text-xs transition-colors ${
                                selectedTopicId === topicId
                                  ? 'bg-orange-600/20 text-orange-400 font-medium'
                                  : 'text-slate-500 hover:bg-slate-800 hover:text-slate-300'
                              }`}
                            >
                              {isAr ? topic.titleAr : topic.titleEn}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>

          {/* Topic content */}
          <div className="flex-1 overflow-y-auto">
            <ScrollArea className="h-full">
              {selectedTopic ? (
                <div className="p-6 space-y-4" dir={isAr ? 'rtl' : 'ltr'}>
                  {/* Title */}
                  <div>
                    <h2 className="text-xl font-bold text-slate-100">
                      {isAr ? selectedTopic.titleAr : selectedTopic.titleEn}
                    </h2>
                    <p className="text-sm text-slate-500 mt-1">
                      {isAr ? selectedTopic.titleEn : selectedTopic.titleAr}
                    </p>
                  </div>

                  {/* Bilingual badge */}
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="border-emerald-600/30 text-emerald-400">
                      EN
                    </Badge>
                    <Badge variant="outline" className="border-orange-600/30 text-orange-400">
                      AR
                    </Badge>
                    {selectedTopic.navigateTo && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-xs text-slate-400 hover:text-orange-400"
                        onClick={() => {
                          window.location.href = selectedTopic.navigateTo!;
                        }}
                      >
                        {isAr ? 'اذهب للصفحة' : 'Go to page'} →
                      </Button>
                    )}
                  </div>

                  {/* Description */}
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium text-orange-400">
                      {isAr ? 'الوصف' : 'Description'}
                    </h3>
                    <p className="text-sm text-slate-300">
                      {isAr ? selectedTopic.descriptionAr : selectedTopic.descriptionEn}
                    </p>
                  </div>

                  {/* Steps */}
                  {selectedTopic.stepsEn.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-sm font-medium text-orange-400 flex items-center gap-1">
                        <CheckCircle2 className="h-4 w-4" />
                        {isAr ? 'الخطوات' : 'Steps'}
                      </h3>
                      <ol className="space-y-2">
                        {(isAr ? selectedTopic.stepsAr : selectedTopic.stepsEn).map((step, i) => (
                          <li key={i} className="flex gap-3 text-sm text-slate-300">
                            <span className="shrink-0 w-5 h-5 rounded-full bg-orange-600/20 text-orange-400 flex items-center justify-center text-xs font-bold">
                              {i + 1}
                            </span>
                            <span>{step}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {/* Warnings */}
                  {selectedTopic.warningsEn.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-sm font-medium text-red-400 flex items-center gap-1">
                        <AlertTriangle className="h-4 w-4" />
                        {isAr ? 'تحذيرات' : 'Warnings'}
                      </h3>
                      <ul className="space-y-1">
                        {(isAr ? selectedTopic.warningsAr : selectedTopic.warningsEn).map((w, i) => (
                          <li key={i} className="text-sm text-amber-300 bg-amber-600/10 border border-amber-600/20 rounded p-2">
                            {w}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Related topics */}
                  {selectedTopic.relatedTopics.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-sm font-medium text-blue-400 flex items-center gap-1">
                        <Lightbulb className="h-4 w-4" />
                        {isAr ? 'مواضيع ذات صلة' : 'Related Topics'}
                      </h3>
                      <div className="flex flex-wrap gap-2">
                        {selectedTopic.relatedTopics.map((rtId) => {
                          const rt = HELP_TOPICS[rtId];
                          if (!rt) return null;
                          return (
                            <button
                              key={rtId}
                              onClick={() => setSelectedTopicId(rtId)}
                              className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-400 hover:border-orange-600/30 hover:text-orange-400 transition-colors"
                            >
                              {isAr ? rt.titleAr : rt.titleEn}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-6 text-center text-slate-500">
                  <BookOpen className="h-12 w-12 mx-auto mb-3 opacity-50" />
                  <p>{isAr ? 'اختر موضوعاً من القائمة' : 'Select a topic from the tree'}</p>
                </div>
              )}
            </ScrollArea>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
