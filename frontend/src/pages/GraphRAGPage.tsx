/**
 * GraphRAGPage.tsx — Graph-based Knowledge Retrieval & Q&A.
 *
 * V218: New page — 4 backend endpoints now have UI.
 * Ingest knowledge, ask questions (NL→Cypher→Neo4j), semantic search.
 */
import { useState } from "react";
import { Network, Loader2, Send, Search, Upload, Activity } from "lucide-react";
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
import { v2Api } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

export function GraphRAGPage() {
	const { toast } = useToast();
	const [loading, setLoading] = useState(false);
	const [health, setHealth] = useState<Record<string, unknown> | null>(null);

	// Ask
	const [question, setQuestion] = useState("");
	const [answer, setAnswer] = useState<Record<string, unknown> | null>(null);

	// Search
	const [searchQuery, setSearchQuery] = useState("");
	const [searchResults, setSearchResults] = useState<unknown[]>([]);

	// Ingest
	const [knowledgeText, setKnowledgeText] = useState("");
	const [extractEntities, setExtractEntities] = useState(true);

	const handleHealth = async () => {
		setLoading(true);
		try {
			const res = await v2Api.getGraphragHealth();
			setHealth(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "Health Check Failed",
				description: err instanceof Error ? err.message : "GraphRAG may not be configured",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleAsk = async () => {
		if (!question.trim()) return;
		setLoading(true);
		setAnswer(null);
		try {
			const res = await v2Api.askGraphrag({ question });
			setAnswer(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "Query Failed",
				description: err instanceof Error ? err.message : "GraphRAG query failed",
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
			const res = await v2Api.searchGraphrag({ query: searchQuery, limit: 10 });
			setSearchResults((res as { results?: unknown[] }).results || []);
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

	const handleIngest = async () => {
		if (!knowledgeText.trim()) return;
		setLoading(true);
		try {
			await v2Api.ingestGraphragKnowledge({
				text: knowledgeText,
				extract_entities: extractEntities,
			});
			setKnowledgeText("");
			toast({
				title: "Knowledge Ingested",
				description: "Text processed and entities extracted.",
			});
		} catch (err) {
			toast({
				title: "Ingest Failed",
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
						<Network className="h-5 w-5 text-primary" />
						GraphRAG Knowledge Engine
					</h1>
					<p className="text-sm text-muted-foreground mt-1">
						Natural language Q&A over engineering knowledge graph (Neo4j + LLM)
					</p>
				</div>

				{/* Health Check */}
				<div className="flex items-center gap-3">
					<Button onClick={handleHealth} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Activity className="h-4 w-4" />}
						Check Health
					</Button>
					{health && (
						<div className="flex items-center gap-2">
							{Object.entries(health).map(([key, val]) => (
								<Badge
									key={key}
									variant={val === true || val === "connected" ? "default" : "secondary"}
									className="text-xs"
								>
									{key}: {String(val)}
								</Badge>
							))}
						</div>
					)}
				</div>

				{/* Ask Question */}
				<Card>
					<CardHeader>
						<CardTitle>Ask a Question</CardTitle>
						<CardDescription>
							Natural language query → LLM generates Cypher → Neo4j executes → LLM formulates answer
						</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="space-y-3">
							<div className="flex gap-2">
								<Input
									value={question}
									onChange={(e) => setQuestion(e.target.value)}
									placeholder="e.g., What rooms have insufficient detector coverage?"
									onKeyDown={(e) => e.key === "Enter" && handleAsk()}
								/>
								<Button onClick={handleAsk} disabled={loading || !question.trim()}>
									{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
									Ask
								</Button>
							</div>
							{answer && (
								<div className="space-y-2">
									<Label className="text-xs text-muted-foreground">Answer</Label>
									<pre className="text-sm font-mono bg-muted p-3 rounded-md overflow-auto max-h-60">
										{JSON.stringify(answer, null, 2)}
									</pre>
								</div>
							)}
						</div>
					</CardContent>
				</Card>

				{/* Semantic Search */}
				<Card>
					<CardHeader>
						<CardTitle>Semantic Search</CardTitle>
						<CardDescription>Fast vector similarity search (no LLM call)</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="flex gap-2 mb-4">
							<Input
								value={searchQuery}
								onChange={(e) => setSearchQuery(e.target.value)}
								placeholder="Search for rooms, devices, compliance..."
								onKeyDown={(e) => e.key === "Enter" && handleSearch()}
							/>
							<Button onClick={handleSearch} disabled={loading || !searchQuery.trim()} variant="outline">
								{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
								Search
							</Button>
						</div>
						{searchResults.length > 0 && (
							<div className="space-y-2 max-h-48 overflow-auto">
								{searchResults.map((r, i) => (
									<div key={i} className="text-sm border-b border-border pb-2">
										<pre className="text-xs font-mono text-muted-foreground">
											{JSON.stringify(r, null, 2)}
										</pre>
									</div>
								))}
							</div>
						)}
					</CardContent>
				</Card>

				{/* Ingest Knowledge */}
				<Card>
					<CardHeader>
						<CardTitle>Ingest Knowledge</CardTitle>
						<CardDescription>
							Add engineering text — LLMGraphTransformer extracts entities & relationships
						</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="space-y-3">
							<Textarea
								value={knowledgeText}
								onChange={(e) => setKnowledgeText(e.target.value)}
								placeholder="Paste engineering documentation, code requirements, or project notes..."
								rows={4}
							/>
							<div className="flex items-center gap-4">
								<Button onClick={handleIngest} disabled={loading || !knowledgeText.trim()}>
									{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
									Ingest
								</Button>
								<Button
									onClick={() => setExtractEntities(!extractEntities)}
									variant="ghost"
									size="sm"
									className="text-xs"
								>
									{extractEntities ? "✓ Extract entities" : "Extract entities"}
								</Button>
							</div>
						</div>
					</CardContent>
				</Card>
			</div>
		</div>
	);
}
