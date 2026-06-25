import React from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { 
  History, Calendar, Users, Filter, Search, Download, 
  GitCommit, GitBranch, ShieldCheck, CheckCircle2,
  FileText, Activity, AlertTriangle
} from "lucide-react";

export function AuditTrail() {
  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground dark font-sans">
      {/* Header */}
      <div className="flex flex-col border-b bg-card shrink-0">
        <div className="h-12 flex items-center justify-between px-4 border-b border-border/50">
          <div className="flex items-center gap-4">
            <History className="h-5 w-5 text-blue-400" />
            <div className="font-bold tracking-wider text-sm">Engineering Audit Trail & Revision History</div>
            <Separator orientation="vertical" className="h-5" />
            <div className="text-sm text-slate-300">Project: Tower-B Office Complex</div>
          </div>
        </div>
        <div className="h-12 flex items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <div className="flex items-center bg-background border rounded-md px-3 h-8 text-xs text-muted-foreground w-48 cursor-text">
              <Calendar className="h-3.5 w-3.5 mr-2" /> Last 30 Days
            </div>
            <div className="flex items-center bg-background border rounded-md px-3 h-8 text-xs text-muted-foreground w-40 cursor-pointer">
              <Users className="h-3.5 w-3.5 mr-2" /> All Users
            </div>
            <div className="flex items-center bg-background border rounded-md px-3 h-8 text-xs text-muted-foreground w-40 cursor-pointer">
              <Filter className="h-3.5 w-3.5 mr-2" /> All Actions
            </div>
            <div className="flex items-center bg-background border rounded-md px-3 h-8 text-xs text-muted-foreground w-64 cursor-pointer">
              <FileText className="h-3.5 w-3.5 mr-2" /> Tower-B-Electrical-Floor3.dwg
            </div>
            <div className="relative">
              <Input className="h-8 w-64 text-xs bg-background pr-8" placeholder="Search logs..." />
              <Search className="h-3.5 w-3.5 absolute right-2.5 top-2.5 text-muted-foreground" />
            </div>
          </div>
          <Button size="sm" variant="outline" className="h-8 text-xs border-slate-700">
            <Download className="h-3.5 w-3.5 mr-1" /> Export Audit Log
          </Button>
        </div>
        {/* Active Filters */}
        <div className="h-8 bg-slate-900/50 flex items-center px-4 gap-2 text-[10px]">
          <span className="text-muted-foreground">Active Filters:</span>
          <Badge variant="outline" className="bg-slate-800 text-slate-300 border-slate-700 h-5 px-2">Last 30 days ✕</Badge>
          <Badge variant="outline" className="bg-slate-800 text-slate-300 border-slate-700 h-5 px-2">All Users ✕</Badge>
          <Badge variant="outline" className="bg-slate-800 text-slate-300 border-slate-700 h-5 px-2">All Actions ✕</Badge>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Column - Revision Tree */}
        <div className="w-[280px] flex flex-col border-r bg-card/30 shrink-0">
          <div className="flex border-b bg-card/40 overflow-x-auto scrollbar-hide text-[11px]">
            <div className="px-3 py-2 border-b-2 border-blue-500 text-blue-400 font-medium whitespace-nowrap cursor-pointer">Tower-B-Electrical...</div>
            <div className="px-3 py-2 text-muted-foreground whitespace-nowrap cursor-pointer hover:text-foreground">Fire-Alarm-Plan.dwg</div>
          </div>
          <ScrollArea className="flex-1 p-4">
            <div className="space-y-0 relative before:absolute before:inset-0 before:ml-[11px] before:w-[2px] before:bg-slate-700">
              
              <RevNode rev="14" time="TODAY 14:32" user="Ahmed Al-Rashidi" msg="Final compliance corrections" current />
              <div className="h-6"></div>
              <RevNode rev="13" time="Yesterday 16:45" user="Sarah Chen" msg="Updated panel LP-3A load schedule" />
              <div className="h-6"></div>
              <RevNode rev="12" time="Nov 12 11:20" user="Ahmed" msg="Added circuit breaker coordination notes" />
              <div className="h-6"></div>
              <RevNode rev="11" time="Nov 10 09:15" user="Marcus Williams" msg="Approved for client review" approved />
              <div className="h-6"></div>
              <RevNode rev="10" time="Nov 8 14:02" user="James Okafor" msg="Compliance check corrections" />
              <div className="h-6"></div>
              <RevNode rev="9" time="Nov 7 16:30" user="Fatima Al-Zahra" msg="Added grounding symbols" />
              <div className="h-6"></div>
              <RevNode rev="8" time="Nov 5 10:00" user="Ahmed" msg="Initial electrical layout" />
              
            </div>
          </ScrollArea>
          <div className="p-3 border-t bg-card/50 space-y-2">
            <Button variant="outline" className="w-full text-xs h-8">Compare Revisions</Button>
            <Button variant="outline" className="w-full text-xs h-8">Restore Revision</Button>
            <Button variant="outline" className="w-full text-xs h-8"><GitBranch className="h-3.5 w-3.5 mr-1" /> Branch from Here</Button>
          </div>
        </div>

        {/* Center Column - Audit Log */}
        <div className="flex-1 flex flex-col bg-[#0a0a0f] overflow-hidden">
          <div className="flex border-b border-slate-800 bg-slate-900/80 text-[11px] uppercase tracking-wider font-semibold text-muted-foreground px-2">
            <button className="px-4 py-2 text-foreground border-b-2 border-blue-500">All Events</button>
            <button className="px-4 py-2 hover:text-foreground">Drawing Changes</button>
            <button className="px-4 py-2 hover:text-foreground">File Operations</button>
            <button className="px-4 py-2 hover:text-foreground">Analysis Runs</button>
            <button className="px-4 py-2 hover:text-foreground">User Access</button>
            <button className="px-4 py-2 hover:text-foreground">System Events</button>
          </div>
          
          <ScrollArea className="flex-1">
            <table className="w-full text-left text-xs whitespace-nowrap">
              <thead className="bg-slate-800/80 text-slate-400 sticky top-0 z-10 border-b border-slate-700">
                <tr>
                  <th className="px-4 py-2 font-medium w-24">Timestamp</th>
                  <th className="px-4 py-2 font-medium w-32">User</th>
                  <th className="px-4 py-2 font-medium w-48">Action</th>
                  <th className="px-4 py-2 font-medium">Detail</th>
                  <th className="px-4 py-2 font-medium w-48">File</th>
                  <th className="px-4 py-2 font-medium w-32 text-right">IP/Device</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 font-mono">
                <LogRow time="14:47:03" user="Ahmed Al-Rashidi" action="COMPLIANCE_CHECK_RUN" type="yellow" msg="NEC 2023 check — 3 critical, 8 warnings" file="All drawings" dev="WS-AHM-01" />
                
                {/* Selected Row */}
                <tr className="bg-blue-500/10 border-l-2 border-l-blue-500 hover:bg-blue-500/20 cursor-pointer text-slate-200">
                  <td className="px-4 py-2.5">14:43:21</td>
                  <td className="px-4 py-2.5 text-slate-300">Ahmed Al-Rashidi</td>
                  <td className="px-4 py-2.5 text-blue-400 font-bold text-[10px]">ELEMENT_MODIFIED</td>
                  <td className="px-4 py-2.5 truncate max-w-[300px]" title="Panel LP-3A: voltage rating changed 240V→480V">Panel LP-3A: voltage rating changed 240V→480V</td>
                  <td className="px-4 py-2.5 text-slate-400 truncate max-w-[150px]">Electrical-Floor3.dwg Rev14</td>
                  <td className="px-4 py-2.5 text-slate-500 text-right">WS-AHM-01</td>
                </tr>

                <LogRow time="14:32:17" user="Ahmed Al-Rashidi" action="REVISION_SAVED" type="green" msg="Revision 14 saved: 'Final compliance...'" file="Electrical-Floor3.dwg" dev="WS-AHM-01" />
                <LogRow time="14:31:58" user="System" action="BIM_SYNC" type="slate" msg="BIM model synchronized with Revit v14" file="BIM-Model.rvt" dev="Server" isSystem />
                <LogRow time="14:28:44" user="Sarah Chen" action="COMMENT_ADDED" type="blue" msg="Comment on Panel LP-3A: 'Verify load schedule'" file="Electrical-Floor3.dwg" dev="Laptop-SC-03" />
                <LogRow time="14:15:02" user="James Okafor" action="FILE_EXPORTED" type="orange" msg="Exported compliance report to PDF (4.2MB)" file="Compliance-Report.pdf" dev="WS-JO-02" />
                <LogRow time="14:03:39" user="Fatima Al-Zahra" action="ELEMENT_ADDED" type="blue" msg="Smoke detector SD-051 added at Room 312" file="Fire-Alarm-Plan.dwg" dev="WS-FA-04" />
                
                <tr className="bg-slate-900 border-l-2 border-l-emerald-500 hover:bg-slate-800 cursor-pointer">
                  <td className="px-4 py-2.5 text-slate-300">13:55:12</td>
                  <td className="px-4 py-2.5 text-slate-300">Marcus Williams</td>
                  <td className="px-4 py-2.5 text-emerald-400 font-bold text-[10px]">APPROVAL_GRANTED</td>
                  <td className="px-4 py-2.5 text-emerald-100 font-bold truncate max-w-[300px]">Rev 14 approved for client submission</td>
                  <td className="px-4 py-2.5 text-slate-400 truncate max-w-[150px]">Load-Calculations.xlsx</td>
                  <td className="px-4 py-2.5 text-slate-500 text-right">Laptop-MW-01</td>
                </tr>

                <LogRow time="13:44:28" user="System" action="AUTOSAVE" type="slate" msg="Auto-save complete — all 5 files" file="All" dev="Server" isSystem />
                <LogRow time="13:32:01" user="Ahmed Al-Rashidi" action="ANALYSIS_RUN" type="purple" msg="Arc flash study run — labels generated for 6..." file="All" dev="WS-AHM-01" />
                <LogRow time="13:21:47" user="James Okafor" action="FILE_IMPORTED" type="orange" msg="IFC model imported (MEP-Coord-v3, 89MB)" file="MEP-Coordination.ifc" dev="WS-JO-02" />
                <LogRow time="13:10:22" user="Sarah Chen" action="SESSION_START" type="slate" msg="Collaboration session joined (SES-2024-4821)" file="—" dev="Laptop-SC-03" />
                <LogRow time="13:04:55" user="Ahmed Al-Rashidi" action="SESSION_START" type="slate" msg="Collaboration session started (SES-2024-4821)" file="—" dev="WS-AHM-01" />
              </tbody>
            </table>
          </ScrollArea>
        </div>

        {/* Right Column - Event Detail */}
        <div className="w-[300px] flex flex-col border-l bg-card/30 shrink-0">
          <div className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-foreground border-b flex justify-between items-center bg-card/40">
            <span>Event Details</span>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-4 space-y-6">
              
              <div>
                <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/30 text-[10px] mb-2">ELEMENT_MODIFIED</Badge>
                <h3 className="font-bold text-sm leading-tight text-white mb-4">Panel LP-3A Properties Updated</h3>
                
                <div className="space-y-2">
                  <PropRow label="Event ID" value="EVT-2024-114823" />
                  <PropRow label="Time" value="Today 14:43:21 UTC+3" />
                  <PropRow label="User" value="Ahmed Al-Rashidi" />
                  <PropRow label="Role" value="Project Lead" />
                  <PropRow label="Category" value="Drawing Change" />
                  <PropRow label="File" value="Tower-B-Electrical.dwg" />
                  <PropRow label="Element" value="PNL-003 (Panel LP-3A)" />
                </div>
              </div>

              <div>
                <h4 className="text-xs font-bold text-muted-foreground uppercase border-b border-border/50 pb-1 mb-2">Change Details (Diff)</h4>
                <div className="bg-slate-900 border border-slate-700 rounded-md overflow-hidden text-xs">
                  <table className="w-full text-left font-mono">
                    <thead className="bg-slate-800 text-slate-400">
                      <tr>
                        <th className="px-2 py-1.5 font-medium">Property</th>
                        <th className="px-2 py-1.5 font-medium">Before</th>
                        <th className="px-2 py-1.5 font-medium">After</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      <tr>
                        <td className="px-2 py-1.5 text-slate-300">Voltage</td>
                        <td className="px-2 py-1.5 text-red-400 line-through">240V</td>
                        <td className="px-2 py-1.5 text-emerald-400">480V</td>
                      </tr>
                      <tr>
                        <td className="px-2 py-1.5 text-slate-300">Ampacity</td>
                        <td className="px-2 py-1.5 text-red-400 line-through">200A</td>
                        <td className="px-2 py-1.5 text-emerald-400">400A</td>
                      </tr>
                      <tr>
                        <td className="px-2 py-1.5 text-slate-300">Phase</td>
                        <td className="px-2 py-1.5 text-red-400 line-through">1Φ</td>
                        <td className="px-2 py-1.5 text-emerald-400">3Φ</td>
                      </tr>
                      <tr>
                        <td className="px-2 py-1.5 text-slate-300">Location</td>
                        <td className="px-2 py-1.5 text-slate-500">"Level 3..."</td>
                        <td className="px-2 py-1.5 text-emerald-400">"Level 3, El..."</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <h4 className="text-xs font-bold text-muted-foreground uppercase border-b border-border/50 pb-1 mb-2">Impact Analysis</h4>
                <div className="space-y-2">
                  <div className="flex items-start gap-2 text-orange-400 bg-orange-500/10 border border-orange-500/30 rounded p-2 text-xs">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <div>
                      <span className="font-bold">Load Calculations:</span> Recalculation required
                    </div>
                  </div>
                  <div className="flex items-start gap-2 text-slate-300 bg-slate-800 rounded p-2 text-xs">
                    <Activity className="h-4 w-4 shrink-0 text-blue-400" />
                    <div>
                      <span className="font-bold text-white">Connected Elements:</span> 8 circuits affected
                    </div>
                  </div>
                  <div className="flex items-start gap-2 text-orange-400 bg-orange-500/10 border border-orange-500/30 rounded p-2 text-xs">
                    <ShieldCheck className="h-4 w-4 shrink-0" />
                    <div>
                      <span className="font-bold">Compliance:</span> Re-check NEC §408 required
                    </div>
                  </div>
                </div>
              </div>

              <div className="pt-2 flex flex-col gap-2">
                <Button variant="outline" className="w-full text-xs h-8 border-slate-600 bg-slate-800">Restore to Before</Button>
                <div className="flex gap-2">
                  <Button variant="outline" className="flex-1 text-xs h-8 border-slate-700">View Full Diff</Button>
                  <Button variant="outline" className="flex-1 text-xs h-8 border-slate-700">Flag for Review</Button>
                </div>
              </div>

            </div>
          </ScrollArea>
        </div>
      </div>

      {/* Bottom Console */}
      <div className="h-10 border-t bg-card flex items-center justify-between px-4 text-[11px] shrink-0 text-slate-400">
        <div className="flex items-center gap-4">
          <span>Showing 13 of 1,247 events today</span>
          <Separator orientation="vertical" className="h-4" />
          <span>Total project events: 48,392</span>
          <Separator orientation="vertical" className="h-4" />
          <span>Retention: 7 years (Enterprise Policy)</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="cursor-pointer hover:text-foreground underline">Configure Retention</span>
          <span className="cursor-pointer hover:text-foreground underline">Generate Audit Certificate</span>
        </div>
      </div>
    </div>
  );
}

function RevNode({ rev, time, user, msg, current, approved }: any) {
  return (
    <div className="relative pl-6">
      {/* Node Dot */}
      {approved ? (
        <div className="absolute left-0 top-1 w-6 h-6 -ml-[12px] rounded-full bg-slate-900 border-2 border-emerald-500 flex items-center justify-center z-10">
          <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
        </div>
      ) : (
        <div className="absolute left-0 top-1.5 w-3 h-3 -ml-[5.5px] rounded-full bg-slate-700 border-2 border-slate-900 z-10"></div>
      )}

      <div className="bg-slate-800/50 border border-slate-700 rounded p-2 hover:bg-slate-800 transition-colors cursor-pointer">
        <div className="flex justify-between items-start mb-1">
          <div className="flex items-center gap-2">
            <span className="font-bold text-white">Rev {rev}</span>
            {current && <Badge className="bg-blue-500/20 text-blue-400 border-transparent text-[8px] h-4 px-1 py-0 font-normal">CURRENT</Badge>}
            {approved && <Badge className="bg-emerald-500/20 text-emerald-400 border-transparent text-[8px] h-4 px-1 py-0 font-normal"><CheckCircle2 className="w-2.5 h-2.5 mr-0.5" /> APPROVED</Badge>}
          </div>
          <span className="text-[10px] text-slate-400">{time}</span>
        </div>
        <div className="text-slate-300 mb-1">{msg}</div>
        <div className="text-[10px] text-slate-500">by {user}</div>
      </div>
    </div>
  );
}

function LogRow({ time, user, action, type, msg, file, dev, isSystem }: any) {
  let border = "border-l-slate-700";
  if (type === "yellow") border = "border-l-yellow-500";
  if (type === "blue") border = "border-l-blue-500";
  if (type === "green") border = "border-l-emerald-500";
  if (type === "purple") border = "border-l-purple-500";
  if (type === "orange") border = "border-l-orange-500";

  const textStyle = isSystem ? "text-slate-500 italic" : "text-slate-300";

  return (
    <tr className={`bg-slate-900 border-l-2 ${border} hover:bg-slate-800 cursor-pointer`}>
      <td className={`px-4 py-2.5 ${isSystem ? "text-slate-500" : "text-slate-400"}`}>{time}</td>
      <td className={`px-4 py-2.5 ${textStyle}`}>{user}</td>
      <td className={`px-4 py-2.5 text-slate-400 font-bold text-[10px]`}>{action}</td>
      <td className={`px-4 py-2.5 truncate max-w-[300px] ${textStyle}`} title={msg}>{msg}</td>
      <td className={`px-4 py-2.5 text-slate-400 truncate max-w-[150px]`}>{file}</td>
      <td className={`px-4 py-2.5 text-slate-500 text-right`}>{dev}</td>
    </tr>
  );
}

function PropRow({ label, value }: { label: string, value: string }) {
  return (
    <div className="flex justify-between items-center text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-foreground text-right">{value}</span>
    </div>
  );
}
