// NOSONAR
/**
 * ConversionPanel.tsx — Conversion panel with progress bar
 */

import { ArrowRightLeft, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { digitalTwinService } from "@/services/digitalTwinService";

type ConvertState = "idle" | "converting" | "success" | "error";

export function ConversionPanel() {
	const [sourceFile, setSourceFile] = useState("");
	const [targetFormat, setTargetFormat] = useState("revit");
	const [state, setState] = useState<ConvertState>("idle");
	const [result, setResult] = useState<Record<string, unknown> | null>(null);

	const handleConvert = async () => {
		if (!sourceFile.trim()) {
			toast.error("Please enter a source file path");
			return;
		}
		setState("converting");
		try {
			const res = await digitalTwinService.convert(sourceFile, targetFormat);
			setResult(res as Record<string, unknown>);
			setState("success");
			toast.success("Conversion completed successfully");
		} catch (err) {
			setState("error");
			toast.error(
				`Conversion failed: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
		}
	};

	return (
		<Card className="border-slate-700 bg-slate-800">
			<CardHeader>
				<CardTitle className="flex items-center gap-2 text-slate-100">
					<ArrowRightLeft className="h-5 w-5 text-orange-400" />
					Bidirectional Conversion
				</CardTitle>
				<CardDescription className="text-slate-400">
					Convert between AutoCAD (DWG) and Revit (RVT) formats
				</CardDescription>
			</CardHeader>
			<CardContent className="space-y-4">
				<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
					<div className="space-y-2">
						<Label className="text-slate-300">Source File</Label>
						<Input
							placeholder="/path/to/file.dwg"
							value={sourceFile}
							onChange={(e) => setSourceFile(e.target.value)}
							className="bg-slate-900 border-slate-700 text-slate-100"
						/>
					</div>
					<div className="space-y-2">
						<Label className="text-slate-300">Target Format</Label>
						<select
							value={targetFormat}
							onChange={(e) => setTargetFormat(e.target.value)}
							className="w-full bg-slate-900 border border-slate-700 text-slate-100 rounded-md px-3 py-2 text-sm"
						>
							<option value="revit">Revit (RVT)</option>
							<option value="autocad">AutoCAD (DWG)</option>
							<option value="ifc">IFC</option>
						</select>
					</div>
				</div>
				<Button
					onClick={handleConvert}
					disabled={state === "converting"}
					className="w-full bg-orange-600 hover:bg-orange-700 text-white"
				>
					{state === "converting" ? (
						<>
							<Loader2 className="h-4 w-4 mr-2 animate-spin" />
							Converting...
						</>
					) : (
						<>
							<ArrowRightLeft className="h-4 w-4 mr-2" />
							Convert
						</>
					)}
				</Button>
				{state === "success" && result && (
					<div className="p-3 bg-emerald-600/10 border border-emerald-600/30 rounded-lg">
						<div className="flex items-center gap-2 mb-2">
							<CheckCircle2 className="h-5 w-5 text-emerald-400" />
							<span className="text-sm text-emerald-300">
								Conversion Successful
							</span>
						</div>
						<pre className="text-xs text-slate-400 overflow-auto">
							{JSON.stringify(result, null, 2)}
						</pre>
					</div>
				)}
				{state === "error" && (
					<div className="p-3 bg-red-600/10 border border-red-600/30 rounded-lg">
						<div className="flex items-center gap-2">
							<XCircle className="h-5 w-5 text-red-400" />
							<span className="text-sm text-red-300">Conversion Failed</span>
						</div>
					</div>
				)}
			</CardContent>
		</Card>
	);
}
