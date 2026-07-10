/**
 * MemoryPage.tsx — Engineering Memory Explorer.
 *
 * V218: New page — 6 backend endpoints now have UI.
 * Store/search/retrieve engineering decisions, preferences, and learned patterns.
 */
import { useState } from "react";
import { Brain, Loader2, Plus, Search, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
import { Textarea } from "@/components/ui/textarea";
import { memoryApi } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

interface MemoryItem {
	id: string;
	content: string;
	metadata?: Record<string, unknown>;
	created_at?: string;
}

export function MemoryPage() {
	const { toast } = useToast();
	const [loading, setLoading] = useState(false);
	const [status, setStatus] = useState<Record<string, unknown> | null>(null);
	const [memories, setMemories] = useState<MemoryItem[]>([]);
	const [searchQuery, setSearchQuery] = useState("");
	const [searchResults, setSearchResults] = useState<MemoryItem[]>([]);
	const [newContent, setNewContent] = useState("");

	const handleStatus = async () => {
		setLoading(true);
		try {
			const res = await memoryApi.getStatus();
			setStatus(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleGetAll = async () => {
		setLoading(true);
		try {
			const res = await memoryApi.getAll();
			setMemories((res as MemoryItem[]) || []);
		} catch (err) {
			toast({
				title: "Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleSearch = async () => {
		if (!searchQuery.trim()) return;
		setLoading(true);
		try {
			const res = await memoryApi.search({ query: searchQuery, limit: 10 });
			setSearchResults((res as { results?: MemoryItem[] }).results || []);
		} catch (err) {
			toast({
				title: "Search Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleAdd = async () => {
		if (!newContent.trim()) return;
		setLoading(true);
		try {
			await memoryApi.add({ content: newContent });
			setNewContent("");
			toast({ title: "Memory added", description: "Engineering note stored." });
			handleGetAll();
		} catch (err) {
			toast({
				title: "Add Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleDelete = async (id: string) => {
		setLoading(true);
		try {
			await memoryApi.delete(id);
			setMemories((prev) => prev.filter((m) => m.id !== id));
			toast({ title: "Deleted", description: "Memory removed." });
		} catch (err) {
			toast({
				title: "Delete Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	return (
		<div className="flex-1 overflow-auto">
			<div className="p-6 max-w-5xl mx-auto space-y-6">
				<div>
					<h1 className="text-lg font-semibold text-foreground flex items-center gap-2">
						<Brain className="h-5 w-5 text-primary" />
						Engineering Memory
					</h1>
					<p className="text-sm text-muted-foreground mt-1">
						Store and retrieve engineering decisions, preferences, and learned patterns
					</p>
				</div>

				{/* Status + Actions */}
				<div className="flex gap-3">
					<Button onClick={handleStatus} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Brain className="h-4 w-4" />}
						Status
					</Button>
					<Button onClick={handleGetAll} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Brain className="h-4 w-4" />}
						Load All
					</Button>
				</div>

				{status && (
					<Card>
						<CardHeader>
							<CardTitle>Memory Service Status</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="grid grid-cols-2 md:grid-cols-4 gap-4">
								{Object.entries(status).map(([key, val]) => (
									<div key={key} className="space-y-1">
										<span className="text-xs text-muted-foreground uppercase tracking-wider">
											{key}
										</span>
										<div className="text-sm font-mono text-foreground">
											{typeof val === "boolean" ? (
												<Badge variant={val ? "default" : "destructive"}>
													{val ? "OK" : "OFF"}
												</Badge>
											) : (
												String(val)
											)}
										</div>
									</div>
								))}
							</div>
						</CardContent>
					</Card>
				)}

				{/* Add New Memory */}
				<Card>
					<CardHeader>
						<CardTitle>Add Engineering Note</CardTitle>
						<CardDescription>Store a decision, preference, or learned pattern</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="space-y-3">
							<Textarea
								value={newContent}
								onChange={(e) => setNewContent(e.target.value)}
								placeholder="e.g., Office building corridor spacing should use 12.5m per NFPA 72 §17.7.3.2.3..."
								rows={3}
							/>
							<Button onClick={handleAdd} disabled={loading || !newContent.trim()}>
								<Plus className="h-4 w-4" />
								Add Memory
							</Button>
						</div>
					</CardContent>
				</Card>

				{/* Search */}
				<Card>
					<CardHeader>
						<CardTitle>Search Memories</CardTitle>
					</CardHeader>
					<CardContent>
						<div className="flex gap-2 mb-4">
							<Input
								value={searchQuery}
								onChange={(e) => setSearchQuery(e.target.value)}
								placeholder="Search engineering notes..."
								onKeyDown={(e) => e.key === "Enter" && handleSearch()}
							/>
							<Button onClick={handleSearch} disabled={loading || !searchQuery.trim()}>
								{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
								Search
							</Button>
						</div>
						{searchResults.length > 0 && (
							<div className="space-y-2">
								{searchResults.map((m) => (
									<div key={m.id} className="text-sm border-b border-border pb-2">
										<p className="text-foreground">{m.content}</p>
										<span className="text-xs text-muted-foreground font-mono">{m.id}</span>
									</div>
								))}
							</div>
						)}
					</CardContent>
				</Card>

				{/* All Memories */}
				{memories.length > 0 && (
					<Card>
						<CardHeader>
							<CardTitle>All Memories ({memories.length})</CardTitle>
						</CardHeader>
						<CardContent>
							<div className="space-y-2 max-h-96 overflow-auto">
								{memories.map((m) => (
									<div
										key={m.id}
										className="flex items-start justify-between gap-3 text-sm border-b border-border pb-2"
									>
										<div className="flex-1 min-w-0">
											<p className="text-foreground truncate">{m.content}</p>
											<span className="text-xs text-muted-foreground font-mono">{m.id}</span>
										</div>
										<Button
											onClick={() => handleDelete(m.id)}
											disabled={loading}
											variant="ghost"
											size="icon"
										>
											<Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
										</Button>
									</div>
								))}
							</div>
						</CardContent>
					</Card>
				)}
			</div>
		</div>
	);
}
