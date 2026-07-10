/**
 * ExplainButton.tsx - "Explain this result" button for calculation results.
 *
 * A small button that, when clicked, calls POST /api/v1/llm/explain to
 * get an AI explanation of a calculation result. The explanation is
 * displayed in a popover/dialog below the button.
 */
import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Bot, X, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { llmApi } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

export interface ExplainButtonProps {
        /** Type of calculation (e.g. "voltage_drop", "battery_sizing") */
        readonly calculationType: string;
        /** The calculation result JSON to explain */
        readonly result: Record<string, unknown>;
        /** Optional custom question to ask the AI */
        readonly question?: string;
}

export function ExplainButton({
        calculationType,
        result,
        question,
}: ExplainButtonProps) {
        const { t } = useTranslation();
        const [explanation, setExplanation] = useState<string | null>(null);
        const [loading, setLoading] = useState(false);
        const [isOpen, setIsOpen] = useState(false);
        const { toast } = useToast();

        const handleExplain = useCallback(async () => {
                if (loading) return;

                // Toggle: if already open, close it
                if (isOpen && explanation) {
                        setIsOpen(false);
                        return;
                }

                setLoading(true);
                setIsOpen(true);
                setExplanation(null);

                try {
                        const response = await llmApi.explain({
                                calculation_type: calculationType,
                                calculation_result: result,
                                question:
                                        question ||
                                        "Explain this result: what does it mean, is it compliant, and what NFPA 72 / NEC section applies?",
                        });
                        setExplanation(response.content);
                } catch (err: unknown) {
                        const msg =
                                err instanceof Error ? err.message : "Failed to get explanation";
                        toast({
                                title: "AI Explain Error",
                                description: msg,
                                variant: "destructive",
                        });
                        setIsOpen(false);
                } finally {
                        setLoading(false);
                }
        }, [calculationType, result, question, loading, isOpen, explanation, toast]);

        return (
                <div className="relative">
                        <Button
                                variant="ghost"
                                size="sm"
                                onClick={handleExplain}
                                disabled={loading}
                                className="h-7 gap-1.5 text-slate-400 hover:text-red-400 hover:bg-red-600/10 text-xs font-medium"
                        >
                                {loading ? (
                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                        <Bot className="w-3.5 h-3.5" />
                                )}
                                {t("ai.explain", "Explain")}
                        </Button>

                        {isOpen && (explanation || loading) && (
                                <div className="absolute top-full left-0 mt-2 w-96 max-w-[calc(100vw-2rem)] z-30 bg-slate-800 border border-slate-600 rounded-lg shadow-xl">
                                        <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700">
                                                <div className="flex items-center gap-1.5">
                                                        <Bot className="w-3.5 h-3.5 text-red-500" />
                                                        <span className="text-xs font-medium text-slate-200">
                                                                {t("ai.aiExplanation", "AI Explanation")}
                                                        </span>
                                                </div>
                                                <button
                                                        onClick={() => setIsOpen(false)}
                                                        className="text-slate-500 hover:text-slate-300"
                                                        aria-label={t("common.close", "Close")}
                                                >
                                                        <X className="w-3.5 h-3.5" />
                                                </button>
                                        </div>
                                        <div className="px-3 py-2.5 max-h-72 overflow-y-auto">
                                                {loading ? (
                                                        <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
                                                                <Loader2 className="w-3 h-3 animate-spin" />
                                                                {t("ai.thinking", "AI is analyzing...")}
                                                        </div>
                                                ) : (
                                                        <p className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">
                                                                {explanation}
                                                        </p>
                                                )}
                                        </div>
                                        <div className="px-3 py-1.5 border-t border-slate-700 bg-slate-900/50">
                                                <p className="text-[10px] text-slate-500">
                                                        ⚠️ {t("ai.disclaimerShort", "Advisory — verify against NFPA 72")}
                                                </p>
                                        </div>
                                </div>
                        )}
                </div>
        );
}
