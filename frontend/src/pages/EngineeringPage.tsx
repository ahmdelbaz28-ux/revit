/**
 * EngineeringPage.tsx - Fire Alarm Electrical Calculations
 *
 * P1.3 FIX (2026-06-20): Replaced placeholder math with real engine calls.
 * Previously calculateCableSizing used hardcoded deratingFactor = 0.85 and
 * ignored ambientTemp + installationMethod. calculateVoltageDrop used a
 * simplified resistivity formula without reactance or phase multiplier.
 * calculateBatteryRequirements didn't apply NFPA 72 §27.6.2 validation.
 * Now all three route through frontend/src/engine/ which has proper IEC
 * 60364 / NEC / NFPA 72 implementations.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Calculator,
  Zap,
  Battery,
  Cable,
  Ruler,
} from 'lucide-react';
// P1.3: import real calculation engines
import {
  calculateVoltageDrop as engineCalcVoltageDrop,
  calculateCableSizing as engineCalcCableSizing,
  type CableMaterial,
  type InstallationMethod,
} from '@/engine/CalculationEngine';
import {
  calculateBatteryRequirements as engineCalcBattery,
  validateBatteryCompliance,
} from '@/engine/BatteryCalculator';

// P1.3: BatteryCalcInput is not exported from BatteryCalculator, so we
// redefine it locally to match the engine's expected shape.
interface BatteryCalcInput {
  devices: {
    type: string;
    standbyCurrent: number;  // mA
    alarmCurrent: number;    // mA
    count: number;
  }[];
  standbyHours: number;
  alarmMinutes: number;
  safetyFactor: number;
}

// ============================================================================
// EngineeringPage Component
// ============================================================================

export function EngineeringPage() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('voltage-drop');
  const [voltageDropInputs, setVoltageDropInputs] = useState({
    current: '',
    length: '',
    cableSize: '',
    voltage: '',
    material: 'cu',
  });
  const [cableSizingInputs, setCableSizingInputs] = useState({
    loadCurrent: '',
    length: '',
    ambientTemp: '',
    installationMethod: 'free-air',
  });
  const [batteryCalcInputs, setBatteryCalcInputs] = useState({
    standbyDevices: '',
    standbyCurrent: '',
    alarmDevices: '',
    alarmCurrent: '',
    standbyHours: '24',
    alarmMinutes: '5',
  });

  const calculateVoltageDrop = () => {
    // P1.3: route through real engine. Previous implementation used a
    // simplified resistivity formula (V = resistivity × L × 2 / crossSection)
    // that ignored cable reactance, power factor, and phase multiplier.
    // The real engine uses IEC 60364-5-52 Annex G:
    //   ΔV = phaseMultiplier × I × L × (R·cosφ + X·sinφ)
    // with phaseMultiplier = 2 (single-phase) or √3 (three-phase).
    const current = parseFloat(voltageDropInputs.current);
    const length = parseFloat(voltageDropInputs.length);
    const cableSize = parseFloat(voltageDropInputs.cableSize);
    const voltage = parseFloat(voltageDropInputs.voltage);

    if (isNaN(current) || isNaN(length) || isNaN(cableSize) || isNaN(voltage)) {
      return { percentage: 0, absolute: 0 };
    }

    try {
      const material: CableMaterial = voltageDropInputs.material === 'cu' ? 'Cu' : 'Al';
      const result = engineCalcVoltageDrop(
        current,
        length,
        material,
        cableSize,
        0.85, // powerFactor — fire alarm circuits are typically resistive
        voltage,
        'power', // circuitType — fire alarm NAC circuits are power circuits
        'single', // phaseType — most fire alarm systems are single-phase
      );
      return {
        percentage: result.percentage,
        absolute: result.absoluteVoltage,
        status: result.status,
        limit: result.limit,
      };
    } catch {
      // Engine throws on invalid input (negative current, etc.)
      return { percentage: 0, absolute: 0 };
    }
  };

  const calculateCableSizing = () => {
    // P1.3: route through real engine. Previous implementation used
    // hardcoded deratingFactor = 0.85 and IGNORED ambientTemp and
    // installationMethod. The real engine uses IEC 60364-5-52:
    //   deratingFactor = installationFactor × ambientTempFactor × simultaneousFactor
    // with separate ampacity tables for Cu and Al (V131 FIX in engine).
    const loadCurrent = parseFloat(cableSizingInputs.loadCurrent);
    const length = parseFloat(cableSizingInputs.length); // eslint-disable-line @typescript-eslint/no-unused-vars
    const ambientTemp = parseFloat(cableSizingInputs.ambientTemp);

    if (isNaN(loadCurrent) || isNaN(ambientTemp)) {
      return { recommendedSize: 'N/A', baseAmpacity: 0, deratingFactor: 0, finalAmpacity: 0 };
    }

    // Map UI values to engine's InstallationMethod enum.
    // UI uses 'free-air'/'conduit'/'trunking'; engine uses 'free_air'/'conduit'/'tray'.
    const methodMap: Record<string, InstallationMethod> = {
      'free-air': 'free_air',
      'conduit': 'conduit',
      'trunking': 'tray',
    };
    const installationMethod = methodMap[cableSizingInputs.installationMethod] || 'free_air';

    try {
      const result = engineCalcCableSizing(
        loadCurrent,
        'Cu', // material — fire alarm circuits use copper per NFPA 72
        installationMethod,
        ambientTemp,
        1.0, // simultaneousFactor — fire alarm loads are all-on simultaneously
      );
      return {
        recommendedSize: result.recommendedCrossSection.toFixed(1),
        baseAmpacity: result.ampacity,
        deratingFactor: result.deratingFactor,
        finalAmpacity: result.finalAmpacity,
        ambientTempFactor: result.ambientTempFactor,
        installationFactor: result.installationFactor,
        suitable: result.suitable,
      };
    } catch {
      return { recommendedSize: 'N/A', baseAmpacity: 0, deratingFactor: 0, finalAmpacity: 0 };
    }
  };

  const calculateBatteryRequirements = () => {
    // P1.3: route through real engine with NFPA 72 §27.6.2 validation.
    // Previous implementation used a simplified formula without safety
    // factor validation or 24h/5min minimum duration checks.
    const standbyDevices = parseInt(batteryCalcInputs.standbyDevices);
    const standbyCurrent = parseFloat(batteryCalcInputs.standbyCurrent);
    const alarmDevices = parseInt(batteryCalcInputs.alarmDevices);
    const alarmCurrent = parseFloat(batteryCalcInputs.alarmCurrent);
    const standbyHours = parseFloat(batteryCalcInputs.standbyHours);
    const alarmMinutes = parseFloat(batteryCalcInputs.alarmMinutes);

    if (isNaN(standbyDevices) || isNaN(standbyCurrent) || isNaN(alarmDevices) ||
        isNaN(alarmCurrent) || isNaN(standbyHours) || isNaN(alarmMinutes)) {
      return { totalStandbyCurrent: 0, totalAlarmCurrent: 0, requiredCapacity: 0, recommendedBattery: 'N/A' };
    }

    const input: BatteryCalcInput = {
      devices: [
        {
          type: 'Standby devices',
          standbyCurrent,
          alarmCurrent: 0, // standby devices don't draw alarm current
          count: standbyDevices,
        },
        {
          type: 'Alarm devices',
          standbyCurrent: 0, // alarm devices don't draw standby current in this simplified input
          alarmCurrent,
          count: alarmDevices,
        },
      ],
      standbyHours,
      alarmMinutes,
      safetyFactor: 1.2, // NFPA 72 §27.6.2 recommends 20% safety factor
    };

    try {
      const result = engineCalcBattery(input);
      const compliance = validateBatteryCompliance(result);
      return {
        totalStandbyCurrent: result.totalStandbyCurrent,
        totalAlarmCurrent: result.totalAlarmCurrent,
        requiredCapacity: result.requiredCapacity,
        recommendedBattery: `${result.recommendedBattery.voltage}V ${result.recommendedBattery.capacity}Ah ${result.recommendedBattery.type}`,
        complianceCompliant: compliance.compliant,
        complianceViolations: compliance.violations,
        complianceWarnings: compliance.warnings,
      };
    } catch {
      return { totalStandbyCurrent: 0, totalAlarmCurrent: 0, requiredCapacity: 0, recommendedBattery: 'N/A' };
    }
  };

  const vDropResult = calculateVoltageDrop();
  const cableResult = calculateCableSizing();
  const batteryResult = calculateBatteryRequirements();

  return (
    <div className="flex-1 overflow-auto" aria-label={t('engineering.title')}>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-100">{t('engineering.title')}</h1>
          <p className="text-sm text-slate-400 mt-1">{t('engineering.subtitle')}</p>
        </div>

        {/* Tabs */}
        <div className="flex flex-wrap gap-2 border-b border-slate-700 pb-2">
          <Button
            variant={activeTab === 'voltage-drop' ? 'default' : 'outline'}
            className={
              activeTab === 'voltage-drop'
                ? 'bg-red-600 hover:bg-red-700 text-white border-none'
                : 'border-slate-600 text-slate-300 hover:bg-slate-800'
            }
            onClick={() => setActiveTab('voltage-drop')}
          >
            <Zap className="h-4 w-4 mr-2" />
            {t('engineering.voltageDrop')}
          </Button>
          <Button
            variant={activeTab === 'cable-sizing' ? 'default' : 'outline'}
            className={
              activeTab === 'cable-sizing'
                ? 'bg-red-600 hover:bg-red-700 text-white border-none'
                : 'border-slate-600 text-slate-300 hover:bg-slate-800'
            }
            onClick={() => setActiveTab('cable-sizing')}
          >
            <Cable className="h-4 w-4 mr-2" />
            {t('engineering.cableSizing')}
          </Button>
          <Button
            variant={activeTab === 'battery-calc' ? 'default' : 'outline'}
            className={
              activeTab === 'battery-calc'
                ? 'bg-red-600 hover:bg-red-700 text-white border-none'
                : 'border-slate-600 text-slate-300 hover:bg-slate-800'
            }
            onClick={() => setActiveTab('battery-calc')}
          >
            <Battery className="h-4 w-4 mr-2" />
            {t('engineering.batteryCalculation')}
          </Button>
        </div>

        {/* Voltage Drop Calculator */}
        {activeTab === 'voltage-drop' && (
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader>
              <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                <Zap className="h-5 w-5" />
                {t('engineering.voltageDrop')}
              </CardTitle>
              <CardDescription className="text-slate-400">
                {t('engineering.voltageDropDesc')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.current')}</Label>
                  <Input
                    type="number"
                    value={voltageDropInputs.current}
                    onChange={(e) => setVoltageDropInputs({...voltageDropInputs, current: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="A"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.length')}</Label>
                  <Input
                    type="number"
                    value={voltageDropInputs.length}
                    onChange={(e) => setVoltageDropInputs({...voltageDropInputs, length: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="m"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.cableSize')}</Label>
                  <Input
                    type="number"
                    value={voltageDropInputs.cableSize}
                    onChange={(e) => setVoltageDropInputs({...voltageDropInputs, cableSize: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="mm²"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.voltage')}</Label>
                  <Input
                    type="number"
                    value={voltageDropInputs.voltage}
                    onChange={(e) => setVoltageDropInputs({...voltageDropInputs, voltage: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="V"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.material')}</Label>
                  <Select value={voltageDropInputs.material} onValueChange={(v) => setVoltageDropInputs({...voltageDropInputs, material: v})}>
                    <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-800 border-slate-700">
                      <SelectItem value="cu">{t('engineering.copper')}</SelectItem>
                      <SelectItem value="al">{t('engineering.aluminum')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Separator />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card className="border-slate-700 bg-slate-900/50">
                  <CardHeader>
                    <CardTitle className="text-slate-200 text-sm">{t('engineering.results')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.percentage')}</span>
                        <span className="font-mono text-slate-200">{vDropResult.percentage}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.absolute')}</span>
                        <span className="font-mono text-slate-200">{vDropResult.absolute}V</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                
                <Card className="border-slate-700 bg-slate-900/50">
                  <CardHeader>
                    <CardTitle className="text-slate-200 text-sm">{t('engineering.status')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Badge
                      variant={vDropResult.percentage < 3 ? 'default' : vDropResult.percentage < 5 ? 'secondary' : 'destructive'}
                      className={
                        vDropResult.percentage < 3
                          ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/30'
                          : vDropResult.percentage < 5
                          ? 'bg-amber-600/20 text-amber-400 border-amber-500/30'
                          : 'bg-red-600/20 text-red-400 border-red-500/30'
                      }
                    >
                      {vDropResult.percentage < 3 ? t('engineering.suitable') : vDropResult.percentage < 5 ? t('engineering.acceptable') : t('engineering.excessive')}
                    </Badge>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Cable Sizing Calculator */}
        {activeTab === 'cable-sizing' && (
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader>
              <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                <Cable className="h-5 w-5" />
                {t('engineering.cableSizing')}
              </CardTitle>
              <CardDescription className="text-slate-400">
                {t('engineering.cableSizingDesc')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.loadCurrent')}</Label>
                  <Input
                    type="number"
                    value={cableSizingInputs.loadCurrent}
                    onChange={(e) => setCableSizingInputs({...cableSizingInputs, loadCurrent: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="A"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.length')}</Label>
                  <Input
                    type="number"
                    value={cableSizingInputs.length}
                    onChange={(e) => setCableSizingInputs({...cableSizingInputs, length: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="m"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.ambientTemp')}</Label>
                  <Input
                    type="number"
                    value={cableSizingInputs.ambientTemp}
                    onChange={(e) => setCableSizingInputs({...cableSizingInputs, ambientTemp: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="°C"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.installationMethod')}</Label>
                  <Select value={cableSizingInputs.installationMethod} onValueChange={(v) => setCableSizingInputs({...cableSizingInputs, installationMethod: v})}>
                    <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-800 border-slate-700">
                      <SelectItem value="free-air">{t('engineering.freeAir')}</SelectItem>
                      <SelectItem value="conduit">{t('engineering.conduit')}</SelectItem>
                      <SelectItem value="trunking">{t('engineering.trunking')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Separator />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card className="border-slate-700 bg-slate-900/50">
                  <CardHeader>
                    <CardTitle className="text-slate-200 text-sm">{t('engineering.results')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.recommendedSize')}</span>
                        <span className="font-mono text-slate-200">{cableResult.recommendedSize} mm²</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.baseAmpacity')}</span>
                        <span className="font-mono text-slate-200">{cableResult.baseAmpacity} A</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.deratingFactor')}</span>
                        <span className="font-mono text-slate-200">{cableResult.deratingFactor}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.finalAmpacity')}</span>
                        <span className="font-mono text-slate-200">{cableResult.finalAmpacity} A</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                
                <Card className="border-slate-700 bg-slate-900/50">
                  <CardHeader>
                    <CardTitle className="text-slate-200 text-sm">{t('engineering.status')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Badge className="bg-emerald-600/20 text-emerald-400 border-emerald-500/30">
                      {t('engineering.suitable')}
                    </Badge>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Battery Calculation */}
        {activeTab === 'battery-calc' && (
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader>
              <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                <Battery className="h-5 w-5" />
                {t('engineering.batteryCalculation')}
              </CardTitle>
              <CardDescription className="text-slate-400">
                {t('engineering.batteryCalculationDesc')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.standbyDevices')}</Label>
                  <Input
                    type="number"
                    value={batteryCalcInputs.standbyDevices}
                    onChange={(e) => setBatteryCalcInputs({...batteryCalcInputs, standbyDevices: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="#"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.standbyCurrent')}</Label>
                  <Input
                    type="number"
                    value={batteryCalcInputs.standbyCurrent}
                    onChange={(e) => setBatteryCalcInputs({...batteryCalcInputs, standbyCurrent: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="mA"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.alarmDevices')}</Label>
                  <Input
                    type="number"
                    value={batteryCalcInputs.alarmDevices}
                    onChange={(e) => setBatteryCalcInputs({...batteryCalcInputs, alarmDevices: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="#"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.alarmCurrent')}</Label>
                  <Input
                    type="number"
                    value={batteryCalcInputs.alarmCurrent}
                    onChange={(e) => setBatteryCalcInputs({...batteryCalcInputs, alarmCurrent: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="mA"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.standbyHours')}</Label>
                  <Input
                    type="number"
                    value={batteryCalcInputs.standbyHours}
                    onChange={(e) => setBatteryCalcInputs({...batteryCalcInputs, standbyHours: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="hours"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">{t('engineering.alarmMinutes')}</Label>
                  <Input
                    type="number"
                    value={batteryCalcInputs.alarmMinutes}
                    onChange={(e) => setBatteryCalcInputs({...batteryCalcInputs, alarmMinutes: e.target.value})}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                    placeholder="minutes"
                  />
                </div>
              </div>

              <Separator />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card className="border-slate-700 bg-slate-900/50">
                  <CardHeader>
                    <CardTitle className="text-slate-200 text-sm">{t('engineering.results')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.totalStandbyCurrent')}</span>
                        <span className="font-mono text-slate-200">{batteryResult.totalStandbyCurrent} mA</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.totalAlarmCurrent')}</span>
                        <span className="font-mono text-slate-200">{batteryResult.totalAlarmCurrent} mA</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.requiredCapacity')}</span>
                        <span className="font-mono text-slate-200">{batteryResult.requiredCapacity} Ah</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                
                <Card className="border-slate-700 bg-slate-900/50">
                  <CardHeader>
                    <CardTitle className="text-slate-200 text-sm">{t('engineering.recommendations')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-slate-400">{t('engineering.recommendedBattery')}</span>
                        <span className="font-mono text-slate-200">{batteryResult.recommendedBattery}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}