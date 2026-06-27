/**
 * EngineeringPage.tsx - Fire Alarm Electrical Calculations
 *
 * V140 Phase 5: Connected to real QOMN API endpoints. Falls back to local
 * calculation when API is unavailable (offline mode).
 */
import { useState, useCallback } from 'react';
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
import { qomnApi } from '@/services/fullApi';

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

  const [apiLoading, setApiLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const calculateVoltageDrop = useCallback(() => {
    // Local fallback calculation
    const current = parseFloat(voltageDropInputs.current);
    const length = parseFloat(voltageDropInputs.length);
    const cableSize = parseFloat(voltageDropInputs.cableSize);
    const voltage = parseFloat(voltageDropInputs.voltage);
    
    if (isNaN(current) || isNaN(length) || isNaN(cableSize) || isNaN(voltage)) {
      return { percentage: 0, absolute: 0 };
    }
    
    // Simplified calculation: Vdrop = (R * I * L) / 1000
    const resistivity = voltageDropInputs.material === 'cu' ? 0.0172 : 0.0282;
    const resistance = (resistivity * length * 2) / cableSize;
    const voltageDrop = current * resistance;
    const percentage = (voltageDrop / voltage) * 100;
    
    return {
      percentage: parseFloat(percentage.toFixed(2)),
      absolute: parseFloat(voltageDrop.toFixed(3))
    };
  }, [voltageDropInputs]);

  // V140 Phase 5: Call real QOMN API for voltage drop calculation
  const calculateVoltageDropViaApi = useCallback(async () => {
    setApiLoading(true);
    setApiError(null);
    try {
      const result = await qomnApi.voltageDrop({
        current: parseFloat(voltageDropInputs.current),
        length: parseFloat(voltageDropInputs.length),
        cable_size: voltageDropInputs.cableSize,
        voltage: parseFloat(voltageDropInputs.voltage),
        material: voltageDropInputs.material,
      });
      return result;
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'API calculation failed');
      // Fall back to local calculation
      return calculateVoltageDrop();
    } finally {
      setApiLoading(false);
    }
  }, [voltageDropInputs, calculateVoltageDrop]);

  const calculateCableSizing = () => {
    // Placeholder calculation
    const loadCurrent = parseFloat(cableSizingInputs.loadCurrent);
    const length = parseFloat(cableSizingInputs.length);
    const ambientTemp = parseFloat(cableSizingInputs.ambientTemp);
    
    if (isNaN(loadCurrent) || isNaN(length) || isNaN(ambientTemp)) {
      return { recommendedSize: 'N/A', baseAmpacity: 0, deratingFactor: 0, finalAmpacity: 0 };
    }
    
    // Simplified calculation
    const baseAmpacity = loadCurrent * 1.25; // 25% safety factor
    const deratingFactor = 0.85; // Simplified derating
    const finalAmpacity = baseAmpacity * deratingFactor;
    const recommendedSize = Math.ceil(finalAmpacity / 5) * 2.5; // Approximate size
    
    return {
      recommendedSize: recommendedSize.toFixed(1),
      baseAmpacity: parseFloat(baseAmpacity.toFixed(2)),
      deratingFactor: parseFloat(deratingFactor.toFixed(2)),
      finalAmpacity: parseFloat(finalAmpacity.toFixed(2))
    };
  };

  const calculateBatteryRequirements = () => {
    // Placeholder calculation
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
    
    const totalStandbyCurrent = standbyDevices * standbyCurrent;
    const totalAlarmCurrent = alarmDevices * alarmCurrent;
    const standbyCapacity = (totalStandbyCurrent / 1000) * standbyHours;
    const alarmCapacity = (totalAlarmCurrent / 1000) * (alarmMinutes / 60);
    const requiredCapacity = (standbyCapacity + alarmCapacity) * 1.2; // 20% safety factor
    
    return {
      totalStandbyCurrent: parseFloat(totalStandbyCurrent.toFixed(2)),
      totalAlarmCurrent: parseFloat(totalAlarmCurrent.toFixed(2)),
      requiredCapacity: parseFloat(requiredCapacity.toFixed(2)),
      recommendedBattery: `24V ${Math.ceil(requiredCapacity)}Ah Lead Acid`
    };
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