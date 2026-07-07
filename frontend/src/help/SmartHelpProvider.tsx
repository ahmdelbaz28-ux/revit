/**
 * SmartHelpProvider.tsx — Legacy stub (V140 Phase 7)
 *
 * The full help system is now in GlobalHelpDrawer.tsx + ContextualHelpButton.tsx.
 * This file is kept as a stub for backward compatibility with any code that
 * still imports it.
 */
import { createContext, type ReactNode } from "react";
import type { SmartHelpContextValue } from "./types";

export const SmartHelpContext = createContext<SmartHelpContextValue | null>(
	null,
);

const noop = () => {};

const defaultValue: SmartHelpContextValue = {
	open: false,
	setOpen: noop,
	searchQuery: "",
	setSearchQuery: noop,
	selectedTopicId: null,
	setSelectedTopicId: noop,
	topics: [],
	categories: [],
	searchResults: [],
	navigateToTopic: noop,
};

export function SmartHelpProvider({ children }: { children: ReactNode }) {  // NOSONAR - typescript:S6759
	return (
		<SmartHelpContext.Provider value={defaultValue}>
			{children}
		</SmartHelpContext.Provider>
	);
}
