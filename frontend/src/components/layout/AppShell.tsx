import type React from "react";
import Sidebar from "./Sidebar";
import StatusBar from "./StatusBar";
import TopBar from "@/components/layout/TopBar";

interface AppShellProps {
	children: React.ReactNode;
	isConnected: boolean;
	backendUrl: string;
	environment: string;
	onHelpOpen: () => void;
	onSearchOpen?: () => void;
	currentLanguage: string;
	onLanguageChange: (lang: string) => void;
}

const AppShell: React.FC<AppShellProps> = ({
	children,
	isConnected,
	backendUrl,
	environment,
	onHelpOpen,
	onSearchOpen,
	currentLanguage,
	onLanguageChange,
}) => {
	const isRTL = document.documentElement.dir === "rtl";

	return (
		<div
			// V177 UI FIX: Removed gradient + blur overlays that were destroying text contrast.
			// Root cause: AppShell had 3 stacked overlay layers (gradient background,
			// red/orange blur at opacity 30%, grid pattern at opacity 20%) all rendering
			// BEHIND the content but ABOVE the base bg-background. The combined effect
			// washed out text contrast to ~2/10 (per VLM audit), making every page look
			// "dimmed/empty" even when real data was loaded. The overlays may look subtle
			// in Figma but in production they make the UI unusable.
			//
			// Fix: Use a flat solid background (bg-background) with NO overlays. The
			// sidebar and topbar provide enough visual structure. Content area is now
			// clean and high-contrast.
			className="h-screen w-screen flex overflow-hidden bg-background relative"
			dir={isRTL ? "rtl" : "ltr"}
		>
			<Sidebar />

			<div className="flex-1 flex flex-col min-w-0">
				<TopBar
					isConnected={isConnected}
					onHelpOpen={onHelpOpen}
					onSearchOpen={onSearchOpen}
					currentLanguage={currentLanguage}
					onLanguageChange={onLanguageChange}
				/>

				<main className="flex-1 overflow-auto bg-background relative">
					<div className="relative z-10">{children}</div>
				</main>

				<StatusBar
					backendUrl={backendUrl}
					isConnected={isConnected}
					environment={environment}
				/>
			</div>
		</div>
	);
};

export default AppShell;
