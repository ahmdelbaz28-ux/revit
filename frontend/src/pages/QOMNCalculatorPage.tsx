import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Zap, AlertTriangle, Settings } from "lucide-react";
import PhysicsGuardsMonitor, { GuardRule } from "@/components/engineering/PhysicsGuardsMonitor";
import { cn } from "@/lib/utils";

type CalculatorTab = "smoke" | "heat" | "battery" | "voltage" | "detectors" | "duct";

const SmokeCalculator: React.FC = () => {
  const [roomArea, setRoomArea] = useState(400);
  const [ceilingHeight, setCeilingHeight] = useState(10);
  const [detectorType, setDetectorType] = useState("standard");

  const requiredDetectors = Math.ceil(roomArea / 900);
  const spacing = Math.sqrt(roomArea / requiredDetectors);

  const guards: GuardRule[] = [
    {
      id: "smoke-spacing",
      name: "Smoke Detector Spacing",
      description: "NFPA 72 Table 23.3.6 - Standard spacing 30 ft",
      severity: "error",
      category: "spacing",
      min: 20,
      max: 30,
      currentValue: spacing,
      unit: "ft",
      status: spacing <= 30 && spacing >= 20 ? "pass" : spacing <= 35 ? "warn" : "fail",
    },
    {
      id: "ceiling-height",
      name: "Ceiling Height Compliance",
      description: "Standard detectors: 8-12 ft, High ceiling: 12+ ft",
      severity: "error",
      category: "smoke",
      min: 8,
      max: 50,
      currentValue: ceilingHeight,
      unit: "ft",
      status: ceilingHeight >= 8 ? "pass" : "fail",
    },
    {
      id: "detector-count",
      name: "Detector Count",
      description: `Required: ${requiredDetectors} detectors for ${roomArea} sq ft`,
      severity: "warn",
      category: "smoke",
      status: "pass",
    },
  ];

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          { label: "Room Area (sq ft)", value: roomArea, onChange: setRoomArea },
          { label: "Ceiling Height (ft)", value: ceilingHeight, onChange: setCeilingHeight },
        ].map((field, idx) => (
          <div key={idx} className="space-y-3">
            <label className="block text-sm font-semibold text-slate-200">
              {field.label}
            </label>
            <input
              type="number"
              value={field.value}
              onChange={(e) => field.onChange(Number(e.target.value))}
              className="w-full px-4 py-3 bg-slate-800/50 border border-slate-600/60 rounded-lg text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-cyan-400/20 transition-all"
            />
          </div>
        ))}
        <div className="space-y-3">
          <label className="block text-sm font-semibold text-slate-200">
            Detector Type
          </label>
          <select
            value={detectorType}
            onChange={(e) => setDetectorType(e.target.value)}
            className="w-full px-4 py-3 bg-slate-800/50 border border-slate-600/60 rounded-lg text-slate-100 focus:border-cyan-400 focus:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-cyan-400/20 transition-all"
          >
            <option value="standard">Standard</option>
            <option value="rated">High Ceiling Rated</option>
            <option value="beam">Beam Type</option>
          </select>
        </div>
      </div>

      {/* Results Cards */}
      <div className="grid grid-cols-2 md:grid-cols-2 gap-6">
        <div className="bg-gradient-to-br from-cyan-900/40 to-cyan-900/20 border border-cyan-500/40 rounded-xl p-6 backdrop-blur-sm hover:border-cyan-400/60 transition-all">
          <div className="text-sm font-medium text-cyan-400 mb-2">Required Detectors</div>
          <div className="text-4xl font-bold text-cyan-300">{requiredDetectors}</div>
          <div className="text-xs text-cyan-400/70 mt-3">for {roomArea.toLocaleString()} sq ft</div>
        </div>
        <div className="bg-gradient-to-br from-blue-900/40 to-blue-900/20 border border-blue-500/40 rounded-xl p-6 backdrop-blur-sm hover:border-blue-400/60 transition-all">
          <div className="text-sm font-medium text-blue-400 mb-2">Spacing</div>
          <div className="text-4xl font-bold text-blue-300">{spacing.toFixed(1)}</div>
          <div className="text-xs text-blue-400/70 mt-3">feet between detectors</div>
        </div>
      </div>

      {/* Physics Guards */}
      <PhysicsGuardsMonitor rules={guards} />
    </div>
  );
};

const BatteryCalculator: React.FC = () => {
  const [deviceCount, setDeviceCount] = useState(10);
  const [currentDraw, setCurrentDraw] = useState(2);
  const [standbyHours, setStandbyHours] = useState(24);
  const [alarmMinutes, setAlarmMinutes] = useState(15);

  const standbyCapacity = (standbyHours * deviceCount * currentDraw) / 1000;
  const alarmCapacity = ((alarmMinutes / 60) * deviceCount * currentDraw) / 1000;
  const totalCapacity = standbyCapacity + alarmCapacity;
  const withSafetyMargin = totalCapacity * 1.2;

  const guards: GuardRule[] = [
    {
      id: "battery-margin",
      name: "Safety Margin (20%)",
      description: "Required: 20% safety factor for battery capacity",
      severity: "error",
      category: "battery",
      min: 1.0,
      max: 1.5,
      currentValue: 1.2,
      unit: "x",
      status: "pass",
    },
    {
      id: "battery-capacity",
      name: "Total Battery Capacity",
      description: `Required: ${withSafetyMargin.toFixed(2)} Ah (with 20% margin)`,
      severity: "error",
      category: "battery",
      status: "pass",
    },
    {
      id: "alarm-duration",
      name: "Alarm Duration",
      description: `Min: 5 minutes, Current: ${alarmMinutes} minutes`,
      severity: "warn",
      category: "battery",
      min: 5,
      max: 60,
      currentValue: alarmMinutes,
      unit: "min",
      status: alarmMinutes >= 5 ? "pass" : "fail",
    },
  ];

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {[
          { label: "Device Count", value: deviceCount, onChange: setDeviceCount },
          { label: "Current Draw (mA)", value: currentDraw, onChange: setCurrentDraw },
          { label: "Standby Hours", value: standbyHours, onChange: setStandbyHours },
          { label: "Alarm Minutes", value: alarmMinutes, onChange: setAlarmMinutes },
        ].map((field, idx) => (
          <div key={idx} className="space-y-3">
            <label className="block text-sm font-semibold text-slate-200">
              {field.label}
            </label>
            <input
              type="number"
              value={field.value}
              onChange={(e) => field.onChange(Number(e.target.value))}
              className="w-full px-4 py-3 bg-slate-800/50 border border-slate-600/60 rounded-lg text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-cyan-400/20 transition-all"
            />
          </div>
        ))}
      </div>

      {/* Results Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gradient-to-br from-emerald-900/40 to-emerald-900/20 border border-emerald-500/40 rounded-xl p-6 backdrop-blur-sm hover:border-emerald-400/60 transition-all">
          <div className="text-sm font-medium text-emerald-400 mb-2">Standby Capacity</div>
          <div className="text-3xl font-bold text-emerald-300">{standbyCapacity.toFixed(2)}</div>
          <div className="text-xs text-emerald-400/70 mt-3">Ah</div>
        </div>
        <div className="bg-gradient-to-br from-yellow-900/40 to-yellow-900/20 border border-yellow-500/40 rounded-xl p-6 backdrop-blur-sm hover:border-yellow-400/60 transition-all">
          <div className="text-sm font-medium text-yellow-400 mb-2">Alarm Capacity</div>
          <div className="text-3xl font-bold text-yellow-300">{alarmCapacity.toFixed(2)}</div>
          <div className="text-xs text-yellow-400/70 mt-3">Ah</div>
        </div>
        <div className="bg-gradient-to-br from-orange-900/40 to-orange-900/20 border border-orange-500/40 rounded-xl p-6 backdrop-blur-sm hover:border-orange-400/60 transition-all">
          <div className="text-sm font-medium text-orange-400 mb-2">With Safety Margin</div>
          <div className="text-3xl font-bold text-orange-300">{withSafetyMargin.toFixed(2)}</div>
          <div className="text-xs text-orange-400/70 mt-3">Ah (20% margin)</div>
        </div>
      </div>

      {/* Physics Guards */}
      <PhysicsGuardsMonitor rules={guards} />
    </div>
  );
};

const VoltageDropCalculator: React.FC = () => {
  const [wireLength, setWireLength] = useState(100);
  const [wireGauge, setWireGauge] = useState(14);
  const [current, setCurrent] = useState(10);

  // Voltage drop formula: V = (2 * R * L * I) / 1000
  // Simplified for copper wire
  const resistancePerFoot = { 14: 0.0025, 12: 0.00156, 10: 0.001, 8: 0.000625 }[wireGauge as number] || 0.0025;
  const voltageDrop = (2 * resistancePerFoot * wireLength * current) / 1000;
  const percentDrop = (voltageDrop / 12) * 100;

  const guards: GuardRule[] = [
    {
      id: "voltage-drop",
      name: "Voltage Drop (5% max)",
      description: "NFPA 72: Max 5% voltage drop allowed",
      severity: "error",
      category: "voltage",
      min: 0,
      max: 5,
      currentValue: percentDrop,
      unit: "%",
      status: percentDrop <= 5 ? "pass" : percentDrop <= 7 ? "warn" : "fail",
    },
  ];

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          { label: "Wire Length (ft)", value: wireLength, onChange: setWireLength },
          { label: "Wire Gauge (AWG)", value: wireGauge, onChange: setWireGauge },
          { label: "Current (A)", value: current, onChange: setCurrent },
        ].map((field, idx) => (
          <div key={idx} className="space-y-3">
            <label className="block text-sm font-semibold text-slate-200">
              {field.label}
            </label>
            <input
              type="number"
              value={field.value}
              onChange={(e) => field.onChange(Number(e.target.value))}
              className="w-full px-4 py-3 bg-slate-800/50 border border-slate-600/60 rounded-lg text-slate-100 placeholder-slate-500 focus:border-cyan-400 focus:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-cyan-400/20 transition-all"
            />
          </div>
        ))}
      </div>

      {/* Results Cards */}
      <div className="grid grid-cols-2 md:grid-cols-2 gap-6">
        <div className="bg-gradient-to-br from-purple-900/40 to-purple-900/20 border border-purple-500/40 rounded-xl p-6 backdrop-blur-sm hover:border-purple-400/60 transition-all">
          <div className="text-sm font-medium text-purple-400 mb-2">Voltage Drop</div>
          <div className="text-4xl font-bold text-purple-300">{voltageDrop.toFixed(2)}</div>
          <div className="text-xs text-purple-400/70 mt-3">volts</div>
        </div>
        <div className={`bg-gradient-to-br ${percentDrop <= 5 ? 'from-green-900/40 to-green-900/20' : 'from-orange-900/40 to-orange-900/20'} border ${percentDrop <= 5 ? 'border-green-500/40' : 'border-orange-500/40'} rounded-xl p-6 backdrop-blur-sm ${percentDrop <= 5 ? 'hover:border-green-400/60' : 'hover:border-orange-400/60'} transition-all`}>
          <div className={`text-sm font-medium ${percentDrop <= 5 ? 'text-green-400' : 'text-orange-400'} mb-2`}>% Drop</div>
          <div className={`text-4xl font-bold ${percentDrop <= 5 ? 'text-green-300' : 'text-orange-300'}`}>{percentDrop.toFixed(1)}</div>
          <div className={`text-xs ${percentDrop <= 5 ? 'text-green-400/70' : 'text-orange-400/70'} mt-3`}>{percentDrop <= 5 ? 'Within limits' : 'Warning: Exceeds limits'}</div>
        </div>
      </div>

      {/* Physics Guards */}
      <PhysicsGuardsMonitor rules={guards} />
    </div>
  );
};

export const QOMNCalculatorPage: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<CalculatorTab>("smoke");

  const tabs: { id: CalculatorTab; label: string; icon: React.ElementType }[] = [
    { id: "smoke", label: "Smoke Spacing", icon: AlertTriangle },
    { id: "heat", label: "Heat Spacing", icon: Zap },
    { id: "battery", label: "Battery", icon: Zap },
    { id: "voltage", label: "Voltage Drop", icon: Settings },
    { id: "detectors", label: "Detectors", icon: AlertTriangle },
    { id: "duct", label: "Duct Sizing", icon: Settings },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 to-slate-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">QOMN Calculator</h1>
          <p className="text-slate-400 text-lg">Engineering calculations for NFPA 72 compliance</p>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-8 overflow-x-auto pb-2 scrollbar-hide">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-2 px-6 py-3 rounded-lg font-medium text-sm transition-all whitespace-nowrap",
                  activeTab === tab.id
                    ? "bg-gradient-to-r from-cyan-500 to-blue-500 text-white shadow-lg shadow-cyan-500/20"
                    : "bg-slate-800/50 text-slate-300 hover:bg-slate-700/50 border border-slate-700/50"
                )}
              >
                <Icon size={18} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="bg-slate-800/30 border border-slate-700/50 rounded-xl p-8 backdrop-blur-sm">
          {activeTab === "smoke" && <SmokeCalculator />}
          {activeTab === "battery" && <BatteryCalculator />}
          {activeTab === "voltage" && <VoltageDropCalculator />}
          {activeTab === "heat" && <div className="text-slate-400 py-12 text-center">Heat Detector Calculator (Coming Soon)</div>}
          {activeTab === "detectors" && <div className="text-slate-400 py-12 text-center">Detector Placement Tool (Coming Soon)</div>}
          {activeTab === "duct" && <div className="text-slate-400 py-12 text-center">Duct Detector Sizing (Coming Soon)</div>}
        </div>
      </div>
    </div>
  );
};

export default QOMNCalculatorPage;
