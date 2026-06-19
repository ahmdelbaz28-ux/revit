import React, { createContext, useCallback, useMemo, useState } from 'react';
import type { HelpCategory, HelpTopicId, SmartHelpContextValue } from './types';

interface SmartHelpProviderProps {
  children: React.ReactNode;
}

export const SmartHelpContext = createContext<SmartHelpContextValue | null>(null);

export function SmartHelpProvider({ children }: SmartHelpProviderProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [activeContextId, setActiveContextId] = useState<HelpTopicId | string | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<HelpTopicId | null>(null);
  const [query, setQueryState] = useState('');
  const [category, setCategoryState] = useState<HelpCategory | 'all'>('all');

  const openHelp = useCallback((contextId?: HelpTopicId | string) => {
    setActiveContextId(contextId ?? null);
    setSelectedTopicId(null);
    setQueryState('');
    setCategoryState('all');
    setIsSearchOpen(false);
    setIsOpen(true);
  }, []);

  const closeHelp = useCallback(() => {
    setIsOpen(false);
    setIsSearchOpen(false);
  }, []);

  const openSearch = useCallback((initialQuery = '') => {
    setQueryState(initialQuery);
    setIsSearchOpen(true);
    setSelectedTopicId(null);
    setIsOpen(true);
  }, []);

  const closeSearch = useCallback(() => {
    setIsSearchOpen(false);
  }, []);

  const selectTopic = useCallback((topicId: HelpTopicId) => {
    setSelectedTopicId(topicId);
    setActiveContextId(topicId);
    setIsSearchOpen(false);
    setIsOpen(true);
  }, []);

  const setQuery = useCallback((nextQuery: string) => {
    setQueryState(nextQuery);
    setSelectedTopicId(null);
    setIsSearchOpen(true);
  }, []);

  const setCategory = useCallback((nextCategory: HelpCategory | 'all') => {
    setCategoryState(nextCategory);
    setSelectedTopicId(null);
    setIsSearchOpen(true);
  }, []);

  const clearFilters = useCallback(() => {
    setQueryState('');
    setCategoryState('all');
    setSelectedTopicId(null);
  }, []);

  const value = useMemo<SmartHelpContextValue>(() => ({
    isOpen,
    isSearchOpen,
    activeContextId,
    selectedTopicId,
    query,
    category,
    openHelp,
    closeHelp,
    openSearch,
    closeSearch,
    selectTopic,
    setQuery,
    setCategory,
    clearFilters,
  }), [
    isOpen,
    isSearchOpen,
    activeContextId,
    selectedTopicId,
    query,
    category,
    openHelp,
    closeHelp,
    openSearch,
    closeSearch,
    selectTopic,
    setQuery,
    setCategory,
    clearFilters,
  ]);

  return (
    <SmartHelpContext.Provider value={value}>
      {children}
    </SmartHelpContext.Provider>
  );
}
