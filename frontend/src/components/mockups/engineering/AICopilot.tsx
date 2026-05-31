import React, { useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { 
  Zap, Mic, Settings, X, Plus, AlertTriangle, FileText, CheckCircle2,
  Cpu, GitPullRequest, ArrowRight, Server, Search, CheckSquare, Eye, Send
} from "lucide-react";

export function AICopilot() {
  const [isListening, setIsListening] = useState(true);

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
              <h2 className="font-bold text-sm tracking-wide text-white">AI Engineering Copilot</h2>
              <div className="text-[10px] text-primary/70 font-mono">NexusAI Pro v3.1</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-white">
              <Settings className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-white">
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
              Array.from({length: 20}).map((_, i) => (
                <div 
                  key={i} 
                  className="w-1 bg-primary rounded-full animate-pulse" 
                  style={{ 
                    height: `${Math.random() * 100}%`,
                    animationDelay: `${i * 0.05}s`,
                    animationDuration: `${0.5 + Math.random()}s`
                  }}
                ></div>
              ))
            ) : (
              <div className="text-xs text-muted-foreground uppercase tracking-widest font-semibold">Voice Inactive</div>
            )}
          </div>
          
          {isListening && (
            <div className="mt-3 text-sm font-medium text-white/90 z-10 text-center">
              "Route cable tray from electrical room to roof"
            </div>
          )}
        </div>

        {/* Chat History */}
        <ScrollArea className="flex-1 p-4">
          <div className="space-y-6">
            
            {/* Message 1: User */}
            <div className="flex flex-col gap-1 items-end">
              <div className="bg-primary/20 text-white px-4 py-3 rounded-2xl rounded-tr-sm text-sm max-w-[85%] border border-primary/20 backdrop-blur-md">
                Check the electrical panel LP-3A for NEC 2023 compliance
              </div>
            </div>

            {/* Message 2: AI */}
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded bg-primary/20 flex items-center justify-center border border-primary/50 shrink-0 shadow-[0_0_10px_rgba(0,168,255,0.2)]">
                <Zap className="h-4 w-4 text-primary" />
              </div>
              <div className="flex flex-col gap-2 w-full">
                <div className="bg-[#1a1d24] border border-white/10 px-4 py-3 rounded-2xl rounded-tl-sm text-sm text-slate-300">
                  <p className="mb-2">Analyzing panel <span className="font-mono text-primary">LP-3A</span>...</p>
                  <p className="text-amber-400 font-medium flex items-center gap-1 mb-2">
                    <AlertTriangle className="h-4 w-4" /> Found 2 compliance issues:
                  </p>
                  <ol className="list-decimal pl-4 space-y-1 mb-3 text-slate-400">
                    <li>Neutral bar spacing does not meet 408.36 requirements.</li>
                    <li>Missing AFCI protection on branch circuits.</li>
                  </ol>
                  <p className="text-xs text-slate-500 italic">Generating compliance report...</p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button variant="outline" size="sm" className="h-7 text-xs bg-transparent border-white/10 hover:bg-white/5">
                    <Eye className="w-3 h-3 mr-1" /> View Issues
                  </Button>
                  <Button variant="outline" size="sm" className="h-7 text-xs bg-primary/10 border-primary/30 text-primary hover:bg-primary/20">
                    <CheckCircle2 className="w-3 h-3 mr-1" /> Auto-Fix
                  </Button>
                  <Button variant="outline" size="sm" className="h-7 text-xs bg-transparent border-white/10 hover:bg-white/5">
                    <FileText className="w-3 h-3 mr-1" /> Generate Report
                  </Button>
                </div>
              </div>
            </div>

            {/* Message 3: User */}
            <div className="flex flex-col gap-1 items-end">
              <div className="bg-primary/20 text-white px-4 py-3 rounded-2xl rounded-tr-sm text-sm max-w-[85%] border border-primary/20 backdrop-blur-md">
                Generate a load calculation for building Tower-B
              </div>
            </div>

            {/* Message 4: AI */}
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded bg-primary/20 flex items-center justify-center border border-primary/50 shrink-0 shadow-[0_0_10px_rgba(0,168,255,0.2)]">
                <Zap className="h-4 w-4 text-primary" />
              </div>
              <div className="flex flex-col gap-2 w-full">
                <div className="bg-[#1a1d24] border border-white/10 px-4 py-3 rounded-2xl rounded-tl-sm text-sm text-slate-300">
                  <p className="mb-3">Running load calculation for <span className="font-mono text-primary">Tower-B</span>...</p>
                  
                  <div className="bg-black/50 border border-white/5 rounded-md overflow-hidden mb-3">
                    <div className="grid grid-cols-2 text-xs border-b border-white/5">
                      <div className="p-2 text-slate-400">Total connected load:</div>
                      <div className="p-2 font-mono text-white text-right">2,847 kVA</div>
                    </div>
                    <div className="grid grid-cols-2 text-xs border-b border-white/5">
                      <div className="p-2 text-slate-400">Demand load:</div>
                      <div className="p-2 font-mono text-primary text-right">1,923 kVA</div>
                    </div>
                    <div className="grid grid-cols-2 text-xs bg-primary/5">
                      <div className="p-2 text-slate-300 font-medium">Rec. service size:</div>
                      <div className="p-2 font-mono text-emerald-400 text-right font-bold">2,500A @ 480V 3Φ</div>
                    </div>
                  </div>
                  
                  <Button variant="link" className="h-auto p-0 text-xs text-primary">See full breakdown <ArrowRight className="w-3 h-3 ml-1" /></Button>
                </div>
              </div>
            </div>

            {/* Message 5: AI (responding to current voice) */}
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded bg-primary flex items-center justify-center border border-primary shrink-0 shadow-[0_0_15px_rgba(0,168,255,0.5)]">
                <Zap className="h-4 w-4 text-background" />
              </div>
              <div className="flex flex-col gap-2 w-full">
                <div className="bg-[#1a1d24] border border-primary/30 shadow-[0_0_15px_rgba(0,168,255,0.05)] px-4 py-3 rounded-2xl rounded-tl-sm text-sm text-slate-300">
                  <p className="mb-2">Routing optimization complete. Optimal path found.</p>
                  <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-3 py-2 rounded text-xs mb-3 flex items-start gap-2">
                    <CheckSquare className="w-4 h-4 shrink-0 mt-0.5" />
                    <div>
                      <strong className="block mb-1">Option A (Recommended)</strong>
                      Saves 23m of cable tray vs current manual routing.
                    </div>
                  </div>
                  <p className="text-sm text-white">Apply this route to the BIM model?</p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" className="h-8 text-xs bg-primary text-primary-foreground hover:bg-primary/90 flex-1">
                    Apply Route
                  </Button>
                  <Button variant="outline" size="sm" className="h-8 text-xs bg-transparent border-white/10 hover:bg-white/5 flex-1">
                    View Options (3)
                  </Button>
                </div>
              </div>
            </div>

            <div className="h-4" /> {/* spacer */}
          </div>
        </ScrollArea>

        {/* Quick Commands */}
        <div className="p-4 border-t border-white/5 bg-[#0f1115]">
          <div className="flex flex-wrap gap-2 mb-3 max-h-24 overflow-y-auto pr-2 scrollbar-thin">
            {[
              "Compliance Check", "Load Calculation", "Arc Flash Study", 
              "Cable Sizing", "Short Circuit Analysis", "Coordination Study", 
              "Generate SLD", "Export Report"
            ].map((cmd) => (
              <Badge key={cmd} variant="outline" className="bg-[#1a1d24] border-white/10 text-slate-300 hover:bg-primary/20 hover:text-primary hover:border-primary/30 cursor-pointer font-normal py-1 px-3">
                {cmd}
              </Badge>
            ))}
          </div>

          <div className="relative flex items-center">
            <Button size="icon" variant="ghost" className="absolute left-1 h-8 w-8 text-muted-foreground z-10">
              <Plus className="h-4 w-4" />
            </Button>
            <Input 
              className="pl-10 pr-10 bg-[#1a1d24] border-white/10 text-sm h-10 rounded-full focus-visible:ring-primary/50" 
              placeholder="Type a command or ask a question..." 
            />
            <Button size="icon" variant="ghost" className="absolute right-1 h-8 w-8 text-primary z-10 hover:bg-primary/10 rounded-full">
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Settings Bar */}
        <div className="h-8 bg-[#0a0a0c] border-t border-white/5 flex items-center justify-between px-4 text-[10px] font-mono text-slate-500">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1"><Cpu className="w-3 h-3" /> Expert</span>
            <span className="flex items-center gap-1"><Server className="w-3 h-3" /> Current Proj</span>
          </div>
          <div className="flex items-center gap-1 text-emerald-500">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div> Connected
          </div>
        </div>
      </div>
    </div>
  );
}
