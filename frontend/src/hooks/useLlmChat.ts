/**
 * useLlmChat.ts - React hook for the AI Copilot LLM chat with SSE streaming.
 *
 * Streams responses token-by-token via POST /api/v1/llm/chat/stream (SSE).
 * Falls back to non-streaming if the stream fails to connect.
 */
import { useCallback, useRef, useState } from "react";
import { llmApi } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

export interface ChatMessage {
	role: "user" | "assistant";
	content: string;
	source?: string;
	model?: string;
	timestamp: number;
	isStreaming?: boolean;
}

export interface UseLlmChatResult {
	messages: ChatMessage[];
	loading: boolean;
	error: string | null;
	sendMessage: (content: string) => Promise<void>;
	clearChat: () => void;
}

/**
 * Hook for AI Copilot chat with SSE streaming.
 * Maintains message history and calls the backend LLM streaming endpoint.
 */
export function useLlmChat(systemPrompt?: string): UseLlmChatResult {
	const [messages, setMessages] = useState<ChatMessage[]>([]);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const { toast } = useToast();
	const abortRef = useRef<AbortController | null>(null);

	const sendMessage = useCallback(
		async (content: string) => {
			if (!content.trim() || loading) return;

			// Abort any in-flight request
			if (abortRef.current) {
				abortRef.current.abort();
			}

			const controller = new AbortController();
			abortRef.current = controller;

			const userMessage: ChatMessage = {
				role: "user",
				content: content.trim(),
				timestamp: Date.now(),
			};

			// Add user message + placeholder assistant message (streaming)
			const assistantTimestamp = Date.now();
			setMessages((prev) => [
				...prev,
				userMessage,
				{
					role: "assistant",
					content: "",
					timestamp: assistantTimestamp,
					isStreaming: true,
				},
			]);
			setLoading(true);
			setError(null);

			try {
				await llmApi.chatStream(
					{
						prompt: content.trim(),
						system: systemPrompt,
						temperature: 0.1,
						max_tokens: 1500,
					},
					controller.signal,
					// onChunk — update the assistant message incrementally
					(chunk: string) => {
						setMessages((prev) => {
							const updated = [...prev];
							const lastMsg = updated[updated.length - 1];
							if (lastMsg && lastMsg.role === "assistant" && lastMsg.isStreaming) {
								updated[updated.length - 1] = {
									...lastMsg,
									content: lastMsg.content + chunk,
								};
							}
							return updated;
						});
					},
					// onDone — finalize the message
					(done: { content: string; model: string; source: string }) => {
						setMessages((prev) => {
							const updated = [...prev];
							const lastMsg = updated[updated.length - 1];
							if (lastMsg && lastMsg.role === "assistant") {
								updated[updated.length - 1] = {
									...lastMsg,
									content: done.content || lastMsg.content,
									model: done.model,
									source: done.source,
									isStreaming: false,
								};
							}
							return updated;
						});
					},
					// onError — mark message as error
					(errMsg: string) => {
						setMessages((prev) => {
							const updated = [...prev];
							const lastMsg = updated[updated.length - 1];
							if (lastMsg && lastMsg.role === "assistant" && lastMsg.isStreaming) {
								updated[updated.length - 1] = {
									...lastMsg,
									content: lastMsg.content || `(Error: ${errMsg})`,
									isStreaming: false,
								};
							}
							return updated;
						});
						setError(errMsg);
						toast({
							title: "AI Error",
							description: errMsg,
							variant: "destructive",
						});
					},
				);
			} catch (err: unknown) {
				if (controller.signal.aborted) return;
				const msg =
					err instanceof Error ? err.message : "Failed to get AI response";
				setError(msg);
				// Remove the empty streaming message
				setMessages((prev) => {
					const last = prev[prev.length - 1];
					if (last && last.role === "assistant" && last.isStreaming && !last.content) {
						return prev.slice(0, -1);
					}
					return prev;
				});
				toast({
					title: "AI Error",
					description: msg,
					variant: "destructive",
				});
			} finally {
				if (abortRef.current === controller) {
					abortRef.current = null;
				}
				setLoading(false);
			}
		},
		[loading, systemPrompt, toast],
	);

	const clearChat = useCallback(() => {
		if (abortRef.current) {
			abortRef.current.abort();
		}
		setMessages([]);
		setError(null);
	}, []);

	return { messages, loading, error, sendMessage, clearChat };
}
