/**
 * AICopilot.tsx - AI Engineering Copilot with real LLM integration
 * 
 * V223: Replaced mock UI with real LLM API calls via llmApi.chatStream().
 * Uses the same SSE streaming pattern as AskAiSheet.tsx.
 */

import {
        AlertTriangle,  // NOSONAR: typescript:S1128
        ArrowRight,  // NOSONAR: typescript:S1128
        CheckCircle2,  // NOSONAR: typescript:S1128
        CheckSquare,  // NOSONAR: typescript:S1128
        Cpu,
        Eye,  // NOSONAR: typescript:S1128
        FileText,  // NOSONAR: typescript:S1128
        Mic,
        Plus,
        Send,
        Server,
        Settings,
        Trash2,
        X,
        Zap,
        Loader2,
        Bot,
        User,  // NOSONAR: typescript:S1128
        AlertCircle,
} from "lucide-react";
import { useState, useRef, useEffect, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { llmApi } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

interface ChatMessage {
        role: "user" | "assistant";
        content: string;
        isStreaming?: boolean;
        model?: string;
}

const SYSTEM_PROMPT =
        "You are a licensed fire-protection engineering assistant for the BAZSPARK platform. " +
        "Answer questions about NFPA 72, NEC, fire alarm system design, voltage drop, battery sizing, " +
        "detector placement, and FACP selection. Be precise, cite code sections, and flag non-compliance. " +
        "If unsure, say so. Never invent code requirements.";

const QUICK_COMMANDS = [
        "Compliance Check",
        "Load Calculation",
        "Arc Flash Study",
        "Cable Sizing",
        "Short Circuit Analysis",
        "Coordination Study",
        "Generate SLD",
        "Export Report",
];

export function AICopilot() {
        const { toast } = useToast();
        const [isListening, setIsListening] = useState(true);
        const [messages, setMessages] = useState<ChatMessage[]>([]);
        const [input, setInput] = useState("");
        const [loading, setLoading] = useState(false);
        const scrollRef = useRef<HTMLDivElement>(null);
        const inputRef = useRef<HTMLInputElement>(null);
        const abortRef = useRef<AbortController | null>(null);

        // Auto-scroll to bottom on new messages
        useEffect(() => {
                if (scrollRef.current) {
                        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
                }
        }, [messages, loading]);
        const sendMessage = useCallback(async (content: string) => {
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
                };

                setMessages((prev) => [
                        ...prev,
                        userMessage,
                        { role: "assistant", content: "", isStreaming: true },
                ]);
                setLoading(true);

                try {
                        await llmApi.chatStream(
                                {
                                        prompt: content.trim(),
                                        system: SYSTEM_PROMPT,
                                        temperature: 0.1,
                                        max_tokens: 1500,
                                },
                                controller.signal,
                                // onChunk
                                (chunk: string) => {
                                        setMessages((prev) => {
                                                const updated = [...prev];
                                                const lastMsg = updated[updated.length - 1];  // NOSONAR: typescript:S7755
                                                if (lastMsg && lastMsg.role === "assistant" && lastMsg.isStreaming) {
                                                        updated[updated.length - 1] = {
                                                                ...lastMsg,
                                                                content: lastMsg.content + chunk,
                                                        };
                                                }
                                                return updated;
                                        });
                                },
                                // onDone
                                (done: { content: string; model: string; source: string }) => {
                                        setMessages((prev) => {
                                                const updated = [...prev];
                                                const lastMsg = updated[updated.length - 1];  // NOSONAR: typescript:S7755
                                                if (lastMsg && lastMsg.role === "assistant") {
                                                        updated[updated.length - 1] = {
                                                                ...lastMsg,
                                                                content: done.content || lastMsg.content,
                                                                model: done.model,
                                                                isStreaming: false,
                                                        };
                                                }
                                                return updated;
                                        });
                                },
                                // onError
                                (errMsg: string) => {
                                        setMessages((prev) => {
                                                const updated = [...prev];
                                                const lastMsg = updated[updated.length - 1];  // NOSONAR: typescript:S7755
                                                if (lastMsg && lastMsg.role === "assistant" && lastMsg.isStreaming) {
                                                        updated[updated.length - 1] = {
                                                                ...lastMsg,
                                                                content: lastMsg.content || `(Error: ${errMsg})`,
                                                                isStreaming: false,
                                                        };
                                                }
                                                return updated;
                                        });
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
        }, [loading, toast]);

        const handleSubmit = useCallback(
                (e: React.FormEvent) => {
                        e.preventDefault();
                        if (!input.trim() || loading) return;
                        sendMessage(input);
                        setInput("");
                },
                [input, loading, sendMessage],
        );

        const handleQuickCommand = useCallback(
                (cmd: string) => {
                        if (loading) return;
                        sendMessage(cmd);
                },
                [loading, sendMessage],
        );

        const clearChat = useCallback(() => {
                if (abortRef.current) {
                        abortRef.current.abort();
                }
                setMessages([]);
        }, []);

        return (
                <div className="w-screen h-screen flex justify-end bg-background/50 font-sans dark text-foreground overflow-hidden backdrop-blur-sm">
                        <div className="w-[480px] h-full bg-[#0b0c10] border-l border-primary/20 shadow-2xl flex flex-col relative z-10">
                                {/* Header */}
                                <div className="h-14 flex items-center justify-between px-4 border-b border-white/5 bg-[#0f1115]">
                                        <div className="flex items-center gap-2">
                                                <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center border border-primary/30">
                                                        <Zap className="h-4 w-4 text-primary" />
                                                </div>
                                                <div>
                                                        <h2 className="font-bold text-sm tracking-wide text-white">
                                                                AI Engineering Copilot
                                                        </h2>
                                                        <div className="text-[10px] text-primary/70 font-mono">
                                                                NexusAI Pro v3.1
                                                        </div>
                                                </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                                <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-muted-foreground hover:text-white"
                                                        onClick={clearChat}
                                                        disabled={messages.length === 0 || loading}
                                                >
                                                        <Trash2 className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-muted-foreground hover:text-white"
                                                >
                                                        <Settings className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-muted-foreground hover:text-white"
                                                >
                                                        <X className="h-4 w-4" />
                                                </Button>
                                        </div>
                                </div>

                                {/* Voice Interface */}
                                <div className="p-6 border-b border-white/5 bg-gradient-to-b from-primary/5 to-transparent flex flex-col items-center justify-center relative overflow-hidden">
                                        {/* Animated rings */}
                                        {isListening && (
                                                <>
                                                        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-24 h-24 rounded-full border border-primary/30 animate-[ping_2s_cubic-bezier(0,0,0.2,1)_infinite]"></div>
                                                        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-32 h-32 rounded-full border border-primary/10 animate-[ping_3s_cubic-bezier(0,0,0.2,1)_infinite]"></div>
                                                </>
                                        )}

                                        <button
                                                className={`w-16 h-16 rounded-full flex items-center justify-center z-10 transition-all duration-500 shadow-[0_0_30px_rgba(0,168,255,0.2)] ${isListening ? "bg-primary text-background" : "bg-muted text-muted-foreground hover:bg-muted/80"}`}
                                                onClick={() => setIsListening(!isListening)}
                                        >
                                                <Mic className={`h-6 w-6 ${isListening ? "animate-pulse" : ""}`} />
                                        </button>

                                        <div className="mt-4 flex gap-1 items-end h-8 z-10">
                                                {isListening ? (
                                                        Array.from({ length: 20 }).map((_, i) => (
                                                                <div
                                                                        key={i}
                                                                        className="w-1 bg-primary rounded-full animate-pulse"
                                                                        style={{
                                                                                height: `${crypto.getRandomValues(new Uint32Array(1))[0] / 0xFFFFFFFF * 100}%`,
                                                                                animationDelay: `${i * 0.05}s`,
                                                                                animationDuration: `${0.5 + crypto.getRandomValues(new Uint32Array(1))[0] / 0xFFFFFFFF}s`,
                                                                        }}
                                                                ></div>
                                                        ))
                                                ) : (
                                                        <div className="text-xs text-muted-foreground uppercase tracking-widest font-semibold">
                                                                Voice Inactive
                                                        </div>
                                                )}
                                        </div>

                                        {isListening && (
                                                <div className="mt-3 text-sm font-medium text-white/90 z-10 text-center">
                                                        "Route cable tray from electrical room to roof"
                                                </div>
                                        )}
                                </div>

                                {/* Chat History */}
                                <ScrollArea className="flex-1 p-4" ref={scrollRef}>
                                        <div className="space-y-6">
                                                {messages.length === 0 && (
                                                        <div className="flex flex-col items-center justify-center py-8 text-center">
                                                                <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-3">
                                                                        <Bot className="w-6 h-6 text-primary" />
                                                                </div>
                                                                <p className="text-white/70 text-sm font-medium mb-1">
                                                                        Ask me anything about engineering
                                                                </p>
                                                                <p className="text-muted-foreground text-xs max-w-xs">
                                                                        NFPA 72 spacing, voltage drop, battery sizing, FACP selection, and more
                                                                </p>
                                                        </div>
                                                )}

                                                {messages.map((msg, idx) => (
                                                        msg.role === "user" ? (
                                                                <div key={idx} className="flex flex-col gap-1 items-end">
                                                                        <div className="bg-primary/20 text-white px-4 py-3 rounded-md rounded-tr-sm text-sm max-w-[85%] border border-primary/20 backdrop-blur-md">
                                                                                {msg.content}
                                                                        </div>
                                                                </div>
                                                        ) : (
                                                                <div key={idx} className="flex gap-3">
                                                                        <div className="w-8 h-8 rounded bg-primary/20 flex items-center justify-center border border-primary/50 shrink-0 shadow-[0_0_10px_rgba(0,168,255,0.2)]">
                                                                                <Zap className="h-4 w-4 text-primary" />
                                                                        </div>
                                                                        <div className="flex flex-col gap-2 w-full">
                                                                                <div className="bg-[#1a1d24] border border-white/10 px-4 py-3 rounded-md rounded-tl-sm text-sm text-foreground/90">
                                                                                        {msg.isStreaming && !msg.content ? (
                                                                                                <div className="flex items-center gap-1.5">
                                                                                                        <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
                                                                                                        <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
                                                                                                        <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" />
                                                                                                </div>
                                                                                        ) : (
                                                                                                <>
                                                                                                        <p className="whitespace-pre-wrap break-words">
                                                                                                                {msg.content}
                                                                                                                {msg.isStreaming && (
                                                                                                                        <span className="inline-block w-1.5 h-4 bg-slate-500 ml-0.5 animate-pulse align-text-bottom" />
                                                                                                                )}
                                                                                                        </p>
                                                                                                        {!msg.isStreaming && msg.model && (
                                                                                                                <p className="text-[10px] text-muted-foreground mt-2">
                                                                                                                        Model: {msg.model}
                                                                                                                </p>
                                                                                                        )}
                                                                                                </>
                                                                                        )}
                                                                                </div>
                                                                        </div>
                                                                </div>
                                                        )
                                                ))}

                                                {/* Error state */}
                                                {messages.length > 0 && !loading && messages[messages.length - 1]?.content?.startsWith("(Error:") && (
                                                        <div className="flex items-start gap-2 text-sm text-danger bg-red-950/30 border border-red-900/50 rounded-lg p-3">
                                                                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                                                                <span>Failed to get AI response. Please try again.</span>
                                                        </div>
                                                )}

                                                <div className="h-4" /> {/* spacer */}
                                        </div>
                                </ScrollArea>

                                {/* Quick Commands */}
                                <div className="p-4 border-t border-white/5 bg-[#0f1115]">
                                        <div className="flex flex-wrap gap-2 mb-3 max-h-24 overflow-y-auto pr-2 scrollbar-thin">
                                                {QUICK_COMMANDS.map((cmd) => (
                                                        <Badge
                                                                key={cmd}
                                                                variant="outline"
                                                                className="bg-[#1a1d24] border-white/10 text-foreground/90 hover:bg-primary/20 hover:text-primary hover:border-primary/30 cursor-pointer font-normal py-1 px-3"
                                                                onClick={() => handleQuickCommand(cmd)}
                                                        >
                                                                {cmd}
                                                        </Badge>
                                                ))}
                                        </div>

                                        <form onSubmit={handleSubmit} className="relative flex items-center">
                                                <Button
                                                        type="button"
                                                        size="icon"
                                                        variant="ghost"
                                                        className="absolute left-1 h-8 w-8 text-muted-foreground z-10"
                                                >
                                                        <Plus className="h-4 w-4" />
                                                </Button>
                                                <Input
                                                        ref={inputRef}
                                                        value={input}
                                                        onChange={(e) => setInput(e.target.value)}
                                                        className="pl-10 pr-10 bg-[#1a1d24] border-white/10 text-sm h-10 rounded-full focus-visible:ring-primary/50"
                                                        placeholder="Type a command or ask a question..."
                                                        disabled={loading}
                                                />
                                                <Button
                                                        type="submit"
                                                        size="icon"
                                                        variant="ghost"
                                                        disabled={!input.trim() || loading}
                                                        className="absolute right-1 h-8 w-8 text-primary z-10 hover:bg-primary/10 rounded-full"
                                                >
                                                        {loading ? (
                                                                <Loader2 className="h-4 w-4 animate-spin" />
                                                        ) : (
                                                                <Send className="h-4 w-4" />
                                                        )}
                                                </Button>
                                        </form>
                                </div>

                                {/* Settings Bar */}
                                <div className="h-8 bg-[#0a0a0c] border-t border-white/5 flex items-center justify-between px-4 text-[10px] font-mono text-muted-foreground">
                                        <div className="flex items-center gap-3">
                                                <span className="flex items-center gap-1">
                                                        <Cpu className="w-3 h-3" /> Expert
                                                </span>
                                                <span className="flex items-center gap-1">
                                                        <Server className="w-3 h-3" /> Current Proj
                                                </span>
                                        </div>
                                        <div className="flex items-center gap-1 text-emerald-500">
                                                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>{" "}
                                                {loading ? "Thinking..." : "Connected"}
                                        </div>
                                </div>
                        </div>
                </div>
        );
}