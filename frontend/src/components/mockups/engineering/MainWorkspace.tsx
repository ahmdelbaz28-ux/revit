// NOSONAR
import {
        Activity,
        AlertTriangle,
        ArrowRight,
        Bell,
        Box,
        CheckSquare,
        ChevronDown,
        ChevronUp,
        Cloud,
        Cpu,
        Crosshair,
        Eye,
        EyeOff,
        FileText,
        Focus,
        FolderOpen,
        Layers,
        Layout,
        Lock,
        Maximize,
        Menu,
        Mic,
        MinusSquare,
        Monitor,
        PenTool,
        Pin,
        Plus,
        Settings,
        Trash2,
        Triangle,
        User,
        Volume2,
        X,
        Zap,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function MainWorkspace() {
        const [activeTab, setActiveTab] = useState("Electrical");
        const [activeFile, setActiveFile] = useState("Tower-B-Electrical.dwg");
        const [isErrorLogExpanded, setIsErrorLogExpanded] = useState(true);
        const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
        const [isErrorLogPinned, setIsErrorLogPinned] = useState(false);
        const [isListening, setIsListening] = useState(false);
        const [voiceCommand, setVoiceCommand] = useState("");

        return (
                <div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground font-sans">
                        {/* Top Ribbon */}
                        <div className="h-24 flex flex-col border-b bg-card">
                                {/* Top bar */}
                                <div className="h-10 flex items-center justify-between px-4 border-b border-border/50">
                                        <div className="flex items-center gap-4">
                                                <div className="flex items-center gap-2 text-primary">
                                                        <Zap className="h-5 w-5 fill-current" />
                                                        <span className="font-bold tracking-wider text-sm">
                                                                NexusCAD Pro
                                                        </span>
                                                </div>
                                                <Separator orientation="vertical" className="h-5" />
                                                <div className="flex text-xs space-x-1">
                                                        {[
                                                                "File",
                                                                "Edit",
                                                                "View",
                                                                "Insert",
                                                                "Annotate",
                                                                "Structure",
                                                                "Electrical",
                                                                "BIM",
                                                                "AI",
                                                                "Collaborate",
                                                                "Tools",
                                                                "Help",
                                                        ].map((tab) => (
                                                                <button
                                                                        key={tab}
                                                                        className={`px-3 py-1 rounded-sm transition-colors ${activeTab === tab ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted"}`}
                                                                        onClick={() => setActiveTab(tab)} onKeyDown={(e) => { if (e.key === "Enter") (() => setActiveTab(tab))(); }}                                                            >
                                                                        {tab}
                                                                </button>
                                                        ))}
                                                </div>
                                        </div>
                                        <div className="flex items-center gap-4 text-muted-foreground">
                                                <div className="flex items-center gap-2 text-xs">
                                                        <Cloud className="h-4 w-4 text-emerald-400" />
                                                        <span>Synced</span>
                                                </div>
                                                <Separator orientation="vertical" className="h-5" />
                                                <div className="flex items-center gap-2 text-xs">
                                                        <Cpu className="h-4 w-4" />
                                                        <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                                                                <div className="bg-primary h-full w-[45%]"></div>
                                                        </div>
                                                </div>
                                                <Separator orientation="vertical" className="h-5" />
                                                <Bell className="h-4 w-4 hover:text-foreground cursor-pointer" />
                                                <div className="h-6 w-6 rounded-full bg-primary/20 border border-primary/50 flex items-center justify-center text-xs font-bold text-primary">
                                                        JS
                                                </div>
                                        </div>
                                </div>
                                {/* Sub-ribbon */}
                                <div className="h-14 flex items-center px-2 space-x-1 bg-card/50 overflow-x-auto">
                                        {activeTab === "Electrical" && (
                                                <>
                                                        <RibbonBtn icon={<MinusSquare />} label="New Wire" />
                                                        <RibbonBtn icon={<Plus />} label="Add Component" />
                                                        <Separator orientation="vertical" className="h-8 mx-1" />
                                                        <RibbonBtn icon={<Layout />} label="Bus Bar" />
                                                        <RibbonBtn icon={<Layers />} label="Cable Tray" />
                                                        <RibbonBtn icon={<Monitor />} label="Panel Board" />
                                                        <RibbonBtn icon={<Zap />} label="Circuit Breaker" />
                                                        <RibbonBtn icon={<ArrowRight />} label="Ground Symbol" />
                                                        <Separator orientation="vertical" className="h-8 mx-1" />
                                                        <RibbonBtn icon={<Activity />} label="Load Calc" />
                                                        <RibbonBtn
                                                                icon={<Zap className="text-amber-400" />}
                                                                label="Arc Flash"
                                                        />
                                                        <RibbonBtn icon={<Lock />} label="Protection Relay" />
                                                </>
                                        )}
                                </div>
                        </div>

                        <div className="flex flex-1 overflow-hidden">
                                {/* Left Explorer (Project Manager Sidebar) */}
                                <div
                                        className={`${isSidebarCollapsed ? "w-12" : "w-60"} flex flex-col border-r bg-card/30 transition-all duration-300 overflow-hidden`}
                                >
                                        <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b flex justify-between items-center bg-card/50">
                                                {!isSidebarCollapsed && <span>Project Manager</span>}
                                                <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-5 w-5"
                                                        onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)} onKeyDown={(e) => { if (e.key === "Enter") (() => setIsSidebarCollapsed(!isSidebarCollapsed))(); }}                                          >
                                                        <Menu className="h-3 w-3" />
                                                </Button>
                                        </div>
                                        <ScrollArea className="flex-1">
                                                <div
                                                        className={`p-2 text-sm ${isSidebarCollapsed ? "hidden" : "block"}`}
                                                >
                                                        <TreeNode title="Tower-B Project" defaultOpen>
                                                                <TreeNode title="Drawings & Models" defaultOpen>
                                                                        <FileNode
                                                                                title="Single Line Diagram (SLD)"
                                                                                type="dwg"
                                                                                active={activeFile === "SLD"}
                                                                                onClick={() => setActiveFile("SLD")} onKeyDown={(e) => { if (e.key === "Enter") (() => setActiveFile("SLD"))(); }}                                                                      />
                                                                        <FileNode
                                                                                title="Cabling Network"
                                                                                type="dwg"
                                                                                active={activeFile === "Cabling"}
                                                                                onClick={() => setActiveFile("Cabling")} onKeyDown={(e) => { if (e.key === "Enter") (() => setActiveFile("Cabling"))(); }}                                                                      />
                                                                        <FileNode
                                                                                title="Connected Devices"
                                                                                type="dwg"
                                                                                active={activeFile === "Devices"}
                                                                                onClick={() => setActiveFile("Devices")} onKeyDown={(e) => { if (e.key === "Enter") (() => setActiveFile("Devices"))(); }}                                                                      />
                                                                </TreeNode>
                                                                <TreeNode title="Project Elements" defaultOpen>
                                                                        <TreeNode title="SLD Elements">
                                                                                <FileNode title="Transformers" type="rvt" />
                                                                                <FileNode title="Switchgears" type="rvt" />
                                                                        </TreeNode>
                                                                        <TreeNode title="Cabling Systems">
                                                                                <FileNode title="HV Cables" type="xlsx" />
                                                                                <FileNode title="LV Cables" type="xlsx" />
                                                                        </TreeNode>
                                                                </TreeNode>
                                                                <TreeNode title="Analysis & Reports" defaultOpen>
                                                                        <FileNode
                                                                                title="Report Manager"
                                                                                type="xlsx"
                                                                                active={activeFile === "Reports"}
                                                                                onClick={() => setActiveFile("Reports")} onKeyDown={(e) => { if (e.key === "Enter") (() => setActiveFile("Reports"))(); }}                                                                      />
                                                                </TreeNode>
                                                                <TreeNode title="System Settings" defaultOpen>
                                                                        <FileNode title="Preferences" type="xlsx" />
                                                                        <FileNode title="Project Config" type="xlsx" />
                                                                </TreeNode>
                                                        </TreeNode>
                                                </div>
                                                {isSidebarCollapsed && (
                                                        <div className="flex flex-col items-center gap-4 py-4">
                                                                <FileText
                                                                        className="h-5 w-5 text-muted-foreground cursor-pointer"
                                                                        onClick={() => setIsSidebarCollapsed(false)} onKeyDown={(e) => { if (e.key === "Enter") (() => setIsSidebarCollapsed(false))(); }}                                                              />
                                                                <Zap
                                                                        className="h-5 w-5 text-muted-foreground cursor-pointer"
                                                                        onClick={() => setIsSidebarCollapsed(false)} onKeyDown={(e) => { if (e.key === "Enter") (() => setIsSidebarCollapsed(false))(); }}                                                              />
                                                                <Layout
                                                                        className="h-5 w-5 text-muted-foreground cursor-pointer"
                                                                        onClick={() => setIsSidebarCollapsed(false)} onKeyDown={(e) => { if (e.key === "Enter") (() => setIsSidebarCollapsed(false))(); }}                                                              />
                                                        </div>
                                                )}
                                        </ScrollArea>

                                        <div className="h-1/3 flex flex-col border-t bg-card/20">
                                                <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b flex justify-between items-center bg-card/40">
                                                        <span>Layer Manager</span>
                                                        <Settings className="h-3 w-3" />
                                                </div>
                                                <ScrollArea className="flex-1 p-2">
                                                        <LayerRow name="Grid" color="bg-slate-500" />
                                                        <LayerRow name="Walls" color="bg-zinc-400" />
                                                        <LayerRow name="Electrical" color="bg-primary" active />
                                                        <LayerRow name="Lighting" color="bg-yellow-400" />
                                                        <LayerRow name="HVAC" color="bg-blue-300" hidden />
                                                        <LayerRow name="Plumbing" color="bg-cyan-400" hidden />
                                                        <LayerRow name="Structural" color="bg-orange-500" locked />
                                                        <LayerRow name="Annotations" color="bg-green-400" />
                                                </ScrollArea>
                                        </div>
                                </div>

                                {/* Central Canvas */}
                                <div className="flex-1 flex flex-col relative bg-[#0f1115]">
                                        {/* File Tabs */}
                                        <div className="flex border-b bg-card">
                                                {[
                                                        "Tower-B-Electrical.dwg",
                                                        "Fire-Alarm-Plan.dwg",
                                                        "BIM-Model.rvt",
                                                        "Load-Calc.xlsx",
                                                ].map((file) => (
                                                        <div  // NOSONAR — S6848: type assertion acceptable
                                                                key={file}
                                                                className={`px-4 py-2 text-xs border-r flex items-center gap-2 cursor-pointer ${activeFile === file ? "bg-[#0f1115] text-primary border-t-2 border-t-primary" : "text-muted-foreground hover:bg-muted"}`}
                                                                onClick={() => setActiveFile(file)} onKeyDown={(e) => { if (e.key === "Enter") (() => setActiveFile(file))(); }}                                                        >
                                                                {file.endsWith(".dwg") ? (
                                                                        <Layout className="h-3 w-3" />
                                                                ) : (
                                                                        <Box className="h-3 w-3" />
                                                                )}
                                                                {file}
                                                                <X className="h-3 w-3 ml-2 opacity-50 hover:opacity-100" />
                                                        </div>
                                                ))}
                                        </div>

                                        {/* Canvas area */}
                                        <div
                                                className="flex-1 relative overflow-hidden flex"
                                                style={{
                                                        backgroundImage: "radial-gradient(#1e293b 1px, transparent 1px)",
                                                        backgroundSize: "20px 20px",
                                                }}
                                        >
                                                {/* Rulers */}
                                                <div className="absolute top-0 left-6 right-0 h-6 bg-card/80 border-b flex items-end overflow-hidden z-10">
                                                        <div
                                                                className="w-full border-b border-muted-foreground/30 relative"
                                                                style={{ height: "5px" }}
                                                        >
                                                                {Array.from({ length: 40 }).map((_, i) => (
                                                                        <div
                                                                                key={i}  // NOSONAR — S6479: array index key acceptable for static list
                                                                                className="absolute border-l border-muted-foreground/30 h-full"
                                                                                style={{ left: `${i * 50}px` }}
                                                                        ></div>
                                                                ))}
                                                        </div>
                                                </div>
                                                <div className="absolute top-0 bottom-0 left-0 w-6 bg-card/80 border-r flex justify-end overflow-hidden z-10">
                                                        <div
                                                                className="h-full border-r border-muted-foreground/30 relative"
                                                                style={{ width: "5px" }}
                                                        >
                                                                {Array.from({ length: 20 }).map((_, i) => (
                                                                        <div
                                                                                key={i}  // NOSONAR — S6479: array index key acceptable for static list
                                                                                className="absolute border-t border-muted-foreground/30 w-full"
                                                                                style={{ top: `${i * 50}px` }}
                                                                        ></div>
                                                                ))}
                                                        </div>
                                                </div>

                                                {/* Drawing Content */}
                                                <div className="absolute inset-0 pt-6 pl-6 overflow-hidden">
                                                        {activeFile === "Reports" ? (
                                                                <div className="p-6 text-foreground h-full overflow-auto">
                                                                        <h2 className="text-xl font-bold mb-4 text-primary">
                                                                                Report Manager (Comparison Mode)
                                                                        </h2>
                                                                        <div className="grid grid-cols-2 gap-4">
                                                                                <div className="p-4 border rounded bg-card/50">
                                                                                        <h3 className="font-semibold mb-2 text-primary">
                                                                                                Result A (Current)
                                                                                        </h3>
                                                                                        <p className="text-sm text-muted-foreground">
                                                                                                Load Flow Analysis - Rev 14
                                                                                        </p>
                                                                                        <div className="mt-2 text-emerald-400 font-mono text-sm">
                                                                                                Status: Optimal
                                                                                        </div>
                                                                                        <div className="mt-4 space-y-2 text-xs font-mono">
                                                                                                <div>Bus 1 Voltage: 1.02 pu</div>
                                                                                                <div>Bus 2 Voltage: 0.98 pu</div>
                                                                                                <div>Total Losses: 12.4 kW</div>
                                                                                        </div>
                                                                                </div>
                                                                                <div className="p-4 border rounded bg-card/50">
                                                                                        <h3 className="font-semibold mb-2 text-primary">
                                                                                                Result B (Previous)
                                                                                        </h3>
                                                                                        <p className="text-sm text-muted-foreground">
                                                                                                Load Flow Analysis - Rev 13
                                                                                        </p>
                                                                                        <div className="mt-2 text-orange-400 font-mono text-sm">
                                                                                                Status: 2 Warnings
                                                                                        </div>
                                                                                        <div className="mt-4 space-y-2 text-xs font-mono">
                                                                                                <div>Bus 1 Voltage: 1.01 pu</div>
                                                                                                <div>Bus 2 Voltage: 0.94 pu (Low)</div>
                                                                                                <div>Total Losses: 15.8 kW</div>
                                                                                        </div>
                                                                                </div>
                                                                        </div>
                                                                        <div className="mt-4 p-4 border rounded border-red-500/50 bg-red-500/10">
                                                                                <h3 className="font-semibold text-red-400 mb-2 flex items-center gap-2">
                                                                                        <AlertTriangle className="h-4 w-4" />
                                                                                        Clash Detection / Conflicts
                                                                                </h3>
                                                                                <p className="text-sm text-foreground">
                                                                                        Bus 2 Voltage in Result B violates the minimum limit of
                                                                                        0.95 pu. Result A resolves this by upgrading the cable
                                                                                        size on run EL-C-047.
                                                                                </p>
                                                                        </div>
                                                                </div>
                                                        ) : (
                                                                <>
                                                                        {/* Fake diagram elements */}
                                                                        <div className="absolute top-32 left-40 w-64 h-80 border-2 border-slate-600 rounded-sm"></div>
                                                                        <div className="absolute top-[180px] left-40 w-[600px] h-0.5 bg-primary"></div>
                                                                        <div className="absolute top-[280px] left-40 w-[450px] h-0.5 bg-primary"></div>
                                                                        <div className="absolute top-[380px] left-40 w-[550px] h-0.5 bg-primary"></div>

                                                                        <div className="absolute top-[170px] left-[640px] w-8 h-12 border-2 border-primary bg-[#0f1115] z-10"></div>
                                                                        <div className="absolute top-[270px] left-[490px] w-8 h-12 border-2 border-primary bg-[#0f1115] z-10"></div>
                                                                        <div className="absolute top-[370px] left-[590px] w-8 h-12 border-2 border-primary bg-[#0f1115] z-10"></div>

                                                                        {/* Selected Element */}
                                                                        <div className="absolute top-[140px] left-32 w-16 h-100 border border-primary/50 bg-primary/10 backdrop-blur-sm shadow-[0_0_15px_rgba(0,168,255,0.2)] flex items-center justify-center group cursor-pointer z-10">
                                                                                <div className="absolute -top-6 text-[10px] text-primary whitespace-nowrap font-mono">
                                                                                        LP-3A [400A]
                                                                                </div>
                                                                                <div className="w-2 h-2 rounded-full bg-primary absolute -top-1 -left-1"></div>
                                                                                <div className="w-2 h-2 rounded-full bg-primary absolute -top-1 -right-1"></div>
                                                                                <div className="w-2 h-2 rounded-full bg-primary absolute -bottom-1 -left-1"></div>
                                                                                <div className="w-2 h-2 rounded-full bg-primary absolute -bottom-1 -right-1"></div>
                                                                        </div>

                                                                        {/* Dimensions */}
                                                                        <div className="absolute top-28 left-40 w-64 border-t border-dashed border-emerald-500/50 flex justify-center items-center h-4">
                                                                                <div className="px-2 bg-[#0f1115] text-[10px] text-emerald-400 font-mono">
                                                                                        4200mm
                                                                                </div>
                                                                        </div>
                                                                </>
                                                        )}
                                                </div>

                                                {/* Floating Mini Toolbar */}
                                                <div className="absolute top-10 right-4 bg-card/80 backdrop-blur border rounded-md shadow-lg flex flex-col p-1 gap-1 z-20">
                                                        <ToolBtn icon={<Crosshair />} active />
                                                        <ToolBtn icon={<Maximize />} />
                                                        <ToolBtn icon={<Focus />} />
                                                        <Separator />
                                                        <ToolBtn icon={<PenTool />} />
                                                        <ToolBtn icon={<Triangle />} />
                                                </div>

                                                {/* Canvas Footer */}
                                                <div className="absolute bottom-4 right-4 flex items-center gap-2 z-20 font-mono text-[10px] text-muted-foreground bg-card/80 backdrop-blur px-2 py-1 rounded border">
                                                        <span>Zoom: 1:50</span>
                                                        <Separator orientation="vertical" className="h-3" />
                                                        <span>X: 2847.32 Y: 1203.48</span>
                                                </div>
                                        </div>
                                </div>

                                {/* Right Panel */}
                                <div className="w-80 flex flex-col border-l bg-card/30">
                                        {/* Properties Panel */}
                                        <div className="h-1/2 flex flex-col border-b">
                                                <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b flex justify-between items-center bg-card/40">
                                                        <span>Object Properties</span>
                                                        <Settings className="h-3 w-3" />
                                                </div>
                                                <ScrollArea className="flex-1">
                                                        <div className="p-3">
                                                                <div className="flex items-center gap-2 mb-4">
                                                                        <div className="h-8 w-8 rounded bg-primary/20 flex items-center justify-center">
                                                                                <Monitor className="h-4 w-4 text-primary" />
                                                                        </div>
                                                                        <div>
                                                                                <div className="font-medium text-sm">Panel Board LP-3A</div>
                                                                                <div className="text-[10px] text-muted-foreground font-mono">
                                                                                        ID: ELEC-PNL-8932
                                                                                </div>
                                                                        </div>
                                                                </div>

                                                                <div className="space-y-3">
                                                                        <PropRow label="Voltage" value="480V" />
                                                                        <PropRow label="Phases" value="3" />
                                                                        <PropRow label="Ampacity" value="400A" />
                                                                        <PropRow label="Frame Size" value="600A" />
                                                                        <PropRow label="Manufacturer" value="Eaton Corp" />
                                                                        <PropRow label="Location" value="Level 3, Elec Rm B" />

                                                                        <div className="pt-2 border-t mt-2">
                                                                                <div className="flex justify-between items-center text-xs mb-1">
                                                                                        <span className="text-muted-foreground">Compliance</span>
                                                                                        <Badge
                                                                                                variant="outline"
                                                                                                className="text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
                                                                                        >
                                                                                                <CheckSquare className="w-3 h-3 mr-1" /> NFPA 70
                                                                                        </Badge>
                                                                                </div>
                                                                        </div>

                                                                        <div className="pt-2 border-t mt-2">
                                                                                <div className="text-xs text-muted-foreground mb-1">
                                                                                        Remarks
                                                                                </div>
                                                                                <div className="text-xs p-2 rounded bg-muted/50 border italic">
                                                                                        Requires 36" clearance in front per NEC 110.26
                                                                                </div>
                                                                        </div>
                                                                </div>
                                                        </div>
                                                </ScrollArea>
                                        </div>

                                        {/* AI Copilot mini */}
                                        <div className="flex-1 flex flex-col bg-card/20">
                                                <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-primary border-b flex items-center gap-2 bg-card/40">
                                                        <Zap className="h-3 w-3" />
                                                        <span>AI Copilot</span>
                                                </div>
                                                <ScrollArea className="flex-1 p-3">
                                                        <div className="space-y-4">
                                                                <div className="flex flex-col gap-1 items-end">
                                                                        <div className="bg-primary/20 text-foreground px-3 py-2 rounded-lg rounded-tr-none text-xs max-w-[85%] border border-primary/20">
                                                                                Check the load on LP-3A
                                                                        </div>
                                                                        <div className="text-[9px] text-muted-foreground">14:28</div>
                                                                </div>

                                                                <div className="flex gap-2">
                                                                        <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center text-primary-foreground shrink-0 mt-1">
                                                                                <Zap className="h-3 w-3" />
                                                                        </div>
                                                                        <div className="flex flex-col gap-1">
                                                                                <div className="bg-muted px-3 py-2 rounded-lg rounded-tl-none text-xs text-foreground border">
                                                                                        Panel LP-3A is currently loaded at 285A (71% of 400A
                                                                                        capacity).
                                                                                        <br />
                                                                                        <br />
                                                                                        <span className="text-emerald-400 font-mono">
                                                                                                Status: Safe
                                                                                        </span>
                                                                                        <br />
                                                                                        Remaining capacity: 115A.
                                                                                </div>
                                                                                <div className="flex gap-1 mt-1">
                                                                                        <Badge
                                                                                                variant="secondary"
                                                                                                className="text-[10px] cursor-pointer hover:bg-secondary/80"
                                                                                        >
                                                                                                View Details
                                                                                        </Badge>
                                                                                        <Badge
                                                                                                variant="secondary"
                                                                                                className="text-[10px] cursor-pointer hover:bg-secondary/80"
                                                                                        >
                                                                                                Generate Report
                                                                                        </Badge>
                                                                                </div>
                                                                        </div>
                                                                </div>
                                                        </div>
                                                </ScrollArea>

                                                <div className="p-2 border-t bg-card/50">
                                                        <div className="flex gap-1 mb-2 overflow-x-auto pb-1 scrollbar-hide">
                                                                <Badge
                                                                        variant="outline"
                                                                        className="text-[10px] whitespace-nowrap cursor-pointer"
                                                                >
                                                                        Check Compliance
                                                                </Badge>
                                                                <Badge
                                                                        variant="outline"
                                                                        className="text-[10px] whitespace-nowrap cursor-pointer"
                                                                >
                                                                        Suggest Routing
                                                                </Badge>
                                                        </div>
                                                        <div className="relative">
                                                                <Input
                                                                        className="pr-8 bg-background border-muted text-xs h-8"
                                                                        placeholder={isListening ? "Listening..." : "Ask Copilot..."}
                                                                        value={voiceCommand}
                                                                        onChange={(e) => setVoiceCommand(e.target.value)}
                                                                />
                                                                <Button
                                                                        size="icon"
                                                                        variant="ghost"
                                                                        className={`absolute right-0 top-0 h-8 w-8 ${isListening ? "text-red-500 animate-pulse" : "text-primary"}`}
                                                                        onClick={() => {                                                                                setIsListening(!isListening);                                                                           if (!isListening) {
                                                                                        setVoiceCommand("Processing voice command...");
                                                                                        setTimeout(
                                                                                                () => setVoiceCommand("Show me active clashes"),
                                                                                                1500,
                                                                                        );
                                                                                } else {
                                                                                        setVoiceCommand("");
                                                                                }
                                                                        }}
                                                                >
                                                                        {isListening ? (
                                                                                <Volume2 className="h-4 w-4" />
                                                                        ) : (
                                                                                <Mic className="h-4 w-4" />
                                                                        )}
                                                                </Button>
                                                        </div>
                                                </div>
                                        </div>
                                </div>
                        </div>

                        {/* Global Error Log Bar */}
                        <div
                                className={`flex flex-col border-t bg-card/95 backdrop-blur-md transition-all duration-300 ease-in-out shrink-0 overflow-hidden ${isErrorLogPinned ? "h-48" : isErrorLogExpanded ? "h-48" : "h-7"}`}  // NOSONAR — S3358: nested ternary acceptable in this localized context
                        >
                                {/* Header row (always visible) */}
                                <div  // NOSONAR — S6848: type assertion acceptable
                                        className="h-7 flex items-center justify-between px-2 border-b cursor-pointer select-none shrink-0 bg-red-950/10"
                                        onClick={() =>                                          !isErrorLogPinned && setIsErrorLogExpanded(!isErrorLogExpanded)                                 }
                                >
                                        <div className="flex items-center gap-3">
                                                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
                                                <span className="text-[11px] font-semibold uppercase tracking-wider text-foreground">
                                                        Global Error Log
                                                </span>
                                                <div className="flex gap-1.5 items-center">
                                                        <Badge
                                                                variant="destructive"
                                                                className="h-4 text-[9px] px-1.5 py-0 border-red-500/50 bg-red-500"
                                                        >
                                                                3 New
                                                        </Badge>
                                                        <Badge
                                                                variant="outline"
                                                                className="h-4 text-[9px] px-1.5 py-0 text-orange-400 border-orange-500/50 bg-orange-500/10"
                                                        >
                                                                5 Warnings
                                                        </Badge>
                                                </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                                <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className={`h-5 w-5 ${isErrorLogPinned ? "text-primary" : "text-muted-foreground"}`}
                                                        onClick={(e) => {                                                               e.stopPropagation();                                                            setIsErrorLogPinned(!isErrorLogPinned);
                                                        }}
                                                >
                                                        <Pin className="h-3 w-3" />
                                                </Button>
                                                <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-5 w-5 text-muted-foreground hover:text-foreground"
                                                        onClick={(e) => {                                                               e.stopPropagation();                                                    }}
                                                >
                                                        <Trash2 className="h-3 w-3" />
                                                </Button>
                                                <Separator orientation="vertical" className="h-4" />
                                                <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-5 w-5 text-muted-foreground hover:text-foreground"
                                                >
                                                        {isErrorLogExpanded ? (
                                                                <ChevronDown className="h-3 w-3" />
                                                        ) : (
                                                                <ChevronUp className="h-3 w-3" />
                                                        )}
                                                </Button>
                                        </div>
                                </div>

                                {/* Expanded Content */}
                                <div
                                        className={`flex-1 overflow-hidden transition-opacity duration-200 ${isErrorLogExpanded ? "opacity-100" : "opacity-0 pointer-events-none"}`}
                                >
                                        <ScrollArea className="h-full w-full font-mono text-xs">
                                                <div className="flex flex-col">
                                                        <LogEntry
                                                                level="ERROR"
                                                                time="14:47:03"
                                                                source="NEC Compliance"
                                                                message="Panel LP-3A: Neutral bar spacing violates NEC §408.36 — clearance 38mm < 50mm required"
                                                        />
                                                        <LogEntry
                                                                level="ERROR"
                                                                time="14:46:51"
                                                                source="Load Calculator"
                                                                message="MDB-B overloaded: demand 978A exceeds 800A bus rating (122.3%)"
                                                        />
                                                        <LogEntry
                                                                level="ERROR"
                                                                time="14:45:22"
                                                                source="Arc Flash"
                                                                message="Panel LP-3A: Arc flash label missing. Incident energy 52.4 cal/cm² — PPE Cat 4 required"
                                                        />
                                                        <LogEntry
                                                                level="WARN"
                                                                time="14:44:10"
                                                                source="BIM Sync"
                                                                message="IFC export: 3 elements skipped — unsupported geometry type (IFCBSPLINECURVE)"
                                                        />
                                                        <LogEntry
                                                                level="WARN"
                                                                time="14:43:38"
                                                                source="Clash Detection"
                                                                message="5 new soft clashes detected in MEP zone — Level 2, Grid C–E / 3–6"
                                                        />
                                                        <LogEntry
                                                                level="WARN"
                                                                time="14:42:15"
                                                                source="Cable Sizing"
                                                                message="Cable run EL-C-047: voltage drop 4.8% approaching 5% limit"
                                                        />
                                                        <LogEntry
                                                                level="WARN"
                                                                time="14:41:02"
                                                                source="File System"
                                                                message="Auto-save delayed 12s — large file lock on BIM-Model.rvt"
                                                        />
                                                        <LogEntry
                                                                level="WARN"
                                                                time="14:40:30"
                                                                source="Collaboration"
                                                                message="User Marcus Williams connection timeout — changes may not be synced"
                                                        />
                                                        <LogEntry
                                                                level="INFO"
                                                                time="14:38:44"
                                                                source="System"
                                                                message="BIM model synchronized with Revit v14 — 2,847 elements updated"
                                                        />
                                                        <LogEntry
                                                                level="INFO"
                                                                time="14:37:21"
                                                                source="Analysis"
                                                                message="Load flow converged — Newton-Raphson, 7 iterations, tolerance 0.0001 pu"
                                                        />
                                                        <LogEntry
                                                                level="INFO"
                                                                time="14:36:05"
                                                                source="Compliance"
                                                                message="NFPA 72 check complete — 127 items passed, 2 warnings"
                                                        />
                                                        <LogEntry
                                                                level="INFO"
                                                                time="14:35:00"
                                                                source="System"
                                                                message="Auto-save complete — 5 files, 47MB"
                                                        />
                                                </div>
                                        </ScrollArea>
                                </div>
                        </div>

                        {/* Status Bar */}
                        <div className="h-6 flex items-center justify-between px-4 bg-primary/10 border-t border-primary/20 text-[10px] font-mono text-primary/80 shrink-0">
                                <div className="flex items-center gap-4">
                                        <span>X: 2847.32 Y: 1203.48</span>
                                        <Separator orientation="vertical" className="h-3 bg-primary/20" />
                                        <span>Snap: ON</span>
                                        <Separator orientation="vertical" className="h-3 bg-primary/20" />
                                        <span>Grid: 5mm</span>
                                        <Separator orientation="vertical" className="h-3 bg-primary/20" />
                                        <span>Layer: Electrical</span>
                                </div>
                                <div className="flex items-center gap-4">
                                        <span>Project: Tower-B</span>
                                        <Separator orientation="vertical" className="h-3 bg-primary/20" />
                                        <span>Rev: 14</span>
                                        <Separator orientation="vertical" className="h-3 bg-primary/20" />
                                        <span>Last saved: 2 min ago</span>
                                        <Separator orientation="vertical" className="h-3 bg-primary/20" />
                                        <div className="flex items-center gap-1">
                                                <User className="h-3 w-3" />
                                                <span>3 online</span>
                                        </div>
                                </div>
                        </div>
                </div>
        );
}

function LogEntry({  // NOSONAR - typescript:S6759
        level,
        time,
        source,
        message,
}: {
        level: "ERROR" | "WARN" | "INFO";
        time: string;
        source: string;
        message: string;
}) {
        const isError = level === "ERROR";
        const isWarn = level === "WARN";

        return (
                <div
                        className={`flex items-center px-4 py-1.5 border-b border-border/30 hover:bg-muted/30 group ${isError ? "bg-red-950/20 border-l-2 border-l-red-500" : isWarn ? "bg-orange-950/20 border-l-2 border-l-orange-500" : "border-l-2 border-l-transparent"}`}  // NOSONAR — S3358: nested ternary acceptable in this localized context
                >
                        <div className="w-[80px] shrink-0 text-muted-foreground">{time}</div>
                        <div className="w-[60px] shrink-0">
                                <span
                                        className={`${isError ? "text-red-400" : isWarn ? "text-orange-400" : "text-slate-400"}`}  // NOSONAR — S3358: nested ternary acceptable in this localized context
                                >
                                        {level}
                                </span>
                        </div>
                        <div className="w-[130px] shrink-0 text-slate-500 truncate pr-4">
                                {source}
                        </div>
                        <div className="flex-1 text-slate-300 truncate pr-4">{message}</div>
                        <div className="shrink-0 flex items-center gap-4 opacity-0 group-hover:opacity-100 transition-opacity">
                                {level !== "INFO" && (
                                        <span className="text-blue-400 hover:underline cursor-pointer">
                                                Go To
                                        </span>
                                )}
                                <X className="h-3 w-3 text-muted-foreground hover:text-foreground cursor-pointer" />
                        </div>
                </div>
        );
}

function RibbonBtn({ icon, label }: { icon: React.ReactNode; label: string }) {  // NOSONAR - typescript:S6759
        return (
                <div className="flex flex-col items-center justify-center w-16 h-12 rounded hover:bg-muted cursor-pointer transition-colors group">
                        <div className="text-muted-foreground group-hover:text-primary mb-1 [&>svg]:w-4 [&>svg]:h-4">
                                {icon}
                        </div>
                        <span className="text-[9px] text-center leading-tight whitespace-nowrap px-1 overflow-hidden text-ellipsis w-full text-muted-foreground group-hover:text-foreground">
                                {label}
                        </span>
                </div>
        );
}

function TreeNode({  // NOSONAR - typescript:S6759
        title,
        children,
        defaultOpen = false,
}: {
        title: string;
        children?: React.ReactNode;
        defaultOpen?: boolean;
}) {
        const [open, setOpen] = useState(defaultOpen);
        return (
                <div className="select-none">
                        <div  // NOSONAR — S6848: type assertion acceptable
                                className="flex items-center gap-1 py-1 hover:bg-muted/50 cursor-pointer rounded px-1"
                                onClick={() => setOpen(!open)} onKeyDown={(e) => { if (e.key === "Enter") (() => setOpen(!open))(); }}                  >
                                <Triangle
                                        className={`h-3 w-3 text-muted-foreground transition-transform ${open ? "rotate-180" : "rotate-90"}`}
                                />
                                <FolderOpen className="h-3.5 w-3.5 text-blue-400/80" />
                                <span className="text-xs truncate">{title}</span>
                        </div>
                        {open && children && (
                                <div className="ml-3 pl-2 border-l border-border/50 flex flex-col gap-0.5 mt-0.5">
                                        {children}
                                </div>
                        )}
                </div>
        );
}

function FileNode({  // NOSONAR - typescript:S6759
        title,
        type,
        active = false,
        onClick,
        onKeyDown,
}: {
        title: string;
        type: string;
        active?: boolean;
        onClick?: () => void;
        onKeyDown?: (e: React.KeyboardEvent<HTMLDivElement>) => void;
}) {
        let color = "text-muted-foreground";
        if (type === "dwg") color = "text-blue-400";
        if (type === "rvt") color = "text-orange-400";
        if (type === "xlsx") color = "text-emerald-400";

        return (
                <div  // NOSONAR — S6819: non-null assertion acceptable
                        className={`flex items-center gap-2 py-1 px-2 rounded cursor-pointer ${active ? "bg-primary/10 text-primary" : "hover:bg-muted/50 text-muted-foreground"}`}
                        onClick={onClick} onKeyDown={onKeyDown} tabIndex={0} role="button">
                        <FileText className={`h-3.5 w-3.5 ${color}`} />
                        <span className={`text-xs truncate ${active ? "font-medium" : ""}`}>
                                {title}
                        </span>
                </div>
        );
}

function LayerRow({  // NOSONAR - typescript:S6759
        name,
        color,
        active = false,
        hidden = false,
        locked = false,
}: {
        name: string;
        color: string;
        active?: boolean;
        hidden?: boolean;
        locked?: boolean;
}) {
        return (
                <div
                        className={`flex items-center justify-between py-1.5 px-2 rounded hover:bg-muted/50 group ${active ? "bg-muted/30" : ""}`}
                >
                        <div className="flex items-center gap-2">
                                <div className={`w-2.5 h-2.5 rounded-full ${color}`}></div>
                                <span
                                        className={`text-xs ${active ? "text-foreground font-medium" : "text-muted-foreground"}`}
                                >
                                        {name}
                                </span>
                        </div>
                        <div className="flex items-center gap-1.5 opacity-60 group-hover:opacity-100">
                                {hidden ? (
                                        <EyeOff className="h-3 w-3 text-muted-foreground" />
                                ) : (
                                        <Eye className="h-3 w-3 text-foreground" />
                                )}
                                {locked ? (
                                        <Lock className="h-3 w-3 text-amber-500/70" />
                                ) : (
                                        <div className="w-3 h-3"></div>
                                )}
                        </div>
                </div>
        );
}

function ToolBtn({  // NOSONAR - typescript:S6759
        icon,
        active = false,
}: {
        icon: React.ReactNode;
        active?: boolean;
}) {
        return (
                <div
                        className={`w-8 h-8 rounded flex items-center justify-center cursor-pointer [&>svg]:w-4 [&>svg]:h-4 ${active ? "bg-primary/20 text-primary border border-primary/30" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
                >
                        {icon}
                </div>
        );
}

function PropRow({ label, value }: { label: string; value: string }) {  // NOSONAR - typescript:S6759
        return (
                <div className="flex justify-between items-center text-xs">
                        <span className="text-muted-foreground">{label}</span>
                        <span className="font-mono text-foreground">{value}</span>
                </div>
        );
}
