import React, { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Flame, ShieldAlert, Zap, Box, Settings, Search, Eye, Layers, Circle, Triangle, Square, Power, Download, ChevronRight, ChevronDown, CheckCircle2, AlertTriangle, Maximize } from "lucide-react";

export function FireAlarmDesigner() {
  const [activeZone, setActiveZone] = useState("Zone 2-02");

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-900 text-slate-100 font-sans">
      {/* Top Ribbon */}
      <div className="h-24 flex flex-col border-b border-slate-700 bg-slate-800 shrink-0">
        <div className="h-10 flex items-center justify-between px-4 border-b border-slate-700/50 bg-slate-900/50">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-red-400 font-bold tracking-wide">
              <Flame className="h-5 w-5" />
              <span>Fire Alarm & Life Safety Systems Designer</span>
            </div>
            <Separator orientation="vertical" className="h-5 bg-slate-700" />
            <div className="flex text-xs space-x-1">
              <button className="px-3 py-1 rounded-sm transition-colors bg-red-500/10 text-red-400 font-medium border border-red-500/20">Fire Alarm</button>
              <button className="px-3 py-1 rounded-sm transition-colors text-slate-400 hover:bg-slate-800 hover:text-slate-200">Suppression</button>
              <button className="px-3 py-1 rounded-sm transition-colors text-slate-400 hover:bg-slate-800 hover:text-slate-200">Evacuation</button>
              <button className="px-3 py-1 rounded-sm transition-colors text-slate-400 hover:bg-slate-800 hover:text-slate-200">Compliance</button>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button size="sm" variant="outline" className="h-7 text-xs border-slate-600 text-slate-300">Run Validation</Button>
            <Button size="sm" className="h-7 text-xs bg-red-600 hover:bg-red-700 text-white border-none">Export Schedule</Button>
          </div>
        </div>
        
        {/* Ribbon Tools */}
        <div className="flex-1 flex items-center px-2 space-x-1 bg-slate-800/80 overflow-x-auto">
          {/* Group 1 */}
          <div className="flex items-center px-2 border-r border-slate-700">
            <RibbonBtn icon={<Circle className="text-slate-300" />} label="Smoke Det" active />
            <RibbonBtn icon={<Triangle className="text-slate-300" />} label="Heat Det" />
            <RibbonBtn icon={<Box className="text-slate-300" />} label="Multi-sensor" />
            <RibbonBtn icon={<Settings className="text-slate-300" />} label="Aspirating" />
          </div>
          {/* Group 2 */}
          <div className="flex items-center px-2 border-r border-slate-700">
            <RibbonBtn icon={<Square className="text-slate-300" />} label="Horn/Strobe" />
            <RibbonBtn icon={<Power className="text-slate-300" />} label="Speaker" />
            <RibbonBtn icon={<AlertTriangle className="text-slate-300" />} label="Mass Notif" />
          </div>
          {/* Group 3 */}
          <div className="flex items-center px-2 border-r border-slate-700">
            <RibbonBtn icon={<Box className="text-red-400" />} label="Pull Station" />
            <RibbonBtn icon={<Layers className="text-slate-300" />} label="FACP" />
            <RibbonBtn icon={<Zap className="text-slate-300" />} label="Relay Mod" />
          </div>
          {/* Group 4 & 5 */}
          <div className="flex items-center px-2 border-r border-slate-700">
            <RibbonBtn icon={<Download className="text-blue-400" />} label="Sprinkler" />
            <RibbonBtn icon={<Eye className="text-slate-300" />} label="Coverage" active />
            <RibbonBtn icon={<Maximize className="text-slate-300" />} label="Loop Diag" />
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Explorer */}
        <div className="w-[240px] flex flex-col border-r border-slate-700 bg-slate-800 shrink-0">
          <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400 border-b border-slate-700 flex justify-between items-center bg-slate-900/50">
            <span>System Navigator</span>
            <Search className="h-3 w-3" />
          </div>
          <ScrollArea className="flex-1 p-2">
            <NavNode title="Tower-B Fire Alarm" expanded>
              <NavNode title="FACP-1 (Main)" expanded>
                <NavNode title="SLC Loop 1">
                  <NavNode title="Zone 1-01: B2 (12)" />
                  <NavNode title="Zone 1-02: B1 (18)" />
                  <NavNode title="Zone 1-03: GF (24)" />
                </NavNode>
                <NavNode title="SLC Loop 2" expanded>
                  <NavNode title="Zone 2-01: L1 (22)" />
                  <NavNode title="Zone 2-02: L2 (19)" active />
                  <NavNode title="Zone 2-03: L3 (21)" />
                </NavNode>
                <NavNode title="NAC Circuit 1 (Gen)" />
                <NavNode title="NAC Circuit 2 (Elev)" />
              </NavNode>
              <NavNode title="FACP-2 (Annun)" />
              <NavNode title="FM-200 System" />
              <NavNode title="Sprinkler Integration" />
            </NavNode>
          </ScrollArea>
          
          <div className="p-3 border-t border-slate-700 bg-slate-900/50 text-xs">
            <div className="text-slate-400 mb-1 uppercase tracking-wider font-semibold">Device Count</div>
            <div className="grid grid-cols-2 gap-1 text-slate-300">
              <div>Total: <span className="font-mono text-slate-100">247</span></div>
              <div>Smoke: <span className="font-mono text-slate-100">142</span></div>
              <div>Heat: <span className="font-mono text-slate-100">38</span></div>
              <div>Pull: <span className="font-mono text-slate-100">28</span></div>
              <div>H/S: <span className="font-mono text-slate-100">39</span></div>
            </div>
          </div>
        </div>

        {/* Central Canvas */}
        <div className="flex-1 bg-[#0b0f19] relative overflow-hidden flex flex-col" style={{ backgroundImage: 'radial-gradient(#1e293b 1px, transparent 1px)', backgroundSize: '30px 30px' }}>
          <div className="absolute inset-0 flex items-center justify-center">
            {/* SVG Floor Plan */}
            <div className="relative w-full max-w-3xl aspect-[4/3] border border-slate-700 bg-slate-800/20">
              {/* Room Outlines */}
              <div className="absolute top-10 left-10 w-[200px] h-[300px] border border-slate-600"></div>
              <div className="absolute top-10 left-[210px] w-[300px] h-[150px] border border-slate-600"></div>
              <div className="absolute top-[160px] left-[210px] w-[300px] h-[150px] border border-slate-600"></div>
              
              {/* Zone Boundary */}
              <div className="absolute top-8 left-8 w-[510px] h-[310px] border-2 border-dashed border-purple-500/50 rounded pointer-events-none">
                <span className="absolute -top-6 left-0 text-purple-400 text-[10px] font-mono">ZONE 2-02</span>
              </div>

              <svg className="absolute inset-0 w-full h-full pointer-events-none">
                {/* Wiring SLC Loop */}
                <path d="M 60 60 L 160 60 L 160 150 L 60 150 L 60 250 L 160 250 L 260 100 L 460 100" stroke="#3b82f6" strokeWidth="2" strokeDasharray="6 4" fill="none" opacity="0.8" />
                <path d="M 260 250 L 460 250" stroke="#3b82f6" strokeWidth="2" strokeDasharray="6 4" fill="none" opacity="0.8" />

                {/* NAC Circuit */}
                <path d="M 40 80 L 180 80 L 180 200" stroke="#f97316" strokeWidth="1.5" strokeDasharray="4 2" fill="none" opacity="0.6" />

                {/* Coverage Circles */}
                <circle cx="110" cy="105" r="45" fill="rgba(59, 130, 246, 0.05)" stroke="rgba(59, 130, 246, 0.2)" strokeWidth="1" />
                <circle cx="110" cy="200" r="45" fill="rgba(59, 130, 246, 0.05)" stroke="rgba(59, 130, 246, 0.2)" strokeWidth="1" />
                <circle cx="360" cy="100" r="45" fill="rgba(239, 68, 68, 0.1)" stroke="rgba(239, 68, 68, 0.5)" strokeWidth="1" /> {/* Violation */}
                <circle cx="360" cy="250" r="45" fill="rgba(59, 130, 246, 0.05)" stroke="rgba(59, 130, 246, 0.2)" strokeWidth="1" />
              </svg>

              {/* Devices */}
              <DeviceSymbol type="smoke" x={110} y={105} label="SD-2-08" />
              <DeviceSymbol type="smoke" x={110} y={200} label="SD-2-09" selected />
              <DeviceSymbol type="smoke" x={360} y={100} label="SD-2-10" warning />
              <DeviceSymbol type="smoke" x={360} y={250} label="SD-2-11" />
              
              <DeviceSymbol type="heat" x={260} y={100} label="HD-2-01" />
              <DeviceSymbol type="heat" x={460} y={100} label="HD-2-02" />
              
              <DeviceSymbol type="pull" x={60} y={60} label="PS-2-01" />
              <DeviceSymbol type="horn" x={180} y={80} label="HS-2-01" />
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="w-[280px] bg-slate-800 border-l border-slate-700 flex flex-col shrink-0">
          <div className="p-3 border-b border-slate-700 bg-slate-900/50">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-6 h-6 rounded-full border border-blue-400 bg-blue-500/20 flex items-center justify-center text-[10px] text-blue-400">S</div>
              <div className="font-bold text-slate-200">SD-2-09</div>
            </div>
            <div className="text-[10px] text-slate-400 uppercase tracking-wider">Photoelectric Smoke Detector</div>
          </div>

          <ScrollArea className="flex-1 p-3">
            <div className="space-y-4">
              {/* Device Info */}
              <div className="space-y-1 text-xs">
                <PropRow label="Address" value="Loop 2, Addr 109" />
                <PropRow label="Zone" value="2-02 (Office B)" />
                <PropRow label="Location" value="Level 2, Room 205" />
                <PropRow label="Height AFF" value="2.9m" />
                <PropRow label="Mfr" value="Hochiki ESP" />
                <PropRow label="Model" value="ALG-EN" />
              </div>

              <Separator className="bg-slate-700" />

              {/* Coverage */}
              <div>
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Coverage (NFPA 72)</div>
                <div className="space-y-1 text-xs">
                  <PropRow label="Coverage Area" value="64.2 m²" />
                  <PropRow label="Nearest Det." value="7.8m" />
                  <PropRow label="Compliance" value={<span className="text-green-400 font-bold">PASS</span>} />
                </div>
              </div>

              <Separator className="bg-slate-700" />

              {/* Status & Sensitivity */}
              <div>
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Live Status</div>
                <div className="space-y-1 text-xs mb-3">
                  <PropRow label="Current Status" value={<span className="text-green-400">Normal</span>} />
                  <PropRow label="Signal Strength" value="-42 dBm" />
                  <PropRow label="Last Test" value="10 Nov 2024" />
                </div>

                <div className="p-2 bg-slate-900 rounded border border-slate-700 text-[10px] space-y-1 font-mono text-slate-400">
                  <div className="flex justify-between"><span>Sensitivity:</span> <span className="text-slate-200">2 (Medium)</span></div>
                  <div className="flex justify-between"><span>Pre-alarm:</span> <span className="text-slate-200">1.5%/ft</span></div>
                  <div className="flex justify-between"><span>Alarm:</span> <span className="text-red-400">2.5%/ft</span></div>
                </div>
              </div>

              <div className="flex flex-col gap-2 pt-2">
                <Button variant="outline" className="w-full text-xs h-8 border-slate-600 bg-slate-800 text-slate-300">Run Sensitivity Test</Button>
                <Button variant="outline" className="w-full text-xs h-8 border-slate-600 bg-slate-800 text-slate-300">View in Schedule</Button>
              </div>
            </div>
          </ScrollArea>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="h-8 bg-slate-900 border-t border-slate-700 flex items-center justify-between px-4 text-[10px] font-mono shrink-0">
        <div className="flex items-center gap-4 text-slate-400">
          <span className="text-purple-400 font-bold">Zone 2-02</span>
          <span>19 devices</span>
          <Separator orientation="vertical" className="h-4 bg-slate-700" />
          <span className="text-green-400">18 Normal</span>
          <Separator orientation="vertical" className="h-4 bg-slate-700" />
          <span className="text-orange-400">1 Warning</span>
          <Separator orientation="vertical" className="h-4 bg-slate-700" />
          <span>SLC Loop 2: 116/250 (142mA)</span>
        </div>
        <div className="flex items-center gap-4 text-slate-400">
          <span>Standards: NFPA 72 2022 | IBC 2021</span>
          <Separator orientation="vertical" className="h-4 bg-slate-700" />
          <span className="text-blue-400 cursor-pointer hover:text-blue-300">Generate FACP Report</span>
        </div>
      </div>
    </div>
  );
}

function RibbonBtn({ icon, label, active = false }: { icon: React.ReactNode, label: string, active?: boolean }) {
  return (
    <div className={`flex flex-col items-center justify-center w-16 h-12 rounded cursor-pointer transition-colors group ${active ? 'bg-blue-500/20 border border-blue-500/30' : 'hover:bg-slate-700'}`}>
      <div className="mb-1 [&>svg]:w-4 [&>svg]:h-4">
        {icon}
      </div>
      <span className={`text-[9px] text-center leading-tight whitespace-nowrap px-1 overflow-hidden text-ellipsis w-full ${active ? 'text-blue-400' : 'text-slate-400 group-hover:text-slate-200'}`}>{label}</span>
    </div>
  );
}

function NavNode({ title, expanded = false, active = false, children }: { title: string, expanded?: boolean, active?: boolean, children?: React.ReactNode }) {
  return (
    <div className="select-none">
      <div className={`flex items-center gap-1.5 py-1 px-2 rounded cursor-pointer hover:bg-slate-700/50 ${active ? "bg-blue-500/20 text-blue-400 font-medium" : "text-slate-300"}`}>
        <div className="w-4 h-4 flex items-center justify-center">
          {children ? (
            expanded ? <ChevronDown className="h-3 w-3 text-slate-500" /> : <ChevronRight className="h-3 w-3 text-slate-500" />
          ) : <div className="w-1 h-1" />}
        </div>
        <span className="text-xs truncate">{title}</span>
      </div>
      {expanded && children && (
        <div className="ml-3 pl-2 border-l border-slate-700 flex flex-col gap-0.5 mt-0.5">
          {children}
        </div>
      )}
    </div>
  );
}

function DeviceSymbol({ type, x, y, label, selected = false, warning = false }: { type: string, x: number, y: number, label: string, selected?: boolean, warning?: boolean }) {
  const isSmoke = type === "smoke";
  const isHeat = type === "heat";
  const isPull = type === "pull";
  const isHorn = type === "horn";
  
  return (
    <div className="absolute flex flex-col items-center" style={{ left: x - 12, top: y - 12 }}>
      <div className={`relative flex items-center justify-center w-6 h-6 ${selected ? 'ring-2 ring-blue-400 ring-offset-2 ring-offset-slate-900 rounded-sm' : ''} ${warning ? 'ring-2 ring-orange-500 ring-offset-1 ring-offset-slate-900 rounded-sm animate-pulse' : ''}`}>
        {isSmoke && <div className="w-5 h-5 rounded-full border border-slate-300 bg-slate-800 flex items-center justify-center text-[8px] text-slate-300 font-bold">S</div>}
        {isHeat && <div className="w-0 h-0 border-l-[10px] border-r-[10px] border-b-[18px] border-l-transparent border-r-transparent border-b-slate-400 flex items-center justify-center"><span className="absolute top-[6px] text-[7px] text-slate-900 font-bold">H</span></div>}
        {isPull && <div className="w-4 h-5 border border-red-500 bg-red-500/20 flex items-center justify-center text-[7px] text-red-500 font-bold">P</div>}
        {isHorn && <div className="w-5 h-5 bg-orange-500/80 clip-pentagon flex items-center justify-center"></div>}
      </div>
      <div className={`mt-1 text-[8px] font-mono whitespace-nowrap bg-slate-900/80 px-1 rounded ${warning ? 'text-orange-400' : 'text-slate-400'}`}>{label}</div>
    </div>
  );
}

function PropRow({ label, value }: { label: string, value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-start py-0.5">
      <span className="text-slate-400 w-1/2">{label}</span>
      <span className="text-slate-200 w-1/2 text-right font-mono text-[10px]">{value}</span>
    </div>
  );
}
