export type HelpCategory =
  | 'dashboard'
  | 'projects'
  | 'engineering'
  | 'fire-alarm'
  | 'reports'
  | 'digital-twin'
  | 'elements'
  | 'connections'
  | 'conflicts'
  | 'settings'
  | 'troubleshooting'
  | 'general';

export type HelpTopicId =
  | 'dashboard.overview'
  | 'projects.create'
  | 'projects.manage'
  | 'engineering.overview'
  | 'fire-alarm.detector-placement'
  | 'fire-alarm.symbol-library'
  | 'fire-alarm.zone-navigation'
  | 'reports.generate'
  | 'digital-twin.overview'
  | 'elements.overview'
  | 'connections.create'
  | 'conflicts.overview'
  | 'settings.backend'
  | 'troubleshooting.backend'
  | 'troubleshooting.api'
  | 'troubleshooting.auth'
  | 'troubleshooting.app-crash';

export type HelpLanguage = 'en' | 'ar';
export type HelpTextDirection = 'ltr' | 'rtl';

export interface HelpTopic {
  id: HelpTopicId;
  category: HelpCategory;
  titleEn: string;
  titleAr: string;
  descriptionEn: string;
  descriptionAr: string;
  stepsEn: string[];
  stepsAr: string[];
  warningsEn: string[];
  warningsAr: string[];
  keywords: string[];
  relatedTopics: HelpTopicId[];
  navigateTo?: string;
}

export interface HelpSearchResult {
  topic: HelpTopic;
  score: number;
  matchedKeywords: string[];
}

export interface ContextHelpButtonProps {
  contextId?: HelpTopicId | string;
  size?: 'default' | 'sm' | 'lg' | 'icon';
  className?: string;
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link';
}

export interface SmartHelpDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialContextId?: HelpTopicId | string;
  initialSearch?: string;
}

export interface SmartHelpHookValue {
  openHelp: (contextId?: HelpTopicId | string, search?: string) => void;
  openSearch: (initialQuery?: string) => void;
  closeHelp: () => void;
  isHelpOpen: boolean;
  selectedTopic: HelpTopic | null;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  category: HelpCategory | 'all';
  setCategory: (category: HelpCategory | 'all') => void;
  topics: HelpTopic[];
  results: HelpSearchResult[];
}

export interface SmartHelpContextValue {
  isOpen: boolean;
  isSearchOpen: boolean;
  activeContextId: HelpTopicId | string | null;
  selectedTopicId: HelpTopicId | null;
  query: string;
  category: HelpCategory | 'all';
  openHelp: (contextId?: HelpTopicId | string) => void;
  closeHelp: () => void;
  openSearch: (initialQuery?: string) => void;
  closeSearch: () => void;
  selectTopic: (topicId: HelpTopicId) => void;
  setQuery: (query: string) => void;
  setCategory: (category: HelpCategory | 'all') => void;
  clearFilters: () => void;
}
