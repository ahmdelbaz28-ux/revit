
/**
 * ConfigEditor.tsx — JSON config editor with validation
 */

import { AlertCircle, CheckCircle2, Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

interface ConfigEditorProps {
	title: string;
	description?: string;
	loadConfig: () => Promise<Record<string, unknown>>;
	saveConfig: (config: Record<string, unknown>) => Promise<void>;
}

export function ConfigEditor({
	title,
	description,
	loadConfig,
	saveConfig,
}: ConfigEditorProps) {
	const [configText, setConfigText] = useState("");
	const [original, setOriginal] = useState("");
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		const load = async () => {
			setLoading(true);
			try {
				const config = await loadConfig();
				const text = JSON.stringify(config, null, 2);
				setConfigText(text);
				setOriginal(text);
			} catch (err) {
				setError(err instanceof Error ? err.message : "Failed to load config");
				setConfigText("{}");
			} finally {
				setLoading(false);
			}
		};
		load();
	}, [loadConfig]);

	const validate = (): Record<string, unknown> | null => {
		try {
			const parsed = JSON.parse(configText);
			setError(null);
			return parsed;
		} catch (e) {
			setError(e instanceof Error ? e.message : "Invalid JSON");
			return null;
		}
	};

	const handleSave = async () => {
		const parsed = validate();
		if (!parsed) {
			toast.error("Cannot save: invalid JSON");
			return;
		}
		setSaving(true);
		try {
			await saveConfig(parsed);
			setOriginal(configText);
			toast.success("Configuration saved successfully");
		} catch (err) {
			toast.error(
				`Save failed: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
		} finally {
			setSaving(false);
		}
	};

	const hasChanges = configText !== original;

	return (
		<Card className="border-border bg-card">
			<CardHeader>
				<CardTitle className="text-foreground">{title}</CardTitle>
				{description && (
					<CardDescription className="text-muted-foreground">
						{description}
					</CardDescription>
				)}
			</CardHeader>
			<CardContent className="space-y-3">
				{loading ? (
					<div className="h-64 bg-card rounded animate-pulse" />
				) : (
					<>
						<div className="flex items-center gap-2">
							{error ? (
								<Badge variant="destructive" className="gap-1">
									<AlertCircle className="h-3 w-3" /> Invalid JSON
								</Badge>
							) : (
								<Badge
									variant="outline"
									className="border-emerald-600/30 text-success gap-1"
								>
									<CheckCircle2 className="h-3 w-3" /> Valid JSON
								</Badge>
							)}
							{hasChanges && (
								<Badge
									variant="outline"
									className="border-amber-600/30 text-warning"
								>
									Unsaved changes
								</Badge>
							)}
						</div>
						<Textarea
							value={configText}
							onChange={(e) => {
								setConfigText(e.target.value);
								validate();
							}}
							className="font-mono text-sm bg-card border-border text-foreground min-h-[300px]"
							spellCheck={false}
						/>
						{error && <p className="text-xs text-danger font-mono">{error}</p>}
						<Button
							onClick={handleSave}
							disabled={!hasChanges || saving || !!error}
							className="bg-primary hover:bg-orange-700 text-white"
						>
							{saving ? (
								<>
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									Saving...
								</>
							) : (
								<>
									<Save className="h-4 w-4 mr-2" />
									Save Configuration
								</>
							)}
						</Button>
					</>
				)}
			</CardContent>
		</Card>
	);
}
