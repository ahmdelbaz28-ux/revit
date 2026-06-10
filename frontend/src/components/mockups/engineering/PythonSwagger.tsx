import React, { useState, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { 
  Terminal, Play, Square, Trash2, Settings, ChevronRight, ChevronDown, Lock,
  FolderOpen, Code2, PlayCircle, Shield, Globe, Database, Cpu, Package, FileCode2,
  Box, Link2, Share2, Activity, Zap, CheckCircle2
} from "lucide-react";

export function PythonSwagger() {
  const [activeTab, setActiveTab] = useState("Terminal");
  const [swaggerExpanded, setSwaggerExpanded] = useState<Record<string, boolean>>({
    Projects: true,
    Drawings: false,
    Analysis: false,
    Compliance: false,
    AI: false
  });
  const [scriptExpanded, setScriptExpanded] = useState({
    my: true,
    analysis: true,
    automation: true,
    integrations: true,
    reporting: false
  });

  const toggleSwagger = (section: string) => {
    setSwaggerExpanded(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const [cursorVisible, setCursorVisible] = useState(true);
  useEffect(() => {
    const interval = setInterval(() => setCursorVisible(v => !v), 500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-900 text-slate-100 font-sans dark">
      {/* Top Toolbar */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-slate-800 bg-slate-950 shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded bg-[#FFD43B] flex items-center justify-center border border-[#FFD43B]/20">
              <span className="font-bold text-slate-900 text-xs">Py</span>
            </div>
            <h1 className="font-bold text-sm tracking-wide text-slate-200">Python Terminal & API Integration</h1>
          </div>
          <Separator orientation="vertical" className="h-5 bg-slate-800" />
          <div className="flex text-xs space-x-1">
            {["Terminal", "Script Editor", "API Explorer (Swagger)", "Packages", "Connections", "History"].map(tab => (
              <button
                key={tab}
                className={`px-3 py-1.5 rounded font-medium transition-colors ${activeTab === tab ? "bg-slate-800 text-blue-400" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="bg-slate-900 border-slate-700 text-slate-300 font-mono h-6 text-[10px]">Python 3.12.4</Badge>
          <Badge variant="outline" className="bg-purple-900/20 border-purple-500/30 text-purple-400 font-mono h-6 text-[10px]">env: nexuscad-env</Badge>
          <Separator orientation="vertical" className="h-5 bg-slate-800 mx-1" />
          <Button size="icon" variant="ghost" className="h-7 w-7 text-green-400 hover:text-green-300 hover:bg-green-400/10"><Play className="w-4 h-4" fill="currentColor"/></Button>
          <Button size="icon" variant="ghost" className="h-7 w-7 text-red-400 hover:text-red-300 hover:bg-red-400/10"><Square className="w-3.5 h-3.5" fill="currentColor"/></Button>
          <Button size="icon" variant="ghost" className="h-7 w-7 text-slate-400 hover:text-slate-200 hover:bg-slate-800"><Trash2 className="w-4 h-4"/></Button>
          <Button size="icon" variant="ghost" className="h-7 w-7 text-slate-400 hover:text-slate-200 hover:bg-slate-800"><Settings className="w-4 h-4"/></Button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel - Script Library */}
        <div className="w-[300px] flex flex-col border-r border-slate-800 bg-slate-900/40 shrink-0">
          <div className="p-2 border-b border-slate-800 bg-slate-900/60 font-semibold text-[11px] text-slate-400 uppercase tracking-wider">
            Scripts
          </div>
          <ScrollArea className="flex-1 border-b border-slate-800">
            <div className="p-2 text-xs font-mono text-slate-400 space-y-0.5">
              <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer text-slate-200">
                <ChevronDown className="w-3.5 h-3.5" /> <FolderOpen className="w-3.5 h-3.5 text-blue-400" /> My Scripts
              </div>
              <div className="pl-4 space-y-0.5 border-l border-slate-800 ml-2.5">
                
                {/* analysis folder */}
                <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer text-slate-300">
                  <ChevronDown className="w-3 h-3" /> <FolderOpen className="w-3.5 h-3.5 text-slate-500" /> analysis/
                </div>
                <div className="pl-4 space-y-0.5 border-l border-slate-800 ml-2">
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> load_flow_export.py</div>
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded bg-blue-500/15 text-blue-400 font-medium cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]" /> cable_sizing_batch.py</div>
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> compliance_checker.py</div>
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> arc_flash_calc.py</div>
                </div>

                {/* automation folder */}
                <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer text-slate-300">
                  <ChevronDown className="w-3 h-3" /> <FolderOpen className="w-3.5 h-3.5 text-slate-500" /> automation/
                </div>
                <div className="pl-4 space-y-0.5 border-l border-slate-800 ml-2">
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> auto_save_all.py</div>
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> batch_export_pdf.py</div>
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> drawing_renamer.py</div>
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> revision_bump.py</div>
                </div>

                {/* integrations folder */}
                <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer text-slate-300">
                  <ChevronDown className="w-3 h-3" /> <FolderOpen className="w-3.5 h-3.5 text-slate-500" /> integrations/
                </div>
                <div className="pl-4 space-y-0.5 border-l border-slate-800 ml-2">
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> etap_sync.py</div>
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> revit_link.py</div>
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> sharepoint_upload.py</div>
                  <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer"><FileCode2 className="w-3.5 h-3.5 text-[#FFD43B]/70" /> weather_api_fetch.py</div>
                </div>

                {/* reporting folder */}
                <div className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-slate-800 cursor-pointer text-slate-300">
                  <ChevronRight className="w-3 h-3" /> <FolderOpen className="w-3.5 h-3.5 text-slate-500" /> reporting/
                </div>

              </div>

              <div className="flex items-center gap-1.5 py-1.5 px-1 rounded hover:bg-slate-800 cursor-pointer text-slate-300 mt-2">
                <ChevronRight className="w-3.5 h-3.5 text-slate-500" /> <FolderOpen className="w-3.5 h-3.5 text-slate-500" /> Shared Scripts <span className="ml-auto text-[10px] text-slate-500">12</span>
              </div>
              <div className="flex items-center gap-1.5 py-1.5 px-1 rounded hover:bg-slate-800 cursor-pointer text-slate-300">
                <ChevronRight className="w-3.5 h-3.5 text-slate-500" /> <FolderOpen className="w-3.5 h-3.5 text-slate-500" /> System Scripts <span className="ml-auto text-[10px] text-slate-500">8</span>
              </div>
              <div className="flex items-center gap-1.5 py-1.5 px-1 rounded hover:bg-slate-800 cursor-pointer text-slate-300">
                <ChevronRight className="w-3.5 h-3.5 text-slate-500" /> <FolderOpen className="w-3.5 h-3.5 text-slate-500" /> Examples/
              </div>
            </div>
          </ScrollArea>
          
          {/* Packages */}
          <div className="h-[250px] flex flex-col bg-slate-900/80">
            <div className="p-2 border-b border-slate-800 flex justify-between items-center bg-slate-900/60">
              <span className="font-semibold text-[11px] text-slate-400 uppercase tracking-wider">Installed Packages</span>
              <Package className="w-3 h-3 text-slate-500" />
            </div>
            <ScrollArea className="flex-1">
              <div className="p-2 text-xs font-mono space-y-1 text-slate-400">
                <div className="flex justify-between items-center py-1 hover:bg-slate-800 px-1 rounded"><span className="text-purple-400 font-medium">nexuscad-api</span><span className="text-[10px]">4.2.1</span></div>
                <div className="flex justify-between items-center py-1 hover:bg-slate-800 px-1 rounded"><span className="text-slate-300">numpy</span><span className="text-[10px]">1.26.4</span></div>
                <div className="flex justify-between items-center py-1 hover:bg-slate-800 px-1 rounded"><span className="text-slate-300">pandas</span><span className="text-[10px]">2.2.1</span></div>
                <div className="flex justify-between items-center py-1 hover:bg-slate-800 px-1 rounded"><span className="text-slate-300">openpyxl</span><span className="text-[10px]">3.1.2</span></div>
                <div className="flex justify-between items-center py-1 hover:bg-slate-800 px-1 rounded"><span className="text-slate-300">requests</span><span className="text-[10px]">2.31.0</span></div>
                <div className="flex justify-between items-center py-1 hover:bg-slate-800 px-1 rounded"><span className="text-slate-300">shapely</span><span className="text-[10px]">2.0.4</span></div>
                <div className="flex justify-between items-center py-1 hover:bg-slate-800 px-1 rounded"><span className="text-slate-300">ifcopenshell</span><span className="text-[10px]">0.7.10</span></div>
                <div className="flex justify-between items-center py-1 hover:bg-slate-800 px-1 rounded"><span className="text-slate-300">pydantic</span><span className="text-[10px]">2.6.4</span></div>
              </div>
            </ScrollArea>
            <div className="p-2 border-t border-slate-800">
              <Button size="sm" variant="outline" className="w-full h-7 text-[10px] bg-slate-900 border-slate-700 text-slate-300 hover:bg-slate-800 border-dashed">+ Install Package</Button>
            </div>
          </div>
        </div>

        {/* Center Panel - Terminal */}
        <div className="flex-1 flex flex-col bg-[#020617] border-r border-slate-800 min-w-0 font-mono">
          <div className="h-10 border-b border-slate-800/80 flex items-center px-4 gap-3 bg-[#050B14]">
            <span className="text-xs text-slate-400 flex items-center gap-2"><Terminal className="w-3.5 h-3.5 text-blue-500" /> NexusCAD Pro Python Terminal — nexuscad-env</span>
          </div>
          
          <ScrollArea className="flex-1 text-[13px] leading-relaxed p-4 pb-0 text-slate-300">
            <div className="pb-4 space-y-1">
              <div className="text-slate-400">NexusCAD Pro Python Terminal v4.2.1</div>
              <div className="text-slate-400">Python 3.12.4 | nexuscad-env | Connected to: <span className="text-blue-400">Tower-B Office Complex</span></div>
              <div className="text-slate-400 mb-2">Type <span className="text-yellow-200">help()</span> for assistance, <span className="text-yellow-200">nexuscad.docs()</span> for API reference</div>
              <div className="text-slate-600 mb-4">━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</div>

              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100"><span className="text-purple-400">import</span> nexuscad <span className="text-purple-400">as</span> nc</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">project = nc.get_current_project()</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100"><span className="text-purple-400">print</span>(project.name)</span></div>
              <div className="text-blue-300">Tower-B Office Complex</div>
              <br/>

              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">drawings = project.get_drawings(filter=<span className="text-yellow-300">'electrical'</span>)</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100"><span className="text-purple-400">print</span>(<span className="text-yellow-300">f"Found <span className="text-blue-200">{'{'}</span><span className="text-slate-100">len(drawings)</span><span className="text-blue-200">{'}'}</span> electrical drawings"</span>)</span></div>
              <div className="text-blue-300">Found 18 electrical drawings</div>
              <br/>

              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-500 italic"># Run batch cable sizing check</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100"><span className="text-purple-400">from</span> nexuscad.analysis <span className="text-purple-400">import</span> CableSizer</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">sizer = CableSizer(standard=<span className="text-yellow-300">'IEC60364'</span>, project=project)</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">results = sizer.run_all()</span></div>
              <div className="text-slate-400">[INFO] Analyzing 124 cable runs...</div>
              <div className="text-slate-400">[INFO] Checking voltage drop (limit: 5.0%)...</div>
              <div className="text-yellow-400">[WARN] Cable EL-C-047: voltage drop 4.8% — approaching limit</div>
              <div className="text-green-400">[PASS] 123 cables within limits</div>
              <div className="text-yellow-400">[WARN] 1 cable requires attention</div>
              <br/>

              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">results.export_to_excel(<span className="text-yellow-300">'cable_sizing_report.xlsx'</span>)</span></div>
              <div className="text-slate-400">[INFO] Exported to: /projects/Tower-B/reports/cable_sizing_report.xlsx</div>
              <div className="text-green-400">✓ Done — 124 rows written</div>
              <br/>

              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-500 italic"># Connect to external weather API for solar calculations</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100"><span className="text-purple-400">import</span> requests</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">api_key = nc.secrets.get(<span className="text-yellow-300">'WEATHER_API_KEY'</span>)</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">resp = requests.get(<span className="text-yellow-300">f'https://api.openweathermap.org/data/2.5/weather?q=AbuDhabi&appid=<span className="text-blue-200">{'{'}</span><span className="text-slate-100">api_key</span><span className="text-blue-200">{'}'}</span>'</span>)</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">weather = resp.json()</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100"><span className="text-purple-400">print</span>(<span className="text-yellow-300">f"Solar irradiance location: <span className="text-blue-200">{'{'}</span><span className="text-slate-100">weather['coord']['lat']</span><span className="text-blue-200">{'}'}</span>, <span className="text-blue-200">{'{'}</span><span className="text-slate-100">weather['coord']['lon']</span><span className="text-blue-200">{'}'}</span>"</span>)</span></div>
              <div className="text-blue-300">Solar irradiance location: 24.4667, 54.3667</div>
              <br/>

              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-500 italic"># Access Swagger API directly</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">api = nc.api_client(base_url=<span className="text-yellow-300">'https://api.nexuscad.io/v4'</span>)</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100">endpoints = api.list_endpoints()</span></div>
              <div className="flex"><span className="text-green-400 mr-2 shrink-0">{">>>"}</span><span className="text-slate-100"><span className="text-purple-400">print</span>(<span className="text-yellow-300">f"Available endpoints: <span className="text-blue-200">{'{'}</span><span className="text-slate-100">len(endpoints)</span><span className="text-blue-200">{'}'}</span>"</span>)</span></div>
              <div className="text-blue-300">Available endpoints: 247</div>
              <br/>
              
              <div className="flex items-center">
                <span className="text-green-400 mr-2 shrink-0">{">>>"}</span>
                <span className={`w-2 h-4 bg-slate-300 inline-block ${cursorVisible ? 'opacity-100' : 'opacity-0'}`}></span>
              </div>
            </div>
          </ScrollArea>
          
          <div className="h-10 bg-[#050B14] border-t border-slate-800/80 flex items-center px-4 relative shrink-0">
            <span className="text-green-400 mr-2 font-mono text-[13px]">{">>>"}</span>
            <input type="text" className="bg-transparent border-none outline-none text-slate-100 font-mono text-[13px] flex-1 placeholder:text-slate-600" placeholder="Type python command..." />
          </div>
        </div>

        {/* Right Panel - Swagger API Explorer */}
        <div className="w-[340px] flex flex-col bg-slate-950 shrink-0">
          <div className="h-14 border-b border-slate-800 flex justify-between items-center px-4 bg-slate-900 shadow-sm shrink-0">
            <div className="flex flex-col">
              <div className="flex items-center gap-1.5"><Globe className="w-3.5 h-3.5 text-purple-400" /> <span className="font-bold text-slate-100 text-sm">NexusCAD API v4</span></div>
              <span className="text-[10px] text-slate-500 font-mono mt-0.5">OAS 3.1 — Swagger UI</span>
            </div>
            <Button size="icon" variant="outline" className="h-7 w-7 border-green-500/50 bg-green-500/10 hover:bg-green-500/20 text-green-400"><Lock className="w-3.5 h-3.5"/></Button>
          </div>
          <div className="p-3 border-b border-slate-800 bg-slate-900/50 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400 font-mono text-[10px]">https://api.nexuscad.io/v4</span>
              <Badge variant="outline" className="h-5 text-[9px] border-slate-700 bg-slate-800 text-slate-300">Try it out: ON</Badge>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">Auth:</span>
              <span className="text-green-400 flex items-center gap-1"><Shield className="w-3 h-3"/> Bearer Token</span>
            </div>
          </div>
          
          <ScrollArea className="flex-1">
            <div className="p-3 space-y-3 font-sans">
              
              {/* Projects Group */}
              <div className="border border-slate-800 rounded overflow-hidden">
                <div 
                  className="bg-slate-900 px-3 py-2 flex items-center justify-between cursor-pointer hover:bg-slate-800 transition-colors"
                  onClick={() => toggleSwagger('Projects')}
                >
                  <h3 className="font-bold text-sm text-slate-200">Projects</h3>
                  <div className="flex items-center gap-2">
                    <Badge className="h-5 px-1.5 text-[9px] bg-slate-800 text-slate-400 hover:bg-slate-800">7</Badge>
                    {swaggerExpanded.Projects ? <ChevronDown className="w-4 h-4 text-slate-500"/> : <ChevronRight className="w-4 h-4 text-slate-500"/>}
                  </div>
                </div>
                {swaggerExpanded.Projects && (
                  <div className="bg-slate-950 p-2 space-y-1.5 border-t border-slate-800">
                    <div className="flex items-center justify-between bg-slate-900 border border-slate-800 hover:border-green-500/50 p-1.5 rounded cursor-pointer group">
                      <div className="flex items-center gap-2">
                        <span className="bg-green-500 text-green-950 font-bold text-[9px] px-1.5 py-0.5 rounded w-10 text-center">GET</span>
                        <span className="text-xs font-mono text-slate-300">/projects</span>
                      </div>
                      <span className="text-[10px] text-slate-500 truncate max-w-[100px]">List all projects</span>
                    </div>
                    <div className="flex items-center justify-between bg-slate-900 border border-slate-800 hover:border-green-500/50 p-1.5 rounded cursor-pointer group">
                      <div className="flex items-center gap-2">
                        <span className="bg-green-500 text-green-950 font-bold text-[9px] px-1.5 py-0.5 rounded w-10 text-center">GET</span>
                        <span className="text-xs font-mono text-slate-300">/projects/{'{id}'}</span>
                      </div>
                      <span className="text-[10px] text-slate-500 truncate max-w-[100px]">Get project by ID</span>
                    </div>
                    <div className="flex items-center justify-between bg-slate-900 border border-slate-800 hover:border-blue-500/50 p-1.5 rounded cursor-pointer group">
                      <div className="flex items-center gap-2">
                        <span className="bg-blue-500 text-blue-950 font-bold text-[9px] px-1.5 py-0.5 rounded w-10 text-center">POST</span>
                        <span className="text-xs font-mono text-slate-300">/projects</span>
                      </div>
                      <span className="text-[10px] text-slate-500 truncate max-w-[100px]">Create new project</span>
                    </div>
                    <div className="flex items-center justify-between bg-slate-900 border border-slate-800 hover:border-orange-500/50 p-1.5 rounded cursor-pointer group">
                      <div className="flex items-center gap-2">
                        <span className="bg-orange-500 text-orange-950 font-bold text-[9px] px-1.5 py-0.5 rounded w-10 text-center">PUT</span>
                        <span className="text-xs font-mono text-slate-300">/projects/{'{id}'}</span>
                      </div>
                      <span className="text-[10px] text-slate-500 truncate max-w-[100px]">Update project</span>
                    </div>
                    <div className="flex items-center justify-between bg-slate-900 border border-slate-800 hover:border-red-500/50 p-1.5 rounded cursor-pointer group">
                      <div className="flex items-center gap-2">
                        <span className="bg-red-500 text-red-950 font-bold text-[9px] px-1.5 py-0.5 rounded w-10 text-center">DEL</span>
                        <span className="text-xs font-mono text-slate-300">/projects/{'{id}'}</span>
                      </div>
                      <span className="text-[10px] text-slate-500 truncate max-w-[100px]">Delete project</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Other Groups Collapsed */}
              {[
                { name: "Drawings", count: 12 },
                { name: "Analysis", count: 9 },
                { name: "Compliance", count: 6 },
                { name: "AI", count: 8 },
                { name: "Files", count: 11 },
                { name: "Reports", count: 8 },
                { name: "BIM", count: 10 },
                { name: "Users", count: 7 },
              ].map(group => (
                <div key={group.name} className="border border-slate-800 rounded overflow-hidden">
                  <div 
                    className="bg-slate-900 px-3 py-2 flex items-center justify-between cursor-pointer hover:bg-slate-800 transition-colors"
                    onClick={() => toggleSwagger(group.name)}
                  >
                    <h3 className="font-bold text-sm text-slate-200">{group.name}</h3>
                    <div className="flex items-center gap-2">
                      <Badge className="h-5 px-1.5 text-[9px] bg-slate-800 text-slate-400 hover:bg-slate-800">{group.count}</Badge>
                      {swaggerExpanded[group.name] ? <ChevronDown className="w-4 h-4 text-slate-500"/> : <ChevronRight className="w-4 h-4 text-slate-500"/>}
                    </div>
                  </div>
                  {swaggerExpanded[group.name] && group.name === "Analysis" && (
                    <div className="bg-slate-950 p-2 space-y-1.5 border-t border-slate-800">
                      <div className="flex items-center justify-between bg-blue-500/10 border border-blue-500/30 p-1.5 rounded cursor-pointer group">
                        <div className="flex items-center gap-2">
                          <span className="bg-blue-500 text-blue-950 font-bold text-[9px] px-1.5 py-0.5 rounded w-10 text-center">POST</span>
                          <span className="text-xs font-mono text-blue-400">/analysis/cable-size</span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between bg-slate-900 border border-slate-800 hover:border-blue-500/50 p-1.5 rounded cursor-pointer group">
                        <div className="flex items-center gap-2">
                          <span className="bg-blue-500 text-blue-950 font-bold text-[9px] px-1.5 py-0.5 rounded w-10 text-center">POST</span>
                          <span className="text-xs font-mono text-slate-300">/analysis/load-flow</span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between bg-slate-900 border border-slate-800 hover:border-blue-500/50 p-1.5 rounded cursor-pointer group">
                        <div className="flex items-center gap-2">
                          <span className="bg-blue-500 text-blue-950 font-bold text-[9px] px-1.5 py-0.5 rounded w-10 text-center">POST</span>
                          <span className="text-xs font-mono text-slate-300">/analysis/arc-flash</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Active Endpoint Detail */}
              <div className="mt-4 border border-blue-500/30 rounded bg-blue-950/20 overflow-hidden">
                <div className="bg-blue-900/30 px-3 py-2 border-b border-blue-500/30 flex items-center gap-2">
                  <span className="bg-blue-500 text-blue-950 font-bold text-[10px] px-1.5 py-0.5 rounded">POST</span>
                  <span className="text-sm font-mono text-blue-100">/analysis/cable-size</span>
                </div>
                <div className="p-3 space-y-3">
                  <p className="text-xs text-slate-300">Run cable sizing analysis per IEC 60364 or NEC</p>
                  
                  <div className="space-y-1">
                    <div className="text-[10px] font-bold text-slate-500 uppercase">Request Body (application/json)</div>
                    <div className="bg-slate-950 border border-slate-800 rounded p-2 text-xs font-mono text-slate-300 whitespace-pre">
<span className="text-slate-500">{'{'}</span>
  <span className="text-purple-300">"circuit_id"</span><span className="text-slate-500">:</span> <span className="text-yellow-300">"EL-C-047"</span><span className="text-slate-500">,</span>
  <span className="text-purple-300">"load_kw"</span><span className="text-slate-500">:</span> <span className="text-blue-300">157.25</span><span className="text-slate-500">,</span>
  <span className="text-purple-300">"voltage"</span><span className="text-slate-500">:</span> <span className="text-blue-300">480</span><span className="text-slate-500">,</span>
  <span className="text-purple-300">"length_m"</span><span className="text-slate-500">:</span> <span className="text-blue-300">145</span><span className="text-slate-500">,</span>
  <span className="text-purple-300">"standard"</span><span className="text-slate-500">:</span> <span className="text-yellow-300">"IEC60364"</span><span className="text-slate-500">,</span>
  <span className="text-purple-300">"method"</span><span className="text-slate-500">:</span> <span className="text-yellow-300">"B2"</span>
<span className="text-slate-500">{'}'}</span>
                    </div>
                  </div>
                  
                  <Button size="sm" className="w-full bg-blue-600 hover:bg-blue-500 text-white border-0 h-8">Execute</Button>
                  
                  <div className="space-y-1">
                    <div className="text-[10px] font-bold text-slate-500 uppercase">Responses</div>
                    <div className="bg-slate-950 border border-slate-800 rounded p-2 text-[10px] font-mono">
                      <div className="text-green-400 mb-1 flex items-center gap-1"><CheckCircle2 className="w-3 h-3"/> 200 OK</div>
                      <span className="text-slate-500">{'{'}</span> <span className="text-purple-300">"status"</span><span className="text-slate-500">:</span> <span className="text-yellow-300">"success"</span><span className="text-slate-500">,</span> <span className="text-purple-300">"size_mm2"</span><span className="text-slate-500">:</span> <span className="text-blue-300">120</span> <span className="text-slate-500">{'}'}</span>
                    </div>
                  </div>
                </div>
              </div>
              
            </div>
          </ScrollArea>
        </div>
      </div>

      {/* Bottom Status Bar */}
      <div className="h-7 bg-slate-900 border-t border-slate-800 flex items-center justify-between px-4 text-[10px] font-mono text-slate-400 shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-blue-400">Python 3.12.4</span>
          <Separator orientation="vertical" className="h-3 bg-slate-700" />
          <span>nexuscad-env</span>
          <Separator orientation="vertical" className="h-3 bg-slate-700" />
          <span>12 packages loaded</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-green-500"></div> API: Connected</span>
          <Separator orientation="vertical" className="h-3 bg-slate-700" />
          <span>v4.2.1</span>
          <Separator orientation="vertical" className="h-3 bg-slate-700" />
          <span>247 endpoints</span>
          <Separator orientation="vertical" className="h-3 bg-slate-700" />
          <span>Latency: 42ms</span>
          <Separator orientation="vertical" className="h-3 bg-slate-700 mx-1" />
          <span className="hover:text-slate-200 cursor-pointer text-slate-300 font-sans">Swagger UI</span>
          <span className="hover:text-slate-200 cursor-pointer text-slate-300 font-sans">ReDoc</span>
          <span className="hover:text-slate-200 cursor-pointer text-slate-300 font-sans">Download Spec</span>
        </div>
      </div>
    </div>
  );
}
