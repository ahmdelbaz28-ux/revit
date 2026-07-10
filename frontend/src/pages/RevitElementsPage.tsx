
/**
 * RevitElementsPage.tsx — View and manage Revit elements
 */

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { type ElementItem, ElementList } from "@/components/shared/ElementList";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { revitService } from "@/services/revitService";

export function RevitElementsPage() {
	const [elements, setElements] = useState<ElementItem[]>([]);
	const [loading, setLoading] = useState(true);

	const fetchElements = useCallback(async () => {
		setLoading(true);
		try {
			const result = await revitService.getElements();
			const items = Array.isArray(result)
				? result
				: (result as { elements?: unknown[] })?.elements || [];
			setElements(items as ElementItem[]);
		} catch (err) {
			toast.error(
				`Failed to load elements: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
			setElements([]);
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		fetchElements();
	}, [fetchElements]);

	const handleView = (el: ElementItem) => {
		toast.info(`Viewing element: ${el.name} (${el.id})`);
	};

	const handleDelete = async (el: ElementItem) => {
		try {
			await revitService.deleteElement(el.id);
			toast.success(`Deleted element: ${el.name}`);
			fetchElements();
		} catch (err) {
			toast.error(
				`Delete failed: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
		}
	};

	return (
		<div className="flex-1 overflow-auto p-6 max-w-6xl mx-auto space-y-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-2xl font-bold text-foreground">Revit Elements</h1>
					<p className="text-sm text-muted-foreground mt-1">
						View, filter, and manage Revit elements
					</p>
				</div>
				<Button
					onClick={fetchElements}
					variant="outline"
					className="border-border text-foreground/90"
				>
					<RefreshCw className="h-4 w-4 mr-2" /> Refresh
				</Button>
			</div>
			<Card className="border-border bg-card">
				<CardHeader>
					<CardTitle className="text-foreground">
						Elements ({elements.length})
					</CardTitle>
				</CardHeader>
				<CardContent>
					<ElementList
						elements={elements}
						loading={loading}
						onView={handleView}
						onDelete={handleDelete}
					/>
				</CardContent>
			</Card>
		</div>
	);
}
