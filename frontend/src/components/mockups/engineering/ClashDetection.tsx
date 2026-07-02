import React, { useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { 
  Play, Filter, Download, Settings, ChevronLeft, ChevronRight,
  AlertTriangle, AlertCircle, Info, CheckCircle2, Navigation,
  Maximize, Minimize, MousePointer2, BoxSelect, LocateFixed
} from "lucide-react";

export function ClashDetection() {
  const [activeTab, setActiveTab] = useState("MEP");
  const [activeClash, setActiveClash] = useState("CLH-014");

  const clashes = [
    { id: "CLH-014", severity: "Critical", desc: "HVAC Duct D-14 vs Structural Beam SB-07", level: "Level 2", grid: "C-4", status: "Unresolved" },
    { id: "CLH-015", severity: "Critical", desc: "Plumbing Main vs Electrical Tray CT-2", level: "Level 2", grid: "D-2", status: "Unresolved" },
    { id: "CLH-008", severity: "Major", desc: "Conduit Run E-4 vs Fire Sprinkler Main", level: "Level 1", grid: "A-1", status: "Accepted" },
    { id: "CLH-009", severity: "Major", desc: "HVAC Return vs Cable Tray CT-1", level: "Level 1", grid: "B-3", status: "Unresolved" },
    { id: "CLH-011", severity: "Minor", desc: "Lighting Fixture vs Ceiling Grid", level: "Level 1", grid: "C-2", status: "Resolved" },
    { id: "CLH-021", severity: "Critical", desc: "Shear Wall vs Primary Duct", level: "Level 3", grid: "F-5", status: "Unresolved" },
    { id: "CLH-022", severity: "Major", desc: "Drainage Pipe vs Floor Slab Penetration", level: "Level 3", grid: "E-4", status: "Accepted" },
    { id: "CLH-025", severity: "Minor", desc: "Telecom Conduit vs Partition Wall", level: "Level 3", grid: "B-5", status: "Resolved" },
  ];

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
      {/* Top Toolbar */}
      <div className="h-14 flex items-center justify-between px-4 border-b bg-card shrink-0">
        <div className="flex items-center gap-4">
          <div className="font-bold tracking-wide flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            Clash Detection & BIM Coordination
          </div>
          <Separator orientation="vertical" className="h-6" />
          <div className="flex items-center space-x-1 bg-muted p-1 rounded-md">
            {["Architecture", "Structural", "MEP", "Electrical", "Fire Protection"].map(tab => (
              <button
                key={tab}
                className={`px-3 py-1 text-xs rounded-sm transition-colors ${activeTab === tab ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="text-xs text-muted-foreground hidden lg:flex items-center gap-3">
            <span>Last run: 3 minutes ago</span>
            <span className="text-amber-500 font-medium">47 clashes found</span>
            <span className="text-red-400">12 Critical</span>
            <span className="text-orange-400">23 Major</span>
            <span className="text-yellow-400">12 Minor</span>
          </div>
          <Separator orientation="vertical" className="h-6 hidden lg:block" />
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-8 gap-1"><Filter className="h-3.5 w-3.5"/> Filter</Button>
            <Button variant="outline" size="sm" className="h-8 gap-1"><Download className="h-3.5 w-3.5"/> Export</Button>
            <Button size="sm" className="h-8 gap-1"><Play className="h-3.5 w-3.5"/> Run Detection</Button>
            <Button variant="ghost" size="icon" className="h-8 w-8"><Settings className="h-4 w-4"/></Button>
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel - Clash List */}
        <div className="w-[300px] flex flex-col border-r bg-card/30 shrink-0">
          <div className="p-3 border-b bg-card/50 flex justify-between items-center">
            <div className="text-sm font-semibold">Active Clashes</div>
            <Badge variant="secondary">47 Total</Badge>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-2 space-y-2">
              {clashes.map(clash => (
                <div 
                  key={clash.id} 
                  className={`p-3 rounded-md border cursor-pointer transition-all hover:bg-muted/50 ${activeClash === clash.id ? "bg-primary/10 border-primary/50" : "bg-card border-border/50"}`}
                  onClick={() => setActiveClash(clash.id)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={clash.severity} />
                      <span className="text-xs font-mono font-medium">{clash.id}</span>
                    </div>
                    <StatusIcon status={clash.status} />
                  </div>
                  <div className="text-sm font-medium leading-tight mb-2">{clash.desc}</div>
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                    <span>{clash.level} / {clash.grid}</span>
                    <span className={clash.status === 'Resolved' ? "text-emerald-500" : ""}>{clash.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* Center Panel - 3D Viewport */}
        <div className="flex-1 relative bg-[#0f1115] overflow-hidden">
          {/* Abstract 3D View */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="relative w-[600px] h-[500px]" style={{ transform: "rotateX(60deg) rotateZ(-45deg)", transformStyle: "preserve-3d" }}>
              {/* Floor Slab */}
              <div className="absolute inset-0 bg-slate-800 border border-slate-600 shadow-[0_0_50px_rgba(0,0,0,0.5)]" style={{ transform: "translateZ(-100px)" }}>
                {/* Grid lines */}
                <div className="w-full h-full" style={{ backgroundImage: "linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)", backgroundSize: "100px 100px" }}></div>
              </div>
              
              {/* Structural Beam */}
              <div className="absolute top-[200px] left-0 w-[600px] h-[40px] bg-slate-600 border border-slate-500" style={{ transform: "translateZ(150px)" }}></div>
              
              {/* HVAC Duct */}
              <div className="absolute top-0 left-[300px] w-[60px] h-[500px] bg-blue-500/20 border-2 border-blue-500/50" style={{ transform: "translateZ(130px)" }}></div>
              
              {/* Pipe Run */}
              <div className="absolute top-[100px] left-0 w-[600px] h-[10px] bg-green-500/30 border border-green-500/60 rounded-full" style={{ transform: "translateZ(80px)" }}></div>

              {/* Clash Highlight */}
              <div className="absolute top-[170px] left-[270px] w-[120px] h-[100px] border-4 border-red-500 bg-red-500/20 rounded-full animate-pulse shadow-[0_0_30px_rgba(239,68,68,0.6)]" style={{ transform: "translateZ(140px)" }}></div>
              <div className="absolute top-[220px] left-[330px] w-2 h-2 bg-red-400 rounded-full" style={{ transform: "translateZ(180px) rotateX(-60deg) rotateZ(45deg)" }}>
                 <div className="absolute -top-12 -left-6 bg-red-500 text-white text-[10px] px-2 py-1 rounded whitespace-nowrap font-mono">CLH-014</div>
              </div>
            </div>
          </div>

          {/* Overlays */}
          <div className="absolute top-4 left-4 flex flex-col gap-1">
            {["Roof", "L3", "L2", "L1", "B1", "B2"].map(lvl => (
              <div key={lvl} className={`px-2 py-1 text-[10px] font-mono rounded cursor-pointer border ${lvl === "L2" ? "bg-primary/20 text-primary border-primary/50" : "bg-card/80 text-muted-foreground border-transparent hover:bg-muted"}`}>
                {lvl}
              </div>
            ))}
          </div>

          <div className="absolute bottom-4 right-4 flex flex-col gap-2">
            <div className="bg-card/80 backdrop-blur border rounded-md shadow-lg flex flex-col p-1 gap-1">
              <ToolBtn icon={<Navigation />} active />
              <ToolBtn icon={<MousePointer2 />} />
              <ToolBtn icon={<BoxSelect />} />
              <Separator />
              <ToolBtn icon={<LocateFixed />} />
            </div>
            <div className="bg-card/80 backdrop-blur border rounded-md shadow-lg flex flex-col p-1 gap-1">
              <ToolBtn icon={<Maximize />} />
              <ToolBtn icon={<Minimize />} />
            </div>
          </div>

          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-4 bg-card/80 backdrop-blur border rounded-full px-4 py-2">
            <Button variant="ghost" size="icon" className="h-6 w-6 rounded-full"><ChevronLeft className="h-4 w-4"/></Button>
            <div className="text-xs font-mono">CLH-014 of 47</div>
            <Button variant="ghost" size="icon" className="h-6 w-6 rounded-full"><ChevronRight className="h-4 w-4"/></Button>
          </div>
        </div>

        {/* Right Panel - Clash Inspector */}
        <div className="w-[320px] flex flex-col border-l bg-card/30 shrink-0">
          <div className="p-4 border-b bg-card/50 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="text-lg font-mono font-bold text-red-400">CLH-014</div>
              <Badge variant="outline" className="text-red-400 border-red-500/30">Hard Clash</Badge>
            </div>
            <div className="text-sm font-medium">HVAC supply duct (600x400mm) intersects W-flange beam W18x97 at grid intersection C-4, Level 2</div>
          </div>

          <ScrollArea className="flex-1">
            <div className="p-4 space-y-6">
              
              <div className="space-y-3">
                <div className="text-xs font-semibold uppercase text-muted-foreground border-b pb-1">Elements Involved</div>
                <div className="p-3 bg-muted/30 border rounded-md text-xs space-y-2">
                  <div className="flex items-center gap-2 text-blue-400 font-medium mb-1">
                    <div className="w-2 h-2 rounded-full bg-blue-500"></div> Element A: HVAC Duct
                  </div>
                  <div className="grid grid-cols-2 gap-1 text-[10px] font-mono">
                    <span className="text-muted-foreground">System:</span><span>Supply Air</span>
                    <span className="text-muted-foreground">ID:</span><span>DU-2-C4-014</span>
                    <span className="text-muted-foreground">Size:</span><span>600x400mm</span>
                  </div>
                </div>
                
                <div className="p-3 bg-muted/30 border rounded-md text-xs space-y-2">
                  <div className="flex items-center gap-2 text-slate-300 font-medium mb-1">
                    <div className="w-2 h-2 rounded-full bg-slate-400"></div> Element B: Structural Beam
                  </div>
                  <div className="grid grid-cols-2 gap-1 text-[10px] font-mono">
                    <span className="text-muted-foreground">Type:</span><span>W18x97</span>
                    <span className="text-muted-foreground">Mark:</span><span>SB-07</span>
                    <span className="text-muted-foreground">Level:</span><span>2</span>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold uppercase text-muted-foreground border-b pb-1">Resolution</div>
                <div className="p-3 bg-card border border-primary/30 rounded-md">
                  <div className="flex items-center gap-2 text-primary font-medium text-xs mb-2">
                    <Zap className="h-3.5 w-3.5" /> AI Recommendation
                  </div>
                  <p className="text-xs text-muted-foreground mb-3">Reroute duct 450mm to the east or lower beam elevation by 300mm. Route option B saves 2.3m² ceiling space.</p>
                  <div className="flex gap-2">
                    <Button size="sm" className="w-full text-xs h-7">Accept Option B</Button>
                    <Button size="sm" variant="outline" className="w-full text-xs h-7">Manual Fix</Button>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="text-xs font-semibold uppercase text-muted-foreground border-b pb-1 flex justify-between">
                  Activity <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4">2</Badge>
                </div>
                
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <div className="w-6 h-6 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center text-[10px] font-bold shrink-0">SC</div>
                    <div className="text-xs">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium">Sarah Chen</span>
                        <span className="text-[9px] text-muted-foreground">10:42 AM</span>
                      </div>
                      <p className="text-muted-foreground bg-muted p-2 rounded-md rounded-tl-none">I can't lower the beam here, architectural ceiling is too tight.</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <div className="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-[10px] font-bold shrink-0">MW</div>
                    <div className="text-xs">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium">Marcus W.</span>
                        <span className="text-[9px] text-muted-foreground">11:05 AM</span>
                      </div>
                      <p className="text-muted-foreground bg-muted p-2 rounded-md rounded-tl-none">Okay, I will route the duct east. Will update the model shortly.</p>
                    </div>
                  </div>
                </div>
                
                <div className="pt-2">
                  <Input placeholder="Type a comment..." className="text-xs h-8 bg-background" />
                </div>
              </div>

            </div>
          </ScrollArea>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="h-8 border-t bg-card flex items-center justify-between px-4 text-[10px] font-mono text-muted-foreground shrink-0">
        <div className="flex items-center gap-4">
          <span>Clash Summary:</span>
          <span className="text-foreground">47 Total</span>
          <span className="text-red-400">12 Critical</span>
          <span className="text-orange-400">23 Major</span>
          <span className="text-yellow-400">12 Minor</span>
          <span className="text-emerald-400">8 Resolved</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span>Resolution: 17%</span>
            <div className="w-32 h-1.5 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-emerald-500 w-[17%]"></div>
            </div>
          </div>
          <Separator orientation="vertical" className="h-4" />
          <div className="flex gap-3">
            <span className="cursor-pointer hover:text-foreground">IFC BCF</span>
            <span className="cursor-pointer hover:text-foreground">PDF Report</span>
            <span className="cursor-pointer hover:text-foreground">Excel</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  let color = "bg-yellow-500/20 text-yellow-500 border-yellow-500/30";
  if (severity === "Critical") color = "bg-red-500/20 text-red-400 border-red-500/30";
  if (severity === "Major") color = "bg-orange-500/20 text-orange-400 border-orange-500/30";
  
  return (
    <Badge variant="outline" className={`text-[9px] px-1.5 py-0 h-4 uppercase ${color}`}>{severity}</Badge>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "Resolved") return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />;
  if (status === "Accepted") return <Info className="h-3.5 w-3.5 text-blue-400" />;
  return <AlertCircle className="h-3.5 w-3.5 text-muted-foreground" />;
}

function ToolBtn({ icon, active = false }: { icon: React.ReactNode, active?: boolean }) {
  return (
    <div className={`w-8 h-8 rounded flex items-center justify-center cursor-pointer [&>svg]:w-4 [&>svg]:h-4 ${active ? "bg-primary/20 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>
      {icon}
    </div>
  );
}

// Zap Icon duplicate since it wasn't imported from lucide-react above
function Zap(props: any) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinelinejoin="round" {...props}>
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
    </svg>
  );
}
