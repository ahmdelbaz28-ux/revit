// NOSONAR
import { Book, FileText, LifeBuoy, X } from "lucide-react";

interface HelpDrawerProps {
	helpOpen: boolean;
	onHelpToggle: () => void;
}

export function HelpDrawer({ helpOpen, onHelpToggle }: HelpDrawerProps) {  // NOSONAR - typescript:S6759
	return (
		<div
			className={`absolute top-14 right-0 bottom-0 w-80 bg-card border-l border-border shadow-xl transform transition-transform duration-300 ease-in-out z-50 ${
				helpOpen ? "translate-x-0" : "translate-x-full"
			}`}
		>
			<div className="h-full flex flex-col">
				<div className="h-14 flex items-center justify-between px-6 border-b border-border bg-muted/50">
					<div className="text-sm font-bold flex items-center gap-2">
						<Book className="h-4 w-4 text-primary" />
						<span>NexusCAD Help Center</span>
					</div>
					<button
						onClick={onHelpToggle}
						className="p-1.5 rounded-md hover:bg-muted transition-colors"
					>
						<X className="h-4 w-4" />
					</button>
				</div>

				<div className="flex-1 overflow-y-auto p-6 space-y-6">
					{/* Simulated Markdown Content */}
					<div className="prose prose-sm dark:prose-invert">
						<div className="flex items-center gap-2 text-primary font-bold mb-1">
							<FileText className="h-4 w-4" />
							<span>User Guide: Fault Handling</span>
						</div>
						<div className="text-xs text-muted-foreground leading-relaxed">
							Welcome to the NexusCAD Pro simulation environment. This section
							guides you through handling simulated faults.
						</div>

						<div className="h-px bg-border my-4" />

						<h4 className="text-xs font-bold uppercase mb-2">
							1. Visual Indicators
						</h4>
						<p className="text-xs text-muted-foreground">
							When a fault is injected, the affected component will pulse with a
							red border and an alert icon will appear. This indicates a
							critical state requiring attention.
						</p>

						<h4 className="text-xs font-bold uppercase mb-2 mt-4">
							2. Corrective Actions
						</h4>
						<ul className="text-xs text-muted-foreground list-disc pl-4 space-y-1">
							<li>Isolate the faulty component.</li>
							<li>
								Route power through the backup battery bank if the main
								generator fails.
							</li>
							<li>Verify load flow constraints before re-energizing.</li>
						</ul>
					</div>

					<div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg flex items-start gap-3">
						<LifeBuoy className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
						<div>
							<div className="text-xs font-bold text-blue-500">
								Need Expert Support?
							</div>
							<div className="text-[10px] text-blue-400 mt-0.5 leading-relaxed">
								Contact our engineering support team for complex fault analysis
								or system integration questions.
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}

export default HelpDrawer;
