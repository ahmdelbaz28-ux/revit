import React, { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Network, Wifi, MonitorPlay, Speaker, Cable, Server, CheckCircle2, AlertTriangle, Settings, Search, LayoutGrid, Monitor, Layout, ArrowRightLeft, Radio, Mic, Volume2 } from "lucide-react";

export function CablingNetwork() {
  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-900 text-slate-100 font-sans">
      {/* Top Ribbon */}
      <div className="h-24 flex flex-col border-b border-slate-700 bg-slate-800 shrink-0">
        <div className="h-10 flex items-center justify-between px-4 border-b border-slate-700/50 bg-slate-900/50">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-emerald-400 font-bold tracking-wide">
              <Network className="h-5 w-5" />
              <span>Structured Cabling, Network & AV</span>
            </div>
            <Separator orientation="vertical" className="h-5 bg-slate-700" />
            <div className="flex text-xs space-x-1">
              <button className="px-3 py-1 rounded-sm transition-colors bg-emerald-500/10 text-emerald-400 font-medium border border-emerald-500/20">Structured Cabling</button>
              <button className="px-3 py-1 rounded-sm transition-colors text-slate-400 hover:bg-slate-800 hover:text-slate-200">Network Design</button>
              <button className="px-3 py-1 rounded-sm transition-colors text-slate-400 hover:bg-slate-800 hover:text-slate-200">Wi-Fi</button>
              <button className="px-3 py-1 rounded-sm transition-colors text-slate-400 hover:bg-slate-800 hover:text-slate-200">AV & PA</button>
              <button className="px-3 py-1 rounded-sm transition-colors text-slate-400 hover:bg-slate-800 hover:text-slate-200">IPTV</button>
            </div>
          </div>
        </div>
        
        {/* Ribbon Tools */}
        <div className="flex-1 flex items-center px-2 space-x-1 bg-slate-800 overflow-x-auto">
          {/* Outlets */}
          <div className="flex items-center px-2 border-r border-slate-700">
            <RibbonBtn icon={<LayoutGrid className="text-slate-300" />} label="Data Outlet" active />
            <RibbonBtn icon={<Monitor className="text-slate-300" />} label="Voice Outlet" />
            <RibbonBtn icon={<MonitorPlay className="text-slate-300" />} label="AV Outlet" />
          </div>
          {/* Active Equip */}
          <div className="flex items-center px-2 border-r border-slate-700">
            <RibbonBtn icon={<ArrowRightLeft className="text-slate-300" />} label="Switch" />
            <RibbonBtn icon={<Layout className="text-slate-300" />} label="Patch Panel" />
            <RibbonBtn icon={<Wifi className="text-slate-300" />} label="Wi-Fi AP" />
          </div>
          {/* Pathways & Rooms */}
          <div className="flex items-center px-2 border-r border-slate-700">
            <RibbonBtn icon={<Cable className="text-emerald-400" />} label="Cable Tray" />
            <RibbonBtn icon={<Server className="text-slate-300" />} label="Telecom Room" />
          </div>
          {/* AV */}
          <div className="flex items-center px-2 border-r border-slate-700">
            <RibbonBtn icon={<Speaker className="text-slate-300" />} label="Speaker" />
            <RibbonBtn icon={<Mic className="text-slate-300" />} label="Microphone" />
            <RibbonBtn icon={<Volume2 className="text-slate-300" />} label="Amplifier" />
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Explorer */}
        <div className="w-[240px] flex flex-col border-r border-slate-700 bg-slate-800 shrink-0">
          <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400 border-b border-slate-700 flex justify-between items-center bg-slate-900/50">
            <span>Infrastructure Tree</span>
            <Search className="h-3 w-3" />
          </div>
          <ScrollArea className="flex-1 p-2">
            <NavNode title="Tower-B Infrastructure" expanded>
              <NavNode title="MDF (Level 1, Rm 108)" expanded>
                <NavNode title="Core Switch (Cisco)" />
                <NavNode title="ISP Entry" />
                <NavNode title="IDF-B1 (Basement)" />
                <NavNode title="IDF-L1 (Level 1)" />
                <NavNode title="IDF-L2 (Level 2)" active expanded>
                  <NavNode title="PP-2A (Data)" />
                  <NavNode title="SW-2A (PoE+)" />
                </NavNode>
                <NavNode title="IDF-L3 (Level 3)" />
              </NavNode>
              <NavNode title="Backbone (OM4)" />
              <NavNode title="Horizontal (Cat6A)" />
              <NavNode title="Wi-Fi System" expanded>
                <NavNode title="Controller WLC-1" />
                <NavNode title="APs: 48 total" />
              </NavNode>
              <NavNode title="AV Systems">
                <NavNode title="Conference Rooms (8)" />
                <NavNode title="PA System" />
              </NavNode>
            </NavNode>
          </ScrollArea>
          
          <div className="p-3 border-t border-slate-700 bg-slate-900/50 text-xs">
            <div className="text-slate-400 mb-1 uppercase tracking-wider font-semibold">Summary</div>
            <div className="grid grid-cols-2 gap-1 text-slate-300 font-mono">
              <div>Data: <span className="text-slate-100">476</span></div>
              <div>Voice: <span className="text-slate-100">124</span></div>
              <div>AV: <span className="text-slate-100">68</span></div>
              <div>Wi-Fi: <span className="text-slate-100">48</span></div>
            </div>
          </div>
        </div>

        {/* Central Canvas */}
        <div className="flex-1 bg-[#0a0f12] relative overflow-hidden flex flex-col" style={{ backgroundImage: 'radial-gradient(#1e293b 1px, transparent 1px)', backgroundSize: '25px 25px' }}>
          <div className="absolute inset-0 flex items-center justify-center p-8">
            <div className="relative w-full max-w-3xl aspect-[4/3] border border-slate-700 bg-slate-800/20">
              
              {/* Floor Plan Outlines */}
              <div className="absolute top-10 left-10 w-[250px] h-[300px] border border-slate-600 bg-slate-800/30"></div> {/* Office A */}
              <div className="absolute top-10 right-10 w-[250px] h-[300px] border border-slate-600 bg-slate-800/30"></div> {/* Office B */}
              <div className="absolute bottom-10 left-10 w-[150px] h-[100px] border border-slate-600 bg-blue-500/10"></div> {/* Meeting 201 */}
              
              <div className="absolute top-10 left-[45%] w-[10%] h-[150px] border-2 border-emerald-500/50 bg-emerald-500/10 flex items-center justify-center shadow-[0_0_15px_rgba(16,185,129,0.1)]">
                <span className="text-[8px] text-emerald-400 font-bold uppercase rotate-90 tracking-widest">IDF-L2</span>
              </div>

              <svg className="absolute inset-0 w-full h-full pointer-events-none">
                {/* Pathways: Cable Tray */}
                <path d="M 50% 120 L 50% 350" stroke="#64748b" strokeWidth="8" fill="none" opacity="0.6" />
                <path d="M 120 350 L 50% 350" stroke="#64748b" strokeWidth="6" fill="none" opacity="0.6" />
                <path d="M 50% 350 L 80% 350" stroke="#64748b" strokeWidth="6" fill="none" opacity="0.6" />

                {/* Cable Runs */}
                <path d="M 120 200 L 120 350 L 50% 350 L 50% 120" stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="3 3" fill="none" />
                <path d="M 80% 200 L 80% 350 L 50% 350 L 50% 120" stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="3 3" fill="none" />

                <text x="35%" y="345" fill="#94a3b8" fontSize="8" fontFamily="monospace">42m</text>
                <text x="65%" y="345" fill="#94a3b8" fontSize="8" fontFamily="monospace">67m</text>
              </svg>

              {/* Wi-Fi APs */}
              <div className="absolute top-[20%] left-[25%] -translate-x-1/2 -translate-y-1/2">
                <div className="w-6 h-6 rounded-full border border-blue-400 bg-blue-500/20 flex items-center justify-center"><Radio className="w-3 h-3 text-blue-400" /></div>
                <div className="w-24 h-24 rounded-full border border-blue-400/20 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none"></div>
              </div>
              <div className="absolute top-[20%] right-[25%] -translate-x-1/2 -translate-y-1/2">
                <div className="w-6 h-6 rounded-full border border-blue-400 bg-blue-500/20 flex items-center justify-center"><Radio className="w-3 h-3 text-blue-400" /></div>
              </div>

              {/* Outlets */}
              <div className="absolute left-[120px] top-[200px] w-3 h-3 bg-emerald-500/80 border border-emerald-300 ring-2 ring-emerald-400 ring-offset-2 ring-offset-[#0a0f12] -translate-x-1/2 -translate-y-1/2 cursor-pointer z-10"></div>
              <div className="absolute left-[80%] top-[200px] w-3 h-3 bg-slate-500 border border-slate-400 -translate-x-1/2 -translate-y-1/2"></div>
              
              {/* Labels */}
              <div className="absolute left-[120px] top-[210px] text-[8px] text-emerald-300 bg-slate-900 px-1 font-mono -translate-x-1/2 border border-emerald-500/30 rounded">DA-2-047</div>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="w-[300px] bg-slate-800 border-l border-slate-700 flex flex-col shrink-0">
          <div className="p-3 border-b border-slate-700 bg-slate-900/50">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-6 h-6 rounded bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center"><LayoutGrid className="w-3 h-3 text-emerald-400" /></div>
              <div className="font-bold text-slate-200">DA-2-047</div>
            </div>
            <div className="text-[10px] text-slate-400 uppercase tracking-wider">Dual Data Outlet</div>
          </div>

          <ScrollArea className="flex-1 p-3">
            <div className="space-y-4">
              
              <div>
                <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Outlet Details</h3>
                <div className="space-y-1 bg-slate-900/50 p-2 rounded border border-slate-700/50 text-xs">
                  <PropRow label="Location" value="Level 2, Zone A" />
                  <PropRow label="Wall Box" value="2-gang, low-volt" />
                  <PropRow label="Height AFF" value="300mm" />
                </div>
              </div>

              <div>
                <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Cabling & Term</h3>
                <div className="space-y-1 bg-slate-900/50 p-2 rounded border border-slate-700/50 text-xs">
                  <PropRow label="Cable" value="Cat6A U/FTP" />
                  <PropRow label="Length" value="42.3m (Max 90)" />
                  <PropRow label="Patch Panel" value="IDF-L2, PP-2A, P47" />
                  <PropRow label="Switch Port" value="SW-2A, Port 47" />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Certification</h3>
                  <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-[9px] h-4 py-0 px-1 font-mono">PASS</Badge>
                </div>
                <div className="space-y-1 bg-slate-900/50 p-2 rounded border border-slate-700/50 text-xs font-mono text-[10px]">
                  <div className="flex justify-between text-slate-400"><span>Wire Map</span> <span className="text-emerald-400">PASS</span></div>
                  <div className="flex justify-between text-slate-400"><span>Length (42.3m)</span> <span className="text-emerald-400">PASS</span></div>
                  <div className="flex justify-between text-slate-400"><span>Insertion Loss</span> <span className="text-emerald-400">2.1 dB</span></div>
                  <div className="flex justify-between text-slate-400"><span>NEXT</span> <span className="text-emerald-400">42.1 dB</span></div>
                  <div className="text-slate-500 mt-2 text-[9px]">Tested: 08 Nov 24 by J.Okafor<br/>FLUKE DTX-1800 #FL-4821</div>
                </div>
              </div>

              <div>
                <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Network Assign</h3>
                <div className="space-y-1 bg-slate-900/50 p-2 rounded border border-slate-700/50 text-xs">
                  <PropRow label="VLAN" value="20 (Corp Data)" />
                  <PropRow label="IP Range" value="10.20.2.0/24" />
                  <PropRow label="PoE" value="Available" />
                  <PropRow label="Port Speed" value="1Gbps Auto" />
                </div>
              </div>

              <Separator className="bg-slate-700" />
              
              {/* Mini AV preview for context */}
              <div>
                <h3 className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1"><MonitorPlay className="w-3 h-3" /> Selected Room AV</h3>
                <div className="bg-slate-900 border border-slate-700 p-2 rounded text-xs space-y-1">
                  <div className="text-slate-300 font-medium mb-1">Meeting Room 201</div>
                  <PropRow label="Display" value="86&quot; Samsung QM86B" />
                  <PropRow label="Processor" value="Crestron DM" />
                  <PropRow label="Mic" value="Shure MXA910" />
                </div>
              </div>

            </div>
          </ScrollArea>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="h-8 bg-slate-900 border-t border-slate-700 flex items-center justify-between px-4 text-[10px] font-mono shrink-0">
        <div className="flex items-center gap-4 text-slate-400">
          <span className="text-emerald-400 font-bold">Level 2</span>
          <span>124 Data | 32 Voice | 18 AV</span>
          <Separator orientation="vertical" className="h-4 bg-slate-700" />
          <span>Max cable: 67.4m (Pass)</span>
          <Separator orientation="vertical" className="h-4 bg-slate-700" />
          <span className="flex items-center gap-1"><Wifi className="w-3 h-3 text-blue-400" /> 98.2% cvg @ -65dBm</span>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" className="h-6 text-[10px] text-emerald-400 hover:text-emerald-300 px-2">Cable Schedule</Button>
          <Button variant="ghost" size="sm" className="h-6 text-[10px] text-emerald-400 hover:text-emerald-300 px-2">Export Test Reports</Button>
        </div>
      </div>
    </div>
  );
}

function RibbonBtn({ icon, label, active = false }: { icon: React.ReactNode, label: string, active?: boolean }) {
  return (
    <div className={`flex flex-col items-center justify-center w-16 h-12 rounded cursor-pointer transition-colors group ${active ? 'bg-emerald-500/20 border border-emerald-500/30' : 'hover:bg-slate-700'}`}>
      <div className="mb-1 [&>svg]:w-4 [&>svg]:h-4">
        {icon}
      </div>
      <span className={`text-[9px] text-center leading-tight whitespace-nowrap px-1 overflow-hidden text-ellipsis w-full ${active ? 'text-emerald-400' : 'text-slate-400 group-hover:text-slate-200'}`}>{label}</span>
    </div>
  );
}

function NavNode({ title, expanded = false, active = false, children }: { title: string, expanded?: boolean, active?: boolean, children?: React.ReactNode }) {
  return (
    <div className="select-none">
      <div className={`flex items-center gap-1.5 py-1 px-2 rounded cursor-pointer hover:bg-slate-700/50 ${active ? "bg-emerald-500/20 text-emerald-400 font-medium" : "text-slate-300"}`}>
        <div className="w-4 h-4 flex items-center justify-center">
          {children ? (
            expanded ? <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 9l6 6 6-6"/></svg> : <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6"/></svg>
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

function PropRow({ label, value }: { label: string, value: string }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-slate-400">{label}</span>
      <span className="text-slate-200 text-right font-mono text-[10px]">{value}</span>
    </div>
  );
}
