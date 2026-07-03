/**
 * ReportsPage.tsx - Report generation with deterministic analysis
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  FileText,
  Download,
  Calendar,
  Clock,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Loader2,
  Eye,
  Calculator,
} from 'lucide-react';
import { useReports, useGenerateReport, useProjects } from '@/hooks/useApi';
import { calculateBatteryRequirements, generateBatteryReport } from '@/engine/BatteryCalculator';
import { calculateCoverage, generateCoverageReport } from '@/engine/CoverageEngine';

// ============================================================================
// ReportsPage Component
// ============================================================================

export function ReportsPage() {
  const { t } = useTranslation();
  // FIX (Rule 17 — root cause): Previously used hardcoded 'default-project-id' which always 404'd.
  // Now we fetch the list of projects and let the user pick one. If the list is empty, we
  // display a clear empty-state instead of silently calling a broken URL.
  const { data: projects, loading: projectsLoading } = useProjects();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  // Auto-select the first project when the list arrives
  useEffect(() => {
    if (!selectedProjectId && projects && projects.length > 0) {
      setSelectedProjectId(projects[0].project_id || projects[0].id);
    }
  }, [projects, selectedProjectId]);

  const { data: reports, loading: reportsLoading, error: reportsError, refetch: refetchReports } = useReports(selectedProjectId);
  const { mutate: generateReport, loading: generating, error: generateError } = useGenerateReport();

  const [reportType, setReportType] = useState('comprehensive');
  const [execParams, setExecParams] = useState({
    kernel_coverage: 'full',
    deterministic_analysis: true,
    nfpa_compliance: true,
    execution_timeout: 30,
  });

  const handleGenerate = async () => {
    if (!selectedProjectId) {
      // FIX: fail loud instead of sending a hardcoded literal to the backend.
      // Previous behavior: POST /api/v1/projects/default-project-id/reports → 404 every time.
      alert(t('reports.selectProjectFirst', 'Please select a project before generating a report.'));
      return;
    }
    const result = await generateReport({
      projectId: selectedProjectId,
      data: {
        type: reportType,
        execution_params: execParams,
      }
    });
    if (result) {
      refetchReports();
    }
  };

  // Sample data for demonstration
  const sampleDevices = [
    { id: 'dev-1', name: 'Smoke Detector 01', type: 'smoke', standbyCurrent: 100, alarmCurrent: 200, count: 50 },
    { id: 'dev-2', name: 'Heat Detector 01', type: 'heat', standbyCurrent: 120, alarmCurrent: 250, count: 20 },
    { id: 'dev-3', name: 'Pull Station 01', type: 'pull', standbyCurrent: 80, alarmCurrent: 150, count: 10 },
    { id: 'dev-4', name: 'Horn/Strobe 01', type: 'horns', standbyCurrent: 150, alarmCurrent: 300, count: 30 },
  ];

  // Define the Room type to match the expected interface
  interface Room {
    id: string;
    name: string;
    width: number;
    length: number;
    height: number;
    ceilingType: 'flat' | 'sloped' | 'coffered';
    occupancy: string;
  }

  const sampleRooms: Room[] = [
    { id: 'rm-1', name: 'Main Lobby', width: 15, length: 20, height: 3.5, ceilingType: 'flat', occupancy: 'high' },
    { id: 'rm-2', name: 'Conference Room A', width: 8, length: 10, height: 3.2, ceilingType: 'flat', occupancy: 'medium' },
    { id: 'rm-3', name: 'Electrical Room', width: 6, length: 8, height: 3.0, ceilingType: 'flat', occupancy: 'low' },
  ];

  // Define the Detector type to match the expected interface
  interface Detector {
    id: string;
    roomId: string;
    type: 'smoke' | 'heat' | 'rate-of-rise' | 'flame-detector';
    x: number;
    y: number;
    coverageRadius: number;
    sensitivity: 'high' | 'standard' | 'low';
  }

  const sampleDetectors: Detector[] = [
    { id: 'det-1', roomId: 'rm-1', type: 'smoke', x: 5, y: 5, coverageRadius: 6.37, sensitivity: 'standard' },
    { id: 'det-2', roomId: 'rm-1', type: 'smoke', x: 10, y: 5, coverageRadius: 6.37, sensitivity: 'standard' },
    { id: 'det-3', roomId: 'rm-2', type: 'smoke', x: 3, y: 3, coverageRadius: 6.37, sensitivity: 'standard' },
    { id: 'det-4', roomId: 'rm-3', type: 'heat', x: 2, y: 2, coverageRadius: 4.27, sensitivity: 'standard' },
  ];

  const batteryCalculation = calculateBatteryRequirements({
    devices: sampleDevices,
    standbyHours: 24,
    alarmMinutes: 5,
    safetyFactor: 1.2
  });

  const coverageCalculation = calculateCoverage(sampleRooms, sampleDetectors);

  return (
    <div className="flex-1 overflow-auto" aria-label={t('reports.title')}>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">{t('reports.title')}</h1>
            <p className="text-sm text-slate-400 mt-1">{t('reports.subtitle')}</p>
          </div>
          <Button
            variant="outline"
            className="border-slate-600 text-slate-300 hover:bg-slate-800"
            onClick={() => refetchReports()}
          >
            <Clock className="h-4 w-4 mr-1" />
            {t('reports.refresh')}
          </Button>
        </div>

        {/* Error banner */}
        {generateError && (
          <Card className="border-red-500/30 bg-red-500/5">
            <CardContent className="p-3">
              <p className="text-sm text-red-400">{t('reports.reportGenerationFailed')}: {generateError}</p>
            </CardContent>
          </Card>
        )}

        {/* Report Generation Card */}
        <Card className="border-slate-700 bg-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-100">{t('reports.generate')}</CardTitle>
            <CardDescription className="text-slate-400">
              {t('reports.parameters')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-slate-300">{t('reports.reportType')}</Label>
                <Select value={reportType} onValueChange={setReportType}>
                  <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    <SelectItem value="voltage-drop">{t('reports.voltageDropAnalysis')}</SelectItem>
                    <SelectItem value="short-circuit">{t('reports.shortCircuitStudy')}</SelectItem>
                    <SelectItem value="cable-sizing">{t('reports.cableSizingReport')}</SelectItem>
                    <SelectItem value="load-flow">{t('reports.loadFlowAnalysis')}</SelectItem>
                    <SelectItem value="comprehensive">{t('reports.comprehensiveReport')}</SelectItem>
                    <SelectItem value="nfpa-compliance">{t('reports.nfpaCompliance')}</SelectItem>
                    <SelectItem value="battery-calculations">{t('reports.batteryCalculations')}</SelectItem>
                    <SelectItem value="coverage-analysis">{t('reports.coverageAnalysis')}</SelectItem>
                    <SelectItem value="cause-effect">{t('reports.causeEffectMatrix')}</SelectItem>
                    <SelectItem value="cable-schedule">{t('reports.cableSchedule')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">{t('reports.executionParams')}</Label>
                <Select value={execParams.kernel_coverage} onValueChange={(v) => setExecParams(p => ({ ...p, kernel_coverage: v }))}>
                  <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    <SelectItem value="minimal">Minimal Coverage</SelectItem>
                    <SelectItem value="standard">Standard Coverage</SelectItem>
                    <SelectItem value="full">Full Coverage</SelectItem>
                    <SelectItem value="custom">Custom Coverage</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex items-center gap-4 pt-2">
              <div className="flex items-center gap-2">
                <Label className="flex items-center gap-2 text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={execParams.deterministic_analysis}
                    onChange={(e) => setExecParams(p => ({ ...p, deterministic_analysis: e.target.checked }))}
                    className="rounded bg-slate-900 border-slate-600 text-red-500 focus:ring-red-500"
                  />
                  Deterministic Analysis
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Label className="flex items-center gap-2 text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={execParams.nfpa_compliance}
                    onChange={(e) => setExecParams(p => ({ ...p, nfpa_compliance: e.target.checked }))}
                    className="rounded bg-slate-900 border-slate-600 text-red-500 focus:ring-red-500"
                  />
                  NFPA Compliance
                </Label>
              </div>
            </div>

            <Button
              className="bg-red-600 hover:bg-red-700 text-white border-none"
              onClick={handleGenerate}
              disabled={generating}
            >
              {generating ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  {t('reports.generating')}
                </>
              ) : (
                <>
                  <FileText className="h-4 w-4 mr-1" />
                  {t('reports.generate')}
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Battery Calculation Report Preview */}
        <Card className="border-slate-700 bg-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-100">{t('reports.batteryCalculations')}</CardTitle>
            <CardDescription className="text-slate-400">
              {t('reports.batteryCalculationsDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-slate-100">{batteryCalculation.totalStandbyCurrent}</div>
                <div className="text-sm text-slate-400">{t('reports.totalStandbyCurrent')}</div>
              </div>
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-slate-100">{batteryCalculation.totalAlarmCurrent}</div>
                <div className="text-sm text-slate-400">{t('reports.totalAlarmCurrent')}</div>
              </div>
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-slate-100">{batteryCalculation.requiredCapacity}</div>
                <div className="text-sm text-slate-400">{t('reports.requiredCapacity')}</div>
              </div>
            </div>
            <div className="mt-4">
              <div className="text-sm font-medium text-slate-300 mb-2">{t('reports.recommendedBattery')}</div>
              <div className="text-lg font-semibold text-emerald-400">{batteryCalculation.recommendedBattery.voltage}V {batteryCalculation.recommendedBattery.capacity}Ah</div>
            </div>
          </CardContent>
        </Card>

        {/* Coverage Analysis Report Preview */}
        <Card className="border-slate-700 bg-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-100">{t('reports.coverageAnalysis')}</CardTitle>
            <CardDescription className="text-slate-400">
              {t('reports.coverageAnalysisDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-slate-100">{coverageCalculation.summary.totalRooms}</div>
                <div className="text-sm text-slate-400">{t('reports.totalRooms')}</div>
              </div>
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-slate-100">{coverageCalculation.summary.totalDetectors}</div>
                <div className="text-sm text-slate-400">{t('reports.totalDetectors')}</div>
              </div>
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-slate-100">{coverageCalculation.summary.coveragePercentage}%</div>
                <div className="text-sm text-slate-400">{t('reports.overallCoverage')}</div>
              </div>
              <div className="bg-slate-900/50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-emerald-400">{coverageCalculation.summary.passedRooms}</div>
                <div className="text-sm text-slate-400">{t('reports.passedRooms')}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Report History */}
        <Card className="border-slate-700 bg-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-100">{t('reports.history')}</CardTitle>
            <CardDescription className="text-slate-400">
              {reportsLoading ? t('reports.loading') : `${reports?.length || 0} ${t('reports.reports')}`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {reportsLoading ? (
              // Skeleton loader for reports
              <div className="space-y-4">
                {[...Array(5)].map((_, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-700/50">
                    <div className="flex items-center gap-3">
                      <Skeleton className="h-8 w-8 rounded" />
                      <div className="space-y-2">
                        <Skeleton className="h-4 w-40 bg-slate-700" />
                        <Skeleton className="h-3 w-32 bg-slate-700" />
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Skeleton className="h-8 w-20 rounded" />
                      <Skeleton className="h-8 w-8 rounded" />
                    </div>
                  </div>
                ))}
              </div>
            ) : reportsError ? (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
                <p className="text-red-400 text-sm">{t('reports.errorLoading')}: {reportsError}</p>
              </div>
            ) : !reports || reports.length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                <FileText className="h-8 w-8 mx-auto mb-3 opacity-50" />
                <p>{t('reports.noReports')}</p>
                <p className="text-sm mt-1">{t('reports.createFirst')}</p>
              </div>
            ) : (
              <ScrollArea className="max-h-96">
                <div className="space-y-2">
                  {reports.map((report) => (
                    <div
                      key={report.id}
                      className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-700/50"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded bg-blue-500/10 flex items-center justify-center">
                          <FileText className="h-4 w-4 text-blue-400" />
                        </div>
                        <div>
                          <div className="text-sm font-medium text-slate-200">
                            {report.type.replace('-', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </div>
                          <div className="text-xs text-slate-400 flex items-center gap-3">
                            <span className="flex items-center gap-1">
                              <Calendar className="h-3 w-3" />
                              {new Date(report.createdAt).toLocaleDateString()}
                            </span>
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {new Date(report.createdAt).toLocaleTimeString()}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={report.status === 'completed' ? 'default' : report.status === 'pending' ? 'secondary' : 'destructive'}
                          className={
                            report.status === 'completed'
                              ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/30'
                              : report.status === 'pending'
                              ? 'bg-amber-600/20 text-amber-400 border-amber-500/30'
                              : 'bg-red-600/20 text-red-400 border-red-500/30'
                          }
                        >
                          {report.status}
                        </Badge>
                        <Button
                          variant="outline"
                          size="sm"
                          className="border-slate-600 text-slate-300"
                          onClick={() => {
                            // V186 FIX: Download button was non-functional (no onClick).
                            // Now exports the report as a JSON file — root-cause fix that
                            // gives users an actual file download instead of an inert button.
                            try {
                              const payload = JSON.stringify(report, null, 2);
                              const blob = new Blob([payload], { type: 'application/json' });
                              const url = URL.createObjectURL(blob);
                              const link = document.createElement('a');
                              link.href = url;
                              link.download = `report-${report.id}-${new Date().toISOString().slice(0, 10)}.json`;
                              document.body.appendChild(link);
                              link.click();
                              document.body.removeChild(link);
                              URL.revokeObjectURL(url);
                            } catch (err) {
                              console.error('Download failed:', err);
                            }
                          }}
                          aria-label={t('common.download')}
                          title={t('common.download')}
                          disabled={report.status !== 'completed'}
                        >
                          <Download className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}