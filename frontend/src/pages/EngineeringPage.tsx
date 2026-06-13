/**
 * EngineeringPage.tsx - Engineering calculations using CalculationEngine
 * Provides input forms for voltage drop, short circuit, cable sizing, load flow
 * Runs calculations using the ENGINE (not API) and displays results
 *
 * SAFETY-CRITICAL: All numeric inputs are validated before calculation.
 * Invalid inputs show red borders and error messages. Calculate buttons
 * are disabled when inputs are out of range.
 */
import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
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

// ============================================================================
// VALIDATION SYSTEM - Safety-critical input validation
// ============================================================================

interface ValidationRule {
  min?: number;
  max?: number;
  allowNegative?: boolean;
  allowZero?: boolean;
  label: string;
}

interface ValidationResult {
  isValid: boolean;
  error: string | null;
}

/** Valid AWG sizes from 14 to 4/0 */
const VALID_AWG_SIZES = ['14', '12', '10', '8', '6', '4', '3', '2', '1', '1/0', '2/0', '3/0', '4/0'];

function validateNumeric(value: string, rule: ValidationRule): ValidationResult {
  if (!value || value.trim() === '') {
    return { isValid: false, error: `${rule.label} is required` };
  }

  const num = parseFloat(value);

  if (isNaN(num)) {
    return { isValid: false, error: `${rule.label} must be a valid number` };
  }

  if (!isFinite(num)) {
    return { isValid: false, error: `${rule.label} must be a finite number` };
  }

  if (!rule.allowNegative && num < 0) {
    return { isValid: false, error: `${rule.label} cannot be negative` };
  }

  if (!rule.allowZero && num === 0) {
    return { isValid: false, error: `${rule.label} cannot be zero` };
  }

  if (rule.min !== undefined && num < rule.min) {
    return { isValid: false, error: `${rule.label} must be ≥ ${rule.min}` };
  }

  if (rule.max !== undefined && num > rule.max) {
    return { isValid: false, error: `${rule.label} must be ≤ ${rule.max}` };
  }

  return { isValid: true, error: null };
}

/** Returns CSS class for input based on validation state */
function validationClass(isValid: boolean | null): string {
  if (isValid === null) return 'bg-slate-900 border-slate-600 text-slate-100';
  if (isValid) return 'bg-slate-900 border-slate-600 text-slate-100';
  return 'bg-slate-900 border-red-500 text-slate-100 ring-1 ring-red-500/30';
}

// ============================================================================
// Validation Rules (domain-specific for fire alarm engineering)
// ============================================================================

const VOLTAGE_RULE: ValidationRule = { min: 0, max: 1000, label: 'Voltage' };
const CURRENT_RULE: ValidationRule = { min: 0, max: 100, allowZero: true, label: 'Current' };
const DISTANCE_RULE: ValidationRule = { min: 0, max: 1000, label: 'Distance' };
const CABLE_LENGTH_RULE: ValidationRule = { min: 0, max: 5000, label: 'Cable Length' };
const CROSS_SECTION_RULE: ValidationRule = { min: 0, max: 1000, label: 'Cross Section' };
const POWER_FACTOR_RULE: ValidationRule = { min: 0, max: 1, label: 'Power Factor' };
const TEMPERATURE_RULE: ValidationRule = { min: -40, max: 200, label: 'Temperature' };
const BREAKER_RATING_RULE: ValidationRule = { min: 0, max: 100, label: 'Breaker Rating' };
const LOAD_CURRENT_RULE: ValidationRule = { min: 0, max: 100, label: 'Load Current' };
const POWER_RULE: ValidationRule = { min: 0, max: 10000, label: 'Power' };

// ============================================================================
// ValidatedInput - Input field with validation feedback
// ============================================================================

function ValidatedInput({
  value,
  onChange,
  rule,
  type = 'number',
  step,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  rule: ValidationRule;
  type?: string;
  step?: string;
  placeholder?: string;
}) {
  const validation = validateNumeric(value, rule);
  const isInvalid = !validation.isValid && value !== '';
  const errorId = `error-${rule.label.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <div className="space-y-1">
      <Input
        type={type}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={validationClass(value === '' ? null : validation.isValid)}
        placeholder={placeholder}
        aria-invalid={isInvalid || undefined}
        aria-describedby={isInvalid ? errorId : undefined}
        aria-label={rule.label}
      />
      {isInvalid && (
        <p id={errorId} className="text-[11px] text-red-400 leading-tight" role="alert">{validation.error}</p>
      )}
    </div>
  );
}

// ============================================================================
// EngineeringPage Component
// ============================================================================

export function EngineeringPage() {
  const { t } = useTranslation();
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

  // ============================================================================
  // Validation state (computed)
  // ============================================================================

  const vdValid = useMemo(() => {
    const v = [
      validateNumeric(vdCurrent, CURRENT_RULE),
      validateNumeric(vdLength, CABLE_LENGTH_RULE),
      validateNumeric(vdCrossSection, CROSS_SECTION_RULE),
      validateNumeric(vdPowerFactor, POWER_FACTOR_RULE),
      validateNumeric(vdVoltage, VOLTAGE_RULE),
    ];
    return v.every(r => r.isValid);
  }, [vdCurrent, vdLength, vdCrossSection, vdPowerFactor, vdVoltage]);

  const scValid = useMemo(() => {
    const v = [
      validateNumeric(scVoltage, VOLTAGE_RULE),
      validateNumeric(scLength, CABLE_LENGTH_RULE),
      validateNumeric(scCrossSection, CROSS_SECTION_RULE),
      validateNumeric(scBreakerRating, BREAKER_RATING_RULE),
    ];
    return v.every(r => r.isValid);
  }, [scVoltage, scLength, scCrossSection, scBreakerRating]);

  const csValid = useMemo(() => {
    const v = [
      validateNumeric(csLoadCurrent, LOAD_CURRENT_RULE),
      validateNumeric(csAmbientTemp, TEMPERATURE_RULE),
    ];
    return v.every(r => r.isValid);
  }, [csLoadCurrent, csAmbientTemp]);

  const lfValid = useMemo(() => {
    const v = [
      validateNumeric(lfPower, POWER_RULE),
      validateNumeric(lfVoltage, VOLTAGE_RULE),
      validateNumeric(lfPowerFactor, POWER_FACTOR_RULE),
    ];
    return v.every(r => r.isValid);
  }, [lfPower, lfVoltage, lfPowerFactor]);

  const reportValid = useMemo(() => {
    return vdValid && csValid && scValid;
  }, [vdValid, csValid, scValid]);

  // ============================================================================
  // Calculation handlers (with validation gates)
  // ============================================================================

  const handleVoltageDrop = () => {
    if (!vdValid) return;
    const result = calculateVoltageDrop(
      parseFloat(vdCurrent),
      parseFloat(vdLength),
      vdMaterial,
      parseFloat(vdCrossSection),
      parseFloat(vdPowerFactor),
      parseFloat(vdVoltage),
    );
    if (result && !isNaN(result.percentage)) {
      setVdResult(result);
    }
  };

  const handleShortCircuit = () => {
    if (!scValid) return;
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
    if (!csValid) return;
    const result = calculateCableSizing(
      parseFloat(csLoadCurrent),
      csMaterial,
      csInstallMethod,
      parseFloat(csAmbientTemp),
    );
    setCsResult(result);
  };

  const handleLoadFlow = () => {
    if (!lfValid) return;
    const result = calculateLoadFlow(
      parseFloat(lfPower),
      parseFloat(lfVoltage),
      parseFloat(lfPowerFactor),
    );
    setLfResult(result);
  };

  const handleCompleteReport = () => {
    if (!reportValid) return;
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
    <div className="flex-1 overflow-auto" aria-label={t('engineering.title')}>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">{t('engineering.title')}</h1>
            <p className="text-sm text-slate-400 mt-1">{t('engineering.subtitle')}</p>
          </div>
          <Button
            className="bg-red-600 hover:bg-red-700 text-white border-none"
            onClick={handleCompleteReport}
            disabled={!reportValid}
          >
            <FileText className="h-4 w-4 mr-1" />
            {t('engineering.generateReport')}
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
                  title={t('engineering.voltageDrop')}
                  status={report.voltageDrop.status}
                  value={`${report.voltageDrop.percentage}%`}
                  detail={`Limit: ${report.voltageDrop.limit}%`}
                />
                <ReportItem
                  title={t('engineering.shortCircuit')}
                  status={report.shortCircuit.status}
                  value={`${report.shortCircuit.prospectiveCurrent} kA`}
                  detail={`Breaker: ${report.shortCircuit.breakerRating} kA`}
                />
                <ReportItem
                  title={t('engineering.cableSizing')}
                  status={report.cableSizing.suitable ? 'PASS' : 'FAIL'}
                  value={`${report.cableSizing.recommendedCrossSection} mm²`}
                  detail={`Ampacity: ${report.cableSizing.finalAmpacity}A`}
                />
                <ReportItem
                  title={t('engineering.loadFlow')}
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
                      <ValidatedInput value={vdCurrent} onChange={setVdCurrent} rule={CURRENT_RULE} />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Length (m)</Label>
                      <ValidatedInput value={vdLength} onChange={setVdLength} rule={CABLE_LENGTH_RULE} />
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
                      <ValidatedInput value={vdCrossSection} onChange={setVdCrossSection} rule={CROSS_SECTION_RULE} />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Power Factor</Label>
                      <ValidatedInput value={vdPowerFactor} onChange={setVdPowerFactor} rule={POWER_FACTOR_RULE} step="0.01" />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Voltage (V)</Label>
                      <ValidatedInput value={vdVoltage} onChange={setVdVoltage} rule={VOLTAGE_RULE} />
                    </div>
                  </div>
                  <Button className="w-full bg-red-600 hover:bg-red-700 text-white border-none" onClick={handleVoltageDrop} disabled={!vdValid}>
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
                      <ValidatedInput value={scVoltage} onChange={setScVoltage} rule={VOLTAGE_RULE} />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Cable Length (m)</Label>
                      <ValidatedInput value={scLength} onChange={setScLength} rule={CABLE_LENGTH_RULE} />
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
                      <ValidatedInput value={scCrossSection} onChange={setScCrossSection} rule={CROSS_SECTION_RULE} />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Breaker Rating (kA)</Label>
                      <ValidatedInput value={scBreakerRating} onChange={setScBreakerRating} rule={BREAKER_RATING_RULE} />
                    </div>
                  </div>
                  <Button className="w-full bg-red-600 hover:bg-red-700 text-white border-none" onClick={handleShortCircuit} disabled={!scValid}>
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
                      <ValidatedInput value={csLoadCurrent} onChange={setCsLoadCurrent} rule={LOAD_CURRENT_RULE} />
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
                      <ValidatedInput value={csAmbientTemp} onChange={setCsAmbientTemp} rule={TEMPERATURE_RULE} />
                    </div>
                  </div>
                  <Button className="w-full bg-red-600 hover:bg-red-700 text-white border-none" onClick={handleCableSizing} disabled={!csValid}>
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
                      <ValidatedInput value={lfPower} onChange={setLfPower} rule={POWER_RULE} />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Voltage (V)</Label>
                      <ValidatedInput value={lfVoltage} onChange={setLfVoltage} rule={VOLTAGE_RULE} />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300 text-xs">Power Factor</Label>
                      <ValidatedInput value={lfPowerFactor} onChange={setLfPowerFactor} rule={POWER_FACTOR_RULE} step="0.01" />
                    </div>
                  </div>
                  <Button className="w-full bg-red-600 hover:bg-red-700 text-white border-none" onClick={handleLoadFlow} disabled={!lfValid}>
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
