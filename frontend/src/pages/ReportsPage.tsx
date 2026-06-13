/**
 * ReportsPage.tsx - Generate, view, and export project reports
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
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
  Plus,
  RefreshCw,
  Download,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  FolderKanban,
} from 'lucide-react';
import { useProjects, useReports } from '@/hooks/useApi';
import { api } from '@/services/digitalTwinApi';
import type { Project, Report, GenerateReportInput } from '@/services/digitalTwinApi';
import { AccessibleToast } from '@/components/ui/AccessibleToast';

// ============================================================================
// Report type definitions
// ============================================================================

const REPORT_TYPES = [
  { id: 'voltage_drop', label: 'Voltage Drop Analysis', description: 'IEC 60364 compliant voltage drop calculation' },
  { id: 'nfpa72_coverage', label: 'NFPA 72 Coverage', description: 'Detector coverage and spacing compliance' },
  { id: 'nfpa72_battery', label: 'Battery Calculation', description: 'Standby and alarm battery sizing per NFPA 72 §27.6.2' },
  { id: 'cable_sizing', label: 'Cable Sizing Report', description: 'Cable ampacity and derating analysis' },
] as const;

// ============================================================================
// ReportsPage Component
// ============================================================================

export function ReportsPage() {
  const { t } = useTranslation();
  const { data: projects, loading: projectsLoading, refetch: refetchProjects } = useProjects();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const { data: reports, loading: reportsLoading, error: reportsError, refetch: refetchReports } = useReports(selectedProjectId);

  const [showGenerateForm, setShowGenerateForm] = useState(false);
  const [reportType, setReportType] = useState('voltage_drop');
  const [reportName, setReportName] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [toastType, setToastType] = useState<'success' | 'error' | 'warning' | 'info'>('info');

  const selectedProject = projects?.find((p: Project) => p.id === selectedProjectId) || null;

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleGenerateReport = async () => {
    if (!selectedProjectId) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const input: GenerateReportInput = {
        type: reportType,
        name: reportName.trim() || REPORT_TYPES.find(t => t.id === reportType)?.label || reportType,
        parameters: {},
      };
      const res = await api.generateReport(selectedProjectId, input);
      if (res.success) {
        setShowGenerateForm(false);
        setReportName('');
        refetchReports();
      } else {
        setGenerateError(res.error || 'Failed to generate report');
      }
    } catch (err: unknown) {
      setGenerateError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setGenerating(false);
    }
  };

  const handleExportReport = async (report: Report, format: string) => {
    if (!selectedProjectId) return;
    setExporting(report.id);
    try {
      const blob = await api.exportReport(selectedProjectId, report.id, format);
      // Download the blob
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${report.name || report.type}_${report.id.slice(0, 8)}.${format === 'pdf' ? 'pdf' : 'json'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch {
      // Export may fail if backend doesn't support it
      setToastMessage(t('reports.exportFailed'));
      setToastType('error');
    } finally {
      setExporting(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Status helpers
  // ---------------------------------------------------------------------------

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-400" />;
      case 'pending':
        return <Clock className="h-4 w-4 text-yellow-400 animate-pulse" />;
      default:
        return <AlertTriangle className="h-4 w-4 text-slate-400" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge className="bg-emerald-600/20 text-emerald-400 border-emerald-500/30">{status}</Badge>;
      case 'failed':
        return <Badge variant="destructive" className="bg-red-600/20 text-red-400 border-red-500/30">{status}</Badge>;
      case 'pending':
        return <Badge className="bg-yellow-600/20 text-yellow-400 border-yellow-500/30">{status}</Badge>;
      default:
        return <Badge variant="outline" className="border-slate-600 text-slate-400">{status}</Badge>;
    }
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex-1 overflow-auto" aria-label={t('reports.title')}>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">{t('reports.title')}</h1>
            <p className="text-sm text-slate-400 mt-1">{t('reports.subtitle')}</p>
          </div>
          <div className="flex items-center gap-3">
            {selectedProjectId && (
              <Button
                variant="outline"
                size="sm"
                className="border-slate-600 text-slate-300"
                onClick={() => refetchReports()}
              >
                <RefreshCw className="h-4 w-4 mr-1" /> {t('common.refresh')}
              </Button>
            )}
          </div>
        </div>

        {/* Project Selector */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-100">Select Project</CardTitle>
            <CardDescription className="text-slate-400">Choose a project to view and generate reports</CardDescription>
          </CardHeader>
          <CardContent>
            {projectsLoading ? (
              <div className="flex items-center gap-2 text-slate-400">
                <Activity className="h-4 w-4 animate-pulse" />
                <span className="text-sm">Loading projects...</span>
              </div>
            ) : !projects || projects.length === 0 ? (
              <div className="text-center py-6 text-slate-400">
                <FolderKanban className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No projects available. Create a project first.</p>
              </div>
            ) : (
              <Select
                value={selectedProjectId || ''}
                onValueChange={(v) => {
                  setSelectedProjectId(v);
                  setShowGenerateForm(false);
                }}
              >
                <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                  <SelectValue placeholder="Choose a project..." />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  {projects.map((project: Project) => (
                    <SelectItem key={project.id} value={project.id}>
                      {project.name} ({project.deviceCount || 0} devices)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </CardContent>
        </Card>

        {/* Report content for selected project */}
        {selectedProjectId && selectedProject && (
          <>
            {/* Generate Report */}
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium text-slate-200">
                Reports for {selectedProject.name}
              </h2>
              <Button
                size="sm"
                className="bg-red-600 hover:bg-red-700 text-white border-none"
                onClick={() => {
                  setGenerateError(null);
                  setShowGenerateForm(true);
                }}
              >
                <Plus className="h-4 w-4 mr-1" /> Generate Report
              </Button>
            </div>

            {/* Generate Form */}
            {showGenerateForm && (
              <Card className="border-slate-700 bg-slate-800/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg text-slate-100">Generate New Report</CardTitle>
                  <CardDescription className="text-slate-400">Select report type and generate</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {generateError && (
                    <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                      <p className="text-sm text-red-400">{generateError}</p>
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-slate-300">Report Type *</Label>
                      <Select value={reportType} onValueChange={setReportType}>
                        <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-slate-800 border-slate-700">
                          {REPORT_TYPES.map((t) => (
                            <SelectItem key={t.id} value={t.id}>
                              {t.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-slate-300">Report Name</Label>
                      <Input
                        placeholder="Optional custom name"
                        value={reportName}
                        onChange={(e) => setReportName(e.target.value)}
                        className="bg-slate-900 border-slate-600 text-slate-100"
                      />
                    </div>
                  </div>

                  {/* Report type description */}
                  <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-700/50">
                    <p className="text-xs text-slate-400">
                      {REPORT_TYPES.find(t => t.id === reportType)?.description}
                    </p>
                  </div>

                  <div className="flex gap-2">
                    <Button
                      className="bg-red-600 hover:bg-red-700 text-white border-none"
                      onClick={handleGenerateReport}
                      disabled={generating}
                    >
                      {generating ? 'Generating...' : 'Generate Report'}
                    </Button>
                    <Button
                      variant="outline"
                      className="border-slate-600 text-slate-300"
                      onClick={() => { setShowGenerateForm(false); setReportName(''); }}
                    >
                      Cancel
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Error */}
            {reportsError && (
              <Card className="border-red-500/30 bg-red-500/5">
                <CardContent className="p-3">
                  <p className="text-sm text-red-400">Error loading reports: {reportsError}</p>
                </CardContent>
              </Card>
            )}

            {/* Reports List */}
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg text-slate-100">Report History</CardTitle>
                <CardDescription className="text-slate-400">
                  {reportsLoading ? 'Loading...' : `${reports?.length || 0} reports`}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {reportsLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Activity className="h-5 w-5 text-slate-400 animate-pulse" />
                    <span className="ml-2 text-slate-400">Loading reports...</span>
                  </div>
                ) : !reports || reports.length === 0 ? (
                  <div className="text-center py-8 text-slate-400">
                    <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">No reports generated yet</p>
                    <p className="text-xs mt-1">Click "Generate Report" to create your first report</p>
                  </div>
                ) : (
                  <ScrollArea className="max-h-96">
                    <div className="space-y-2">
                      {reports.map((report: Report) => (
                        <div
                          key={report.id}
                          className="flex items-center justify-between p-4 rounded-lg bg-slate-900/50 border border-slate-700/50"
                        >
                          <div className="flex items-center gap-3">
                            {getStatusIcon(report.status)}
                            <div>
                              <div className="text-sm font-medium text-slate-200">{report.name || report.type}</div>
                              <div className="text-xs text-slate-400 mt-0.5">
                                {report.type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                                {' • '}
                                {new Date(report.createdAt).toLocaleString()}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            {getStatusBadge(report.status)}
                            {report.status === 'completed' && (
                              <div className="flex items-center gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 text-xs text-slate-400 hover:text-slate-200"
                                  onClick={() => handleExportReport(report, 'json')}
                                  disabled={exporting === report.id}
                                >
                                  <Download className="h-3 w-3 mr-1" /> JSON
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 text-xs text-slate-400 hover:text-slate-200"
                                  onClick={() => handleExportReport(report, 'pdf')}
                                  disabled={exporting === report.id}
                                >
                                  <Download className="h-3 w-3 mr-1" /> PDF
                                </Button>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                )}
              </CardContent>
            </Card>
          </>
        )}

        {/* No project selected state */}
        {selectedProjectId === null && (
          <Card className="border-slate-700 bg-slate-800/80">
            <CardContent className="py-16 text-center">
              <FileText className="h-16 w-16 mx-auto mb-4 text-slate-600" />
              <h3 className="text-lg font-medium text-slate-300">Select a Project</h3>
              <p className="text-sm text-slate-400 mt-2 max-w-md mx-auto">
                Choose a project above to view reports, generate voltage drop analysis, 
                NFPA 72 coverage studies, battery calculations, and cable sizing reports.
              </p>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Accessible Toast Notification */}
      {toastMessage && (
        <AccessibleToast
          message={toastMessage}
          type={toastType}
          onClose={() => setToastMessage(null)}
        />
      )}
    </div>
  );
}
