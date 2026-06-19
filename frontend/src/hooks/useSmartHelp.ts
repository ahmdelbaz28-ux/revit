import { useEffect, useMemo, useState } from 'react';
import {
  getFallbackHelpTopic,
  getFirstTopicForContext,
  getHelpCategories,
  getHelpTopics,
  searchHelpTopics,
} from '@/help/contextRegistry';
import type { HelpCategory, HelpSearchResult, HelpTopic, HelpTopicId, SmartHelpHookValue } from '@/help/types';

type SmartHelpState = {
  isHelpOpen: boolean;
  selectedTopic: HelpTopic | null;
  searchQuery: string;
  category: HelpCategory | 'all';
  results: HelpSearchResult[];
};

type Listener = (state: SmartHelpState) => void;

const topics = getHelpTopics();
const categories = getHelpCategories();

let helpState: SmartHelpState = {
  isHelpOpen: false,
  selectedTopic: null,
  searchQuery: '',
  category: 'all',
  results: searchHelpTopics('', 'all'),
};

const listeners = new Set<Listener>();

function notifyListeners() {
  for (const listener of listeners) {
    listener(helpState);
  }
}

function setHelpState(patch: Partial<SmartHelpState>) {
  const nextState = {
    ...helpState,
    ...patch,
  };

  helpState = {
    ...nextState,
    results: searchHelpTopics(nextState.searchQuery, nextState.category),
  };

  notifyListeners();
}

function isKnownCategory(category: HelpCategory | 'all'): category is HelpCategory {
  return categories.includes(category as HelpCategory);
}

function getTopicForContext(contextId: HelpTopicId | string | null | undefined, search?: string): HelpTopic | null {
  const context = contextId ?? '';
  const query = search ?? context;

  if (!context && !query) {
    return null;
  }

  return getFirstTopicForContext(context) ?? getFallbackHelpTopic(query) ?? null;
}

export const openHelp = (contextId?: HelpTopicId | string, search = ''): void => {
  setHelpState({
    isHelpOpen: true,
    selectedTopic: getTopicForContext(contextId, search),
    searchQuery: contextId ? search : search,
    category: 'all',
  });
};

export const openSearch = (initialQuery = ''): void => {
  const results = searchHelpTopics(initialQuery, 'all');

  setHelpState({
    isHelpOpen: true,
    selectedTopic: results[0]?.topic ?? null,
    searchQuery: initialQuery,
    category: 'all',
    results,
  });
};

export const closeHelp = (): void => {
  setHelpState({ isHelpOpen: false });
};

export const setSearchQuery = (query: string): void => {
  const results = searchHelpTopics(query, helpState.category);
  const nextSelectedTopic = results[0]?.topic ?? (query.trim() ? null : helpState.selectedTopic);

  setHelpState({
    searchQuery: query,
    selectedTopic: nextSelectedTopic,
    results,
  });
};

export const setCategory = (nextCategory: HelpCategory | 'all'): void => {
  const category = isKnownCategory(nextCategory) ? nextCategory : 'all';
  const results = searchHelpTopics(helpState.searchQuery, category);
  const nextSelectedTopic = results[0]?.topic ?? null;

  setHelpState({
    category,
    selectedTopic: nextSelectedTopic,
    results,
  });
};

export function useSmartHelp(): SmartHelpHookValue {
  const [state, setState] = useState<SmartHelpState>(helpState);

  useEffect(() => {
    const listener: Listener = (nextState) => setState(nextState);
    listeners.add(listener);

    return () => {
      listeners.delete(listener);
    };
  }, []);

  return useMemo<SmartHelpHookValue>(() => ({
    openHelp,
    openSearch,
    closeHelp,
    isHelpOpen: state.isHelpOpen,
    selectedTopic: state.selectedTopic,
    searchQuery: state.searchQuery,
    setSearchQuery,
    category: state.category,
    setCategory,
    topics,
    results: state.results,
  }), [state]);
}
