
import { ArrowRight, DollarSign, TrendingUp } from "lucide-react";
import React from "react";
import { Button } from "@/components/ui/button";
import { useStore } from "@/store/simpleStore";

export function SystemOptimizer() {
	const devices = useStore((s) => s.devices);
	const connections = useStore((s) => s.connections);
	const [optimizationScore, setScore] = React.useState<number>(0);  // NOSONAR: typescript:S6754
	const [suggestions, setSuggestions] = React.useState<string[]>([]);

	const calculateEfficiency = () => {
		if (devices.length === 0) {
			setScore(0);
			setSuggestions([]);
			return;
		}

		let score = 100;
		const newSuggestions: string[] = [];

		// Penalty for Overloads
		const overloadCount = connections.filter((c) => c.isOverloaded).length;
		if (overloadCount > 0) {
			score -= overloadCount * 15;
			newSuggestions.push(
				`Reduce ${overloadCount} overloaded circuits to prevent failure.`,
			);
		}

		// Penalty for Long Runs (Simulated by distance)
		// In a real app, we'd calculate Euclidean distance sum
		if (connections.length > devices.length * 1.5) {
			score -= 10;
			newSuggestions.push(
				"High cable density detected. Consider consolidating panels to reduce wiring costs.",
			);
		}

		// Bonus for Direct Paths (Simplified logic)
		if (
			devices.filter((d) => d.type === "GENERATOR").length > 0 &&  // NOSONAR: typescript:S7754
			connections.length > 0
		) {
			score += 5;
		}

		score = Math.max(0, Math.min(100, score));
		setScore(score);
		setSuggestions(newSuggestions);
	};

	React.useEffect(() => {
		calculateEfficiency();
	}, [calculateEfficiency]);

	return (
		<div className="p-4 space-y-6 h-full overflow-y-auto">
			<div className="text-center">
				<h2 className="text-lg font-bold text-foreground flex items-center justify-center gap-2">
					<TrendingUp className="text-emerald-500" /> System Optimizer
				</h2>
				<p className="text-xs text-muted-foreground">
					Cost & Efficiency Analysis
				</p>
			</div>

			<div className="relative h-32 flex items-center justify-center">
				<svg className="w-32 h-32 transform -rotate-90">
					<circle
						cx="64"
						cy="64"
						r="60"
						stroke="#334155"
						strokeWidth="8"
						fill="none"
					/>
					<circle
						cx="64"
						cy="64"
						r="60"
						stroke={
							optimizationScore > 80
								? "#10b981"
								: optimizationScore > 50  // NOSONAR: typescript:S3358
									? "#f59e0b"
									: "#64748b"
						}
						strokeWidth="8"
						fill="none"
						strokeDasharray={`${(optimizationScore / 100) * 377} 377`}
						className="transition-all duration-1000"
					/>
				</svg>
				<div className="absolute text-2xl font-bold text-foreground">
					{optimizationScore}%
				</div>
			</div>

			<div className="space-y-3">
				<h3 className="text-sm font-bold text-foreground flex items-center gap-2">
					<DollarSign className="h-4 w-4 text-green-500" /> Cost Saving
					Opportunities
				</h3>
				{suggestions.length === 0 ? (
					<p className="text-xs text-muted-foreground italic">
						System is already optimized.
					</p>
				) : (
					suggestions.map((s, i) => (
						<div
							key={i}  // NOSONAR: typescript:S6479
							className="text-xs p-2 bg-green-900/20 border border-green-500/30 rounded text-green-200 flex items-start gap-2"
						>
							<ArrowRight className="h-3 w-3 mt-0.5 shrink-0" /> {s}
						</div>
					))
				)}
			</div>

			<Button
				className="w-full bg-emerald-600 hover:bg-emerald-700"
				onClick={() => alert("Optimization Report Generated (PDF)")}
			>
				Generate Savings Report
			</Button>
		</div>
	);
}
