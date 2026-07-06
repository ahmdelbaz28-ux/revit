import { ChevronDown, ChevronUp, Pin, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { actions, useStore } from "@/store/simpleStore";

export function FloatingErrorLog() {
	const errorLog = useStore((s) => s.errorLog);
	const [isExpanded, setIsExpanded] = useState(true);
	const [isPinned, setIsPinned] = useState(false);

	const handleClear = () => {
		actions.clearErrors();
	};

	const handleFocus = (elementId?: string) => {
		if (elementId) {
			actions.setSelectedElement(elementId);
		}
	};

	if (errorLog.length === 0 && !isPinned) {
		return null; // Hide if no errors and not pinned
	}

	return (
		<div
			className={`flex flex-col border-t bg-card/95 backdrop-blur-md transition-all duration-300 ease-in-out shrink-0 overflow-hidden ${isPinned ? "h-48" : isExpanded ? "h-48" : "h-7"} ${isPinned ? "relative" : "fixed bottom-6 left-0 right-0 z-50"}`}
		>
			{/* Header */}
			<div
				className="h-7 flex items-center justify-between px-2 border-b cursor-pointer select-none shrink-0 bg-red-950/10"
				onClick={{() => !isPinned && setIsExpanded(!isExpanded) onKeyDown={(e) => e.key === "Enter" && {() => !isPinned && setIsExpanded(!isExpanded)}			>
				<div className="flex items-center gap-3">
					<div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
					<span className="text-[11px] font-semibold uppercase tracking-wider text-foreground">
						سجل الأخطاء الحقيقي
					</span>
					<div className="flex gap-1.5 items-center">
						<Badge
							variant="destructive"
							className="h-4 text-[9px] px-1.5 py-0 border-red-500/50 bg-red-500"
						>
							{errorLog.length} New
						</Badge>
					</div>
				</div>
				<div className="flex items-center gap-2">
					<Button
						variant="ghost"
						size="icon"
						className={`h-5 w-5 ${isPinned ? "text-primary" : "text-muted-foreground"}`}
						onClick={{{(e) => {							e.stopPropagation();							setIsPinned(!isPinned);
						}}
					>
						<Pin className="h-3 w-3" />
					</Button>
					<Button
						variant="ghost"
						size="icon"
						className="h-5 w-5 text-muted-foreground hover:text-foreground"
						onClick={{{(e) => {							e.stopPropagation();							handleClear();
						}}
					>
						<Trash2 className="h-3 w-3" />
					</Button>
					<Button
						variant="ghost"
						size="icon"
						className="h-5 w-5 text-muted-foreground hover:text-foreground"
					>
						{isExpanded ? (
							<ChevronDown className="h-3 w-3" />
						) : (
							<ChevronUp className="h-3 w-3" />
						)}
					</Button>
				</div>
			</div>

			{/* Content */}
			<div
				className={`flex-1 overflow-hidden transition-opacity duration-200 ${isExpanded || isPinned ? "opacity-100" : "opacity-0 pointer-events-none"}`}
			>
				<ScrollArea className="h-full w-full font-mono text-xs">
					<div className="flex flex-col">
						{errorLog.map((err) => (
							<div
								key={err.id}
								className="flex items-center px-4 py-1.5 border-b border-border/30 hover:bg-muted/30 group bg-red-950/20 border-l-2 border-l-red-500 cursor-pointer"
								onClick={{() => handleFocus(err.elementId) onKeyDown={(e) => e.key === "Enter" && {() => handleFocus(err.elementId)}							>
								<div className="w-[80px] shrink-0 text-muted-foreground">
									{new Date(err.timestamp).toLocaleTimeString()}
								</div>
								<div className="w-[60px] shrink-0">
									<span className="text-red-400">ERROR</span>
								</div>
								<div className="flex-1 text-slate-300 truncate pr-4">
									{err.message}
								</div>
								<div className="shrink-0 flex items-center gap-4 opacity-0 group-hover:opacity-100 transition-opacity">
									{err.elementId && (
										<span className="text-blue-400 hover:underline text-[10px]">
											Go To
										</span>
									)}
								</div>
							</div>
						))}
					</div>
				</ScrollArea>
			</div>
		</div>
	);
}
