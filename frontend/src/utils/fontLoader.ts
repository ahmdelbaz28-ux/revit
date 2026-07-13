/**
 * fontLoader.ts — Non-blocking font loader.
 *
 * V242: Replaces the inline `onload="this.media='all'"` pattern (which
 * violates CSP `script-src 'self'`) with a defer-loaded module that
 * activates the print-media stylesheet once the page is interactive.
 *
 * The stylesheet <link> in index.html has `media="print"` so it doesn't
 * block render. This script finds it and sets `media="all"` after
 * `DOMContentLoaded`, allowing the Inter font to load progressively
 * without affecting FCP.
 */
export function activateProgressiveFonts(): void {
	if (typeof document === "undefined") return;

	// Find all <link rel="stylesheet" media="print"> and activate them.
	const printStylesheets = document.querySelectorAll<HTMLLinkElement>(
		'link[rel="stylesheet"][media="print"]',
	);
	printStylesheets.forEach((link) => {
		link.setAttribute("media", "all");
	});
}

// Auto-activate on DOMContentLoaded (or immediately if already loaded).
if (typeof document !== "undefined") {
	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", activateProgressiveFonts, {
			once: true,
		});
	} else {
		activateProgressiveFonts();
	}
}
