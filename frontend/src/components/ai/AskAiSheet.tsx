/**
 * AskAiSheet.tsx - AI Copilot chat widget (side Sheet).
 *
 * A slide-in panel from the right with a chat interface for asking
 * engineering questions to the LLM. Calls POST /api/v1/llm/chat.
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Bot, Send, Sparkles, Trash2, User, AlertCircle } from "lucide-react";
import {
        Sheet,
        SheetContent,
        SheetHeader,
        SheetTitle,
        SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { useLlmChat, type ChatMessage } from "@/hooks/useLlmChat";

export interface AskAiSheetProps {
        readonly open: boolean;
        readonly onOpenChange: (open: boolean) => void;
        /** Context label for the page (e.g. "engineering") — used in system prompt */
        readonly context?: string;
}

const SYSTEM_PROMPT_ENGINEERING =
        "You are a licensed fire-protection engineering assistant for the BAZSPARK platform. " +
        "Answer questions about NFPA 72, NEC, fire alarm system design, voltage drop, battery sizing, " +
        "detector placement, and FACP selection. Be precise, cite code sections, and flag non-compliance. " +
        "If unsure, say so. Never invent code requirements.";

const QUICK_PROMPTS = [
        "What is NFPA 72 smoke detector spacing?",
        "How do I calculate voltage drop?",
        "Explain battery sizing per NFPA 72 §10.6.7",
        "What FACP capacity do I need for 150 devices?",
];

export function AskAiSheet({
        open,
        onOpenChange,
        context = "engineering",
}: AskAiSheetProps) {
        const { t } = useTranslation();
        const [input, setInput] = useState("");
        const { messages, loading, error, sendMessage, clearChat } = useLlmChat(
                SYSTEM_PROMPT_ENGINEERING,
        );
        const scrollRef = useRef<HTMLDivElement>(null);
        const inputRef = useRef<HTMLInputElement>(null);

        // Auto-scroll to bottom on new messages
        useEffect(() => {
                if (scrollRef.current) {
                        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
                }
        }, [messages, loading]);

        // Focus input when sheet opens
        useEffect(() => {
                if (open) {
                        setTimeout(() => inputRef.current?.focus(), 300);
                }
        }, [open]);

        const handleSubmit = useCallback(
                (e: React.FormEvent) => {
                        e.preventDefault();
                        if (!input.trim() || loading) return;
                        sendMessage(input);
                        setInput("");
                },
                [input, loading, sendMessage],
        );

        const handleQuickPrompt = useCallback(
                (prompt: string) => {
                        if (loading) return;
                        sendMessage(prompt);
                },
                [loading, sendMessage],
        );

        return (
                <Sheet open={open} onOpenChange={onOpenChange}>
                        <SheetContent
                                side="right"
                                className="w-[480px] sm:max-w-[480px] p-0 flex flex-col bg-card border-border"
                        >
                                {/* Header */}
                                <SheetHeader className="px-4 py-3 border-b border-border bg-card">
                                        <div className="flex items-center gap-3">
                                                <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-danger/10 border border-red-600/30">
                                                        <Sparkles className="w-5 h-5 text-red-500" />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                        <SheetTitle className="text-foreground text-base font-semibold">
                                                                {t("ai.title", "Ask AI Copilot")}
                                                        </SheetTitle>
                                                        <SheetDescription className="text-muted-foreground text-xs">
                                                                {t("ai.subtitle", "Engineering assistant — NFPA 72 & NEC")}
                                                        </SheetDescription>
                                                </div>
                                                <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        onClick={clearChat}
                                                        disabled={messages.length === 0 || loading}
                                                        title={t("ai.clearChat", "Clear chat")}
                                                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                                                >
                                                        <Trash2 className="w-4 h-4" />
                                                </Button>
                                        </div>
                                </SheetHeader>

                                {/* Messages area */}
                                <ScrollArea className="flex-1 px-4" ref={scrollRef}>
                                        <div className="py-4 space-y-4 min-h-full">
                                                {messages.length === 0 && (
                                                        <div className="flex flex-col items-center justify-center py-12 text-center">
                                                                <div className="w-16 h-16 rounded-full bg-danger/10 flex items-center justify-center mb-4">
                                                                        <Bot className="w-8 h-8 text-red-500" />
                                                                </div>
                                                                <p className="text-foreground/90 text-sm font-medium mb-1">
                                                                        {t("ai.welcome", "Ask me anything about fire alarm engineering")}
                                                                </p>
                                                                <p className="text-muted-foreground text-xs max-w-xs">
                                                                        {t(
                                                                                "ai.welcomeDesc",
                                                                                "NFPA 72 spacing, voltage drop, battery sizing, FACP selection, and more",
                                                                        )}
                                                                </p>
                                                        </div>
                                                )}

                                                {messages.map((msg: ChatMessage, idx: number) => (
                                                        <MessageBubble
                                                                key={`${msg.timestamp}-${idx}`}
                                                                message={msg}
                                                        />
                                                ))}

                                                {loading && (
                                                        <div className="flex items-start gap-2.5">
                                                                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-card flex items-center justify-center">
                                                                        <Bot className="w-4 h-4 text-red-500" />
                                                                </div>
                                                                <div className="bg-card rounded-md rounded-tl-sm px-3.5 py-2.5">
                                                                        <div className="flex items-center gap-1.5">
                                                                                <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
                                                                                <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
                                                                                <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce" />
                                                                        </div>
                                                                </div>
                                                        </div>
                                                )}

                                                {error && (
                                                        <div className="flex items-start gap-2 text-sm text-danger bg-red-950/30 border border-red-900/50 rounded-lg p-3">
                                                                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                                                                <span>{error}</span>
                                                        </div>
                                                )}
                                        </div>
                                </ScrollArea>

                                {/* Quick prompts */}
                                {messages.length === 0 && (
                                        <div className="px-4 py-2 border-t border-slate-800">
                                                <div className="flex flex-wrap gap-1.5">
                                                        {QUICK_PROMPTS.map((prompt) => (
                                                                <Badge
                                                                        key={prompt}
                                                                        variant="outline"
                                                                        className="cursor-pointer text-xs text-foreground/90 border-border hover:border-red-600/50 hover:text-danger transition-colors"
                                                                        onClick={() => handleQuickPrompt(prompt)}
                                                                >
                                                                        {prompt}
                                                                </Badge>
                                                        ))}
                                                </div>
                                        </div>
                                )}

                                {/* Input bar */}
                                <form
                                        onSubmit={handleSubmit}
                                        className="px-4 py-3 border-t border-border bg-card"
                                >
                                        <div className="flex items-center gap-2">
                                                <Input
                                                        ref={inputRef}
                                                        value={input}
                                                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                                                setInput(e.target.value)
                                                        }
                                                        placeholder={t(
                                                                "ai.placeholder",
                                                                "Ask about NFPA 72, voltage drop, battery sizing...",
                                                        )}
                                                        disabled={loading}
                                                        className="flex-1 bg-card border-border text-foreground placeholder:text-muted-foreground focus-visible:ring-red-600"
                                                />
                                                <Button
                                                        type="submit"
                                                        size="icon"
                                                        disabled={!input.trim() || loading}
                                                        className="bg-danger hover:bg-danger/90 text-white flex-shrink-0"
                                                >
                                                        <Send className="w-4 h-4" />
                                                </Button>
                                        </div>
                                        <p className="text-[10px] text-muted-foreground mt-1.5 text-center">
                                                {t(
                                                        "ai.disclaimer",
                                                        "⚠️ AI-generated — verify against NFPA 72 code before use",
                                                )}
                                        </p>
                                </form>
                        </SheetContent>
                </Sheet>
        );
}

/** Single chat message bubble */
function MessageBubble({ message }: { readonly message: ChatMessage }) {
        const isUser = message.role === "user";

        if (isUser) {
                return (
                        <div className="flex items-start gap-2.5 justify-end">
                                <div className="bg-danger text-white rounded-md rounded-tr-sm px-3.5 py-2 max-w-[85%]">
                                        <p className="text-sm whitespace-pre-wrap break-words">
                                                {message.content}
                                        </p>
                                </div>
                                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-secondary flex items-center justify-center">
                                        <User className="w-4 h-4 text-foreground/90" />
                                </div>
                        </div>
                );
        }

        return (
                <div className="flex items-start gap-2.5">
                        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-card flex items-center justify-center">
                                <Bot className="w-4 h-4 text-red-500" />
                        </div>
                        <div className="max-w-[85%]">
                                <div className="bg-card text-foreground rounded-md rounded-tl-sm px-3.5 py-2">
                                        <p className="text-sm whitespace-pre-wrap break-words">
                                                {message.content}
                                                {message.isStreaming && (
                                                        <span className="inline-block w-1.5 h-4 bg-red-500 ml-0.5 animate-pulse align-text-bottom" />
                                                )}
                                        </p>
                                </div>
                                <div className="flex items-center gap-2 mt-1 px-1">
                                        {message.isStreaming ? (
                                                <span className="text-[10px] text-danger animate-pulse">
                                                        typing...
                                                </span>
                                        ) : (
                                                <>
                                                        <span className="text-[10px] text-muted-foreground">{message.model}</span>
                                                        {message.source && (
                                                                <span className="text-[10px] text-muted-foreground/70">· {message.source}</span>
                                                        )}
                                                </>
                                        )}
                                </div>
                        </div>
                </div>
        );
}
