/**
 * DashboardPage.tsx - Connected dashboard showing real API data
 */
import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Activity,
  Server,
  FolderKanban,
  Cpu,
  Cable,
  Plus,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowUpRight,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useHealth, useProjects } from '@/hooks/useApi';
import { useCreateProject } from '@/hooks/useApi';
import type { Project } from '@/services/digitalTwinApi';

export function DashboardPage() {
  const { data: health, loading: healthLoading, connected, refetch: refetchHealth } = useHealth();
  const { data: projects, loading: projectsLoading, error: projectsError, refetch: refetchProjects } = useProjects();
  const { mutate: createProject, loading: creating } = useCreateProject();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');

  // Calculate totals from projects
  const totalDevices = projects?.reduce((sum: number, p: Project) => sum + (p.deviceCount || 0), 0) || 0;
  const totalConnections = projects?.reduce((sum: number, p: Project) => sum + (p.connectionCount || 0), 0) || 0;
  const activeProjects = projects?.filter((p: Project) => p.status === 'active').length || 0;

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    const result = await createProject({
      name: newProjectName.trim(),
      description: newProjectDesc.trim() || undefined,
      author: 'FireAI User',
    });
    if (result) {
      setNewProjectName('');
      setNewProjectDesc('');
      setShowCreateForm(false);
      refetchProjects();
    }
  };

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>
            <p className="text-sm text-slate-400 mt-1">FireAI Revit Digital Twin Platform</p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              className="border-slate-600 text-slate-300 hover:bg-slate-800"
              onClick={() => { refetchHealth(); refetchProjects(); }}
            >
              <RefreshCw className="h-4 w-4 mr-1" />
              Refresh
            </Button>
            <Button
              size="sm"
              className="bg-red-600 hover:bg-red-700 text-white border-none"
              onClick={() => setShowCreateForm(true)}
            >
              <Plus className="h-4 w-4 mr-1" />
              New Project
            </Button>
          </div>
        </div>

        {/* Connection Status Bar */}
        <Card className={`border ${connected ? 'border-emerald-500/30 bg-emerald-500/5' : healthLoading ? 'border-yellow-500/30 bg-yellow-500/5' : 'border-red-500/30 bg-red-500/5'}`}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {connected ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                ) : healthLoading ? (
                  <Clock className="h-5 w-5 text-yellow-400 animate-pulse" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-400" />
                )}
                <div>
                  <span className="text-sm font-medium text-slate-200">
                    Backend: {connected ? 'Connected' : healthLoading ? 'Connecting...' : 'Disconnected'}
                  </span>
                  {health && (
                    <span className="text-xs text-slate-400 ml-3">
                      v{health.version} • DB: {health.database} • Uptime: {Math.floor((health.uptime || 0) / 60)}min
                    </span>
                  )}
                </div>
              </div>
              <Badge variant={connected ? 'default' : 'destructive'} className={connected ? 'bg-emerald-600' : ''}>
                {connected ? 'LIVE' : 'OFFLINE'}
              </Badge>
            </div>
          </CardContent>
        </Card>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Projects"
            value={projectsLoading ? '...' : String(projects?.length || 0)}
            subtitle={`${activeProjects} active`}
            icon={<FolderKanban className="h-5 w-5" />}
            color="blue"
          />
          <StatCard
            title="Total Devices"
            value={projectsLoading ? '...' : String(totalDevices)}
            subtitle="Across all projects"
            icon={<Cpu className="h-5 w-5" />}
            color="emerald"
          />
          <StatCard
            title="Connections"
            value={projectsLoading ? '...' : String(totalConnections)}
            subtitle="Cable connections"
            icon={<Cable className="h-5 w-5" />}
            color="amber"
          />
          <StatCard
            title="API Status"
            value={connected ? 'Healthy' : 'Down'}
            subtitle={health ? `v${health.version}` : 'No response'}
            icon={<Server className="h-5 w-5" />}
            color={connected ? 'emerald' : 'red'}
          />
        </div>

        {/* Create Project Form */}
        {showCreateForm && (
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg text-slate-100">Create New Project</CardTitle>
              <CardDescription className="text-slate-400">Add a new digital twin project</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="text-slate-300">Project Name</Label>
                <Input
                  placeholder="e.g., Tower-B Fire Alarm System"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Description</Label>
                <Input
                  placeholder="Brief description of the project"
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  className="bg-red-600 hover:bg-red-700 text-white border-none"
                  onClick={handleCreateProject}
                  disabled={creating || !newProjectName.trim()}
                >
                  {creating ? 'Creating...' : 'Create Project'}
                </Button>
                <Button
                  variant="outline"
                  className="border-slate-600 text-slate-300"
                  onClick={() => setShowCreateForm(false)}
                >
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Projects List */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg text-slate-100">Recent Projects</CardTitle>
                <CardDescription className="text-slate-400">
                  {projectsLoading ? 'Loading...' : projectsError ? `Error: ${projectsError}` : `${projects?.length || 0} projects found`}
                </CardDescription>
              </div>
              <NavLink to="/projects">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-slate-400 hover:text-slate-200"
                >
                  View All <ArrowUpRight className="h-3 w-3 ml-1" />
                </Button>
              </NavLink>
            </div>
          </CardHeader>
          <CardContent>
            {projectsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Activity className="h-6 w-6 text-slate-400 animate-pulse" />
                <span className="ml-2 text-slate-400">Loading projects...</span>
              </div>
            ) : !projects || projects.length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                <FolderKanban className="h-10 w-10 mx-auto mb-2 opacity-50" />
                <p>No projects found. Create your first project!</p>
              </div>
            ) : (
              <ScrollArea className="max-h-96">
                <div className="space-y-2">
                  {projects.map((project: Project) => (
                    <div
                      key={project.id}
                      className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-700/50 hover:border-slate-600 transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-8 h-8 rounded bg-blue-500/10 flex items-center justify-center shrink-0">
                          <FolderKanban className="h-4 w-4 text-blue-400" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-slate-200 truncate">{project.name}</div>
                          <div className="text-xs text-slate-400 truncate">{project.description || 'No description'}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                          <span className="flex items-center gap-1">
                            <Cpu className="h-3 w-3" /> {project.deviceCount || 0}
                          </span>
                          <span className="flex items-center gap-1">
                            <Cable className="h-3 w-3" /> {project.connectionCount || 0}
                          </span>
                        </div>
                        <Badge
                          variant={project.status === 'active' ? 'default' : 'secondary'}
                          className={
                            project.status === 'active'
                              ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/30'
                              : project.status === 'draft'
                              ? 'bg-yellow-600/20 text-yellow-400 border-yellow-500/30'
                              : 'bg-slate-600/20 text-slate-400 border-slate-500/30'
                          }
                        >
                          {project.status}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        {/* System Info */}
        <Card className="border-slate-700 bg-slate-800/80">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-100">System Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <InfoItem label="API Version" value={health?.version || 'N/A'} />
              <InfoItem label="Database" value={health?.database || 'N/A'} />
              <InfoItem label="Uptime" value={health ? `${Math.floor((health.uptime || 0) / 60)} min` : 'N/A'} />
              <InfoItem label="Last Check" value={health?.timestamp ? new Date(health.timestamp).toLocaleTimeString() : 'N/A'} />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ============================================================================
// Sub-components
// ============================================================================

function StatCard({ title, value, subtitle, icon, color }: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ReactNode;
  color: 'blue' | 'emerald' | 'amber' | 'red';
}) {
  const colorMap = {
    blue: 'text-blue-400 bg-blue-500/10',
    emerald: 'text-emerald-400 bg-emerald-500/10',
    amber: 'text-amber-400 bg-amber-500/10',
    red: 'text-red-400 bg-red-500/10',
  };

  return (
    <Card className="border-slate-700 bg-slate-800/80">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium uppercase tracking-wider text-slate-400">{title}</span>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colorMap[color]}`}>
            {icon}
          </div>
        </div>
        <div className="text-2xl font-bold text-slate-100">{value}</div>
        <div className="text-xs text-slate-400 mt-1">{subtitle}</div>
      </CardContent>
    </Card>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-400 uppercase tracking-wider">{label}</div>
      <Separator className="my-1 bg-slate-700" />
      <div className="text-sm font-mono text-slate-200">{value}</div>
    </div>
  );
}
