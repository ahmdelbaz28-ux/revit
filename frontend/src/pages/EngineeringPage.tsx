/**
 * EngineeringPage.tsx - Engineering calculations using CalculationEngine
 * Provides input forms for voltage drop, short circuit, cable sizing, load flow
 * Runs calculations using the ENGINE (not API) and displays results
 */
import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Calculator,
  Zap,
  ShieldAlert,
  Ruler,
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileText,
} from 'lucide-react';
import {
  calculateVoltageDrop,
  calculateShortCircuit,
  calculateCableSizing,
  calculateLoadFlow,
  checkBreakerCoordination,
  calculateEarthFaultLoop,
  calculatePowerFactorCorrection,
  generateCompleteReport,
  type CableMaterial,
  type InstallationMethod,
  type VoltageDropResult,
  type ShortCircuitResult,
  type CableSizingResult,
  type LoadFlowResult,
  type BreakerCoordinationResult,
  type EarthFaultResult,
  type PowerFactorCorrectionResult,
  type EngineeringReport,
} from '@/engine/CalculationEngine';

export function EngineeringPage() {
  const [activeTab, setActiveTab] = useState('voltage-drop');

  // Voltage Drop inputs
  const [vdCurrent, setVdCurrent] = useState('25');
  const [vdLength, setVdLength] = useState('50');
  const [vdMaterial, setVdMaterial] = useState<CableMaterial>('Cu');
  const [vdCrossSection, setVdCrossSection] = useState('2.5');
  const [vdPowerFactor, setVdPowerFactor] = useState('0.85');
  const [vdVoltage, setVdVoltage] = useState('230');
  const [vdResult, setVdResult] = useState<VoltageDropResult | null>(null);

  // Short Circuit inputs
  const [scVoltage, setScVoltage] = useState('400');
  const [scLength, setScLength] = useState('100');
  const [scMaterial, setScMaterial] = useState<CableMaterial>('Cu');
  const [scCrossSection, setScCrossSection] = useState('16');
  const [scBreakerRating, setScBreakerRating] = useState('25');
  const [scResult, setScResult] = useState<ShortCircuitResult | null>(null);

  // Cable Sizing inputs
  const [csLoadCurrent, setCsLoadCurrent] = useState('32');
  const [csMaterial, setCsMaterial] = useState<CableMaterial>('Cu');
  const [csInstallMethod, setCsInstallMethod] = useState<InstallationMethod>('conduit');
  const [csAmbientTemp, setCsAmbientTemp] = useState('30');
  const [csResult, setCsResult] = useState<CableSizingResult | null>(null);

  // Load Flow inputs
  const [lfPower, setLfPower] = useState('50');
  const [lfVoltage, setLfVoltage] = useState('400');
  const [lfPowerFactor, setLfPowerFactor] = useState('0.85');
  const [lfResult, setLfResult] = useState<LoadFlowResult | null>(null);

  // Complete Report
  const [report, setReport] = useState<EngineeringReport | null>(null);

  const handleVoltageDrop = () => {
    // BUG-41 FIX: Guard against NaN inputs — empty fields produce NaN via parseFloat('')
    // which silently propagates through calculations, producing "NaN%" with PASS/FAIL badges.
    const vals = [vdCurrent, vdLength, vdCrossSection, vdPowerFactor, vdVoltage];
    if (vals.some(v => !v || isNaN(parseFloat(v)))) return;
    const result = calculateVoltageDrop(
      parseFloat(vdCurrent),
      parseFloat(vdLength),
      vdMaterial,
      parseFloat(vdCrossSection),
      parseFloat(vdPowerFactor),
      parseFloat(vdVoltage),
    );
    // Don't display NaN results — they're meaningless and potentially dangerous
    if (result && !isNaN(result.percentage)) {
      setVdResult(result);
    }
  };

  const handleShortCircuit = () => {
    const vals = [scVoltage, scLength, scCrossSection, scBreakerRating];
    if (vals.some(v => !v || isNaN(parseFloat(v)))) return;
    const result = calculateShortCircuit(
      parseFloat(scVoltage),
      parseFloat(scLength),
      scMaterial,
      parseFloat(scCrossSection),
      50,
      parseFloat(scBreakerRating),
    );
    if (result && !isNaN(result.prospectiveCurrent)) {
      setScResult(result);
    }
  };

  const handleCableSizing = () => {
    const result = calculateCableSizing(
      parseFloat(csLoadCurrent),
      csMaterial,
      csInstallMethod,
      parseFloat(csAmbientTemp),
    );
    setCsResult(result);
  };

  const handleLoadFlow = () => {
    const result = calculateLoadFlow(
      parseFloat(lfPower),
      parseFloat(lfVoltage),
      parseFloat(lfPowerFactor),
    );
    setLfResult(result);
  };

  const handleCompleteReport = () => {
    const result = generateCompleteReport(
      parseFloat(vdCurrent),
      parseFloat(vdLength),
      vdMaterial,
      parseFloat(vdCrossSection),
      parseFloat(vdPowerFactor),
      parseFloat(vdVoltage),
      csInstallMethod,
      parseFloat(csAmbientTemp),
      parseFloat(scBreakerRating),
      parseFloat(scBreakerRating) / 2,
    );
    setReport(result);
  };

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">Engineering Calculations</h1>
            <p className="text-sm text-slate-400 mt-1">IEC 60364, IEC 60909 & NEC compliant calculations</p>
          </div>
          <Button
            className="bg-red-600 hover:bg-red-700 text-white border-none"
            onClick={handleCompleteReport}
          >
            <FileText className="h-4 w-4 mr-1" />
            Generate Full Report
          </Button>
        </div>

        {/* Complete Report */}
        {report && (
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg text-slate-100">Complete Engineering Report</CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-slate-400 hover:text-slate-200"
                  onClick={() => setReport(null)}
                >
                  Close
                </Button>
              </div>
              <CardDescription className="text-slate-400">
                Generated: {new Date(report.timestamp).toLocaleString()}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <ReportItem
                  title="Voltage Drop"
                  status={report.voltageDrop.status}
                  value={`${report.voltageDrop.percentage}%`}
                  detail={`Limit: ${report.voltageDrop.limit}%`}
                />
                <ReportItem
                  title="Short Circuit"
                  status={report.shortCircuit.status}
                  value={`${report.shortCircuit.prospectiveCurrent} kA`}
                  detail={`Breaker: ${report.shortCircuit.breakerRating} kA`}
                />
                <ReportItem
                  title="Cable Sizing"
                  status={report.cableSizing.suitable ? 'PASS' : 'FAIL'}
                  value={`${report.cableSizing.recommendedCrossSection} mm²`}
                  detail={`Ampacity: ${report.cableSizing.finalAmpacity}A`}
                />
                <ReportItem
                  title="Load Flow"
                  status={report.loadFlow.efficiency > 0.8 ? 'PASS' : 'FAIL'}
                  value={`${report.loadFlow.current}A`}
                  detail={`Efficiency: ${(report.loadFlow.efficiency * 100).toFixed(1)}%`}
                />
                <ReportItem
                  title="Breaker Coordination"
                  status={report.breakerCoordination.status}
                  value={`Ratio: ${report.breakerCoordination.coordinationRatio}`}
                  detail={report.breakerCoordination.recommendation}
                />
              </div>
            </CardContent>
          </Card>
        )}

        {/* Calculation Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-slate-800 border border-slate-700">
            <TabsTrigger value="voltage-drop" className="data-[state=active]:bg-slate-700 data-[state=active]:text-slate-100">
              <Zap className="h-4 w-4 mr-1" /> Voltage Drop
            </TabsTrigger>
            <TabsTrigger value="short-circuit" className="data-[state=active]:bg-slate-700 data-[state=active]:text-slate-100">
              <ShieldAlert className="h-4 w-4 mr-1" /> Short Circuit
            </TabsTrigger>
            <TabsTrigger value="cable-sizing" className="data-[state=active]:bg-slate-700 data-[state=active]:text-slate-100">
              <Ruler className="h-4 w-4 mr-1" /> Cable Sizing
            </TabsTrigger>
            <TabsTrigger value="load-flow" className="data-[state=active]:bg-slate-700 data-[state=active]:text-slate-100">
              <Activity className="h-4 w-4 mr-1" /> Load Flow
            </TabsTrigger>
          </TabsList>

          {/* Voltage Drop Tab */}
          <TabsContent value="voltage-drop">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="border-slate-700 bg-slate-800/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                    <Zap className="h-5 w-5 text-amber-400" /> Voltage Drop Calculator
                  </CardTitle>
                  <CardDescription className="text-slate-400">IEC 60364 voltage drop calculation</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Current (A)</Label>
                      <Input type="number" value={vdCurrent} onChange={(e) => setVdCurrent(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Length (m)</Label>
                      <Input type="number" value={vdLength} onChange={(e) => setVdLength(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Material</Label>
                      <Select value={vdMaterial} onValueChange={(v) => setVdMaterial(v as CableMaterial)}>
                        <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-800 border-slate-700">
                          <SelectItem value="Cu">Copper (Cu)</SelectItem>
                          <SelectItem value="Al">Aluminium (Al)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Cross Section (mm²)</Label>
                      <Input type="number" value={vdCrossSection} onChange={(e) => setVdCrossSection(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Power Factor</Label>
                      <Input type="number" step="0.01" value={vdPowerFactor} onChange={(e) => setVdPowerFactor(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Voltage (V)</Label>
                      <Input type="number" value={vdVoltage} onChange={(e) => setVdVoltage(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                  </div>
                  <Button className="w-full bg-red-600 hover:bg-red-700 text-white border-none" onClick={handleVoltageDrop}>
                    <Calculator className="h-4 w-4 mr-1" /> Calculate Voltage Drop
                  </Button>
                </CardContent>
              </Card>

              {/* Results */}
              {vdResult && (
                <Card className="border-slate-700 bg-slate-800/80">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                      Results
                      <StatusBadge status={vdResult.status} />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                      <ResultItem label="Voltage Drop" value={`${vdResult.percentage}%`} />
                      <ResultItem label="Absolute Drop" value={`${vdResult.absoluteVoltage} V`} />
                      <ResultItem label="Limit" value={`${vdResult.limit}%`} />
                      <ResultItem label="Status" value={vdResult.status} highlight={vdResult.status} />
                    </div>
                    <Separator className="bg-slate-700" />
                    <div className="space-y-1">
                      <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">Formula</div>
                      <div className="text-xs font-mono text-slate-300 bg-slate-900 p-3 rounded-lg border border-slate-700">
                        {vdResult.formula}
                      </div>
                    </div>
                    <Separator className="bg-slate-700" />
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <ResultItem label="Resistance" value={`${vdResult.details.resistance} Ω/km`} />
                      <ResultItem label="Reactance" value={`${vdResult.details.reactance} Ω/km`} />
                      <ResultItem label="Current" value={`${vdResult.details.current} A`} />
                      <ResultItem label="Length" value={`${vdResult.details.length} m`} />
                      <ResultItem label="Power Factor" value={`${vdResult.details.powerFactor}`} />
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          {/* Short Circuit Tab */}
          <TabsContent value="short-circuit">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="border-slate-700 bg-slate-800/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                    <ShieldAlert className="h-5 w-5 text-red-400" /> Short Circuit Calculator
                  </CardTitle>
                  <CardDescription className="text-slate-400">IEC 60909 simplified short circuit calculation</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Nominal Voltage (V)</Label>
                      <Input type="number" value={scVoltage} onChange={(e) => setScVoltage(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Cable Length (m)</Label>
                      <Input type="number" value={scLength} onChange={(e) => setScLength(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Material</Label>
                      <Select value={scMaterial} onValueChange={(v) => setScMaterial(v as CableMaterial)}>
                        <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-800 border-slate-700">
                          <SelectItem value="Cu">Copper (Cu)</SelectItem>
                          <SelectItem value="Al">Aluminium (Al)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Cross Section (mm²)</Label>
                      <Input type="number" value={scCrossSection} onChange={(e) => setScCrossSection(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Breaker Rating (kA)</Label>
                      <Input type="number" value={scBreakerRating} onChange={(e) => setScBreakerRating(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                  </div>
                  <Button className="w-full bg-red-600 hover:bg-red-700 text-white border-none" onClick={handleShortCircuit}>
                    <Calculator className="h-4 w-4 mr-1" /> Calculate Short Circuit
                  </Button>
                </CardContent>
              </Card>

              {scResult && (
                <Card className="border-slate-700 bg-slate-800/80">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                      Results
                      <StatusBadge status={scResult.status} />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <ResultItem label="Prospective Current" value={`${scResult.prospectiveCurrent} kA`} />
                    <ResultItem label="Cable Breaking Capacity" value={`${scResult.cableBreakingCapacity} kA`} />
                    <ResultItem label="Breaker Rating" value={`${scResult.breakerRating} kA`} />
                    <ResultItem label="Min Required Breaking Cap." value={`${scResult.minRequiredBreakingCapacity} kA`} />
                    <Separator className="bg-slate-700" />
                    <div className="text-xs font-mono text-slate-300 bg-slate-900 p-3 rounded-lg border border-slate-700">
                      Isc = Unom / (√3 × Z)<br/>
                      Min. Breaking Capacity = Isc × 1.25 (25% margin)
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          {/* Cable Sizing Tab */}
          <TabsContent value="cable-sizing">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="border-slate-700 bg-slate-800/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                    <Ruler className="h-5 w-5 text-blue-400" /> Cable Sizing Calculator
                  </CardTitle>
                  <CardDescription className="text-slate-400">IEC 60364 cable sizing with derating</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Load Current (A)</Label>
                      <Input type="number" value={csLoadCurrent} onChange={(e) => setCsLoadCurrent(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Material</Label>
                      <Select value={csMaterial} onValueChange={(v) => setCsMaterial(v as CableMaterial)}>
                        <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-800 border-slate-700">
                          <SelectItem value="Cu">Copper (Cu)</SelectItem>
                          <SelectItem value="Al">Aluminium (Al)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Installation Method</Label>
                      <Select value={csInstallMethod} onValueChange={(v) => setCsInstallMethod(v as InstallationMethod)}>
                        <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-800 border-slate-700">
                          <SelectItem value="conduit">Conduit</SelectItem>
                          <SelectItem value="tray">Cable Tray</SelectItem>
                          <SelectItem value="direct_buried">Direct Buried</SelectItem>
                          <SelectItem value="free_air">Free Air</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Ambient Temp (°C)</Label>
                      <Input type="number" value={csAmbientTemp} onChange={(e) => setCsAmbientTemp(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                  </div>
                  <Button className="w-full bg-red-600 hover:bg-red-700 text-white border-none" onClick={handleCableSizing}>
                    <Calculator className="h-4 w-4 mr-1" /> Calculate Cable Size
                  </Button>
                </CardContent>
              </Card>

              {csResult && (
                <Card className="border-slate-700 bg-slate-800/80">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                      Results
                      <StatusBadge status={csResult.suitable ? 'PASS' : 'FAIL'} />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <ResultItem label="Recommended Cross Section" value={`${csResult.recommendedCrossSection} mm²`} />
                    <ResultItem label="Base Ampacity" value={`${csResult.ampacity} A`} />
                    <ResultItem label="Derating Factor" value={`${csResult.deratingFactor}`} />
                    <ResultItem label="Ambient Temp Factor" value={`${csResult.ambientTempFactor}`} />
                    <ResultItem label="Installation Factor" value={`${csResult.installationFactor}`} />
                    <ResultItem label="Final Ampacity" value={`${csResult.finalAmpacity} A`} />
                    <Separator className="bg-slate-700" />
                    <div className="text-xs font-mono text-slate-300 bg-slate-900 p-3 rounded-lg border border-slate-700">
                      Derating = Installation Factor × Temp Factor<br/>
                      Final Ampacity = Base Ampacity × Derating<br/>
                      Suitable if Final Ampacity ≥ Load Current ({csLoadCurrent}A)
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          {/* Load Flow Tab */}
          <TabsContent value="load-flow">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="border-slate-700 bg-slate-800/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                    <Activity className="h-5 w-5 text-emerald-400" /> Load Flow Analysis
                  </CardTitle>
                  <CardDescription className="text-slate-400">Power system load flow calculation</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Real Power (kW)</Label>
                      <Input type="number" value={lfPower} onChange={(e) => setLfPower(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Voltage (V)</Label>
                      <Input type="number" value={lfVoltage} onChange={(e) => setLfVoltage(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Power Factor</Label>
                      <Input type="number" step="0.01" value={lfPowerFactor} onChange={(e) => setLfPowerFactor(e.target.value)} className="bg-slate-900 border-slate-600 text-slate-100" />
                    </div>
                  </div>
                  <Button className="w-full bg-red-600 hover:bg-red-700 text-white border-none" onClick={handleLoadFlow}>
                    <Calculator className="h-4 w-4 mr-1" /> Calculate Load Flow
                  </Button>
                </CardContent>
              </Card>

              {lfResult && (
                <Card className="border-slate-700 bg-slate-800/80">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                      Results
                      <StatusBadge status={lfResult.efficiency > 0.8 ? 'PASS' : 'FAIL'} />
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <ResultItem label="Voltage" value={`${lfResult.voltage} V`} />
                    <ResultItem label="Current" value={`${lfResult.current} A`} />
                    <ResultItem label="Real Power" value={`${lfResult.power} kW`} />
                    <ResultItem label="Apparent Power" value={`${lfResult.apparentPower} kVA`} />
                    <ResultItem label="Reactive Power" value={`${lfResult.reactivePower} kVAr`} />
                    <ResultItem label="Efficiency" value={`${(lfResult.efficiency * 100).toFixed(1)}%`} />
                    <Separator className="bg-slate-700" />
                    <div className="text-xs font-mono text-slate-300 bg-slate-900 p-3 rounded-lg border border-slate-700">
                      S = P / cosφ<br/>
                      Q = S × sinφ<br/>
                      I = S / (√3 × U)<br/>
                      η = cosφ × 0.95 (assumed 95% motor efficiency)
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

// ============================================================================
// Sub-components
// ============================================================================

function StatusBadge({ status }: { status: string }) {
  if (status === 'PASS') {
    return (
      <Badge className="bg-emerald-600/20 text-emerald-400 border-emerald-500/30 hover:bg-emerald-600/20">
        <CheckCircle2 className="h-3 w-3 mr-1" /> PASS
      </Badge>
    );
  }
  if (status === 'FAIL') {
    return (
      <Badge variant="destructive" className="bg-red-600/20 text-red-400 border-red-500/30 hover:bg-red-600/20">
        <XCircle className="h-3 w-3 mr-1" /> FAIL
      </Badge>
    );
  }
  if (status === 'WARNING') {
    return (
      <Badge className="bg-amber-600/20 text-amber-400 border-amber-500/30 hover:bg-amber-600/20">
        <AlertTriangle className="h-3 w-3 mr-1" /> WARNING
      </Badge>
    );
  }
  if (status === 'PROPER') {
    return (
      <Badge className="bg-emerald-600/20 text-emerald-400 border-emerald-500/30 hover:bg-emerald-600/20">
        <CheckCircle2 className="h-3 w-3 mr-1" /> PROPER
      </Badge>
    );
  }
  return <Badge variant="outline">{status}</Badge>;
}

function ResultItem({ label, value, highlight }: { label: string; value: string; highlight?: string }) {
  return (
    <div className="flex justify-between items-center py-1">
      <span className="text-xs text-slate-400">{label}</span>
      <span className={`text-sm font-mono ${highlight === 'PASS' ? 'text-emerald-400 font-bold' : highlight === 'FAIL' ? 'text-red-400 font-bold' : 'text-slate-200'}`}>
        {value}
      </span>
    </div>
  );
}

function ReportItem({ title, status, value, detail }: { title: string; status: string; value: string; detail: string }) {
  return (
    <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-700/50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-slate-300">{title}</span>
        <StatusBadge status={status} />
      </div>
      <div className="text-lg font-bold text-slate-100">{value}</div>
      <div className="text-xs text-slate-400 mt-1">{detail}</div>
    </div>
  );
}
