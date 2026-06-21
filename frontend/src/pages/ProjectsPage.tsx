/**
 * ProjectsPage.tsx - Project management with full CRUD + Device & Connection creation
 */
import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Link } from 'react-router-dom';
import { useProjects, useCreateProject, useDeleteProject, useSyncProject } from '@/hooks/useApi';
import { FolderPlus, Loader2, Folder, User, Clock, Link as LinkIcon, Eye, Trash2, RefreshCw } from 'lucide-react';
import { api } from '@/services/digitalTwinApi';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DEVICE_LIBRARY, DEVICE_CATEGORIES, getDevicesByCategory } from '@/types/deviceLibrary';
import type { DeviceCategory, DeviceSpec } from '@/types/deviceLibrary';
import { useInputNormalization } from '@/hooks/useInputNormalization';
import type { Project, Device, CreateDeviceInput, CreateConnectionInput } from '@/services/digitalTwinApi';
import { Skeleton } from '@/components/ui/skeleton';

// ============================================================================
// Connection types for the dropdown
// ============================================================================
const CONNECTION_TYPES = [
  'power',
  'signal',
  'data',
  'fire_alarm_loop',
  'nac_circuit',
  'poe',
  'cable',
] as const;

const CABLE_SIZES = [
  '1.5mm²',
  '2.5mm²',
  '4mm²',
  '6mm²',
  '10mm²',
  '16mm²',
  '25mm²',
  '35mm²',
  '50mm²',
  '70mm²',
  '95mm²',
  '120mm²',
] as const;

// ============================================================================
// ProjectsPage Component
// ============================================================================

export function ProjectsPage() {
  const { t } = useTranslation();
  const { data: projects, loading: projectsLoading, error: projectsError, refetch } = useProjects();
  const { mutate: deleteProject, loading: deleting } = useDeleteProject();
  const { mutate: syncProject, loading: syncing } = useSyncProject();
  const { mutate: createProject, loading: creatingProject } = useCreateProject();
  const [newProject, setNewProject] = useState({ name: '', description: '' });
  const [creating, setCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [syncTarget, setSyncTarget] = useState<Project | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');
  // Phase 3: surface "Did you mean?" toast when backend normalized input.
  const { showIfNormalized } = useInputNormalization();

  const filteredProjects = useMemo(() => {
    if (!projects) return [];
    return projects.filter(project => 
      statusFilter === 'all' || project.status === statusFilter
    );
  }, [projects, statusFilter]);

  const handleCreate = async () => {
    if (!newProject.name.trim()) return;
    
    setCreating(true);
    const result = await createProject(newProject);
    if (result) {
      // If the backend normalized the project name/description (Arabic
      // mistype → English QWERTY recovery), show a toast so the user
      // can verify the saved value matches their intent.
      showIfNormalized({
        title: t('projects.inputNormalizedTitle', 'Input normalized'),
        description: t(
          'projects.inputNormalizedDesc',
          'Your project name/description was automatically converted from Arabic keyboard to English. Please verify the saved value.'
        ),
      });
      setNewProject({ name: '', description: '' });
      setShowCreateForm(false);
      refetch();
    }
    setCreating(false);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    
    const result = await deleteProject(deleteTarget.id);
    if (result) {
      setDeleteTarget(null);
      refetch();
    }
  };

  const handleSync = async () => {
    if (!syncTarget) return;
    
    const result = await syncProject(syncTarget.id);
    if (result) {
      setSyncTarget(null);
      refetch();
    }
  };

  return (
    <div className="flex-1 overflow-auto" aria-label={t('projects.title')}>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">{t('projects.title')}</h1>
            <p className="text-sm text-slate-400 mt-1">{t('projects.subtitle')}</p>
          </div>
          <Button
            className="bg-red-600 hover:bg-red-700 text-white border-none"
            onClick={() => setShowCreateForm(true)}
          >
            <FolderPlus className="h-4 w-4 mr-1" />
            {t('projects.newProject')}
          </Button>
        </div>

        {/* Create Project Form */}
        {showCreateForm && (
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader>
              <CardTitle className="text-lg text-slate-100">{t('projects.createProject')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="text-slate-300">{t('projects.projectName')}</Label>
                <Input
                  value={newProject.name}
                  onChange={(e) => setNewProject(p => ({ ...p, name: e.target.value }))}
                  placeholder={t('projects.projectName')}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">{t('projects.description')}</Label>
                <Input
                  value={newProject.description}
                  onChange={(e) => setNewProject(p => ({ ...p, description: e.target.value }))}
                  placeholder={t('projects.description')}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <Button
                  variant="outline"
                  className="border-slate-600 text-slate-300"
                  onClick={() => {
                    setShowCreateForm(false);
                    setNewProject({ name: '', description: '' });
                  }}
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  className="bg-red-600 hover:bg-red-700 text-white border-none"
                  onClick={handleCreate}
                  disabled={creating || !newProject.name.trim()}
                >
                  {creating ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                      {t('common.creating')}
                    </>
                  ) : (
                    t('projects.createProject')
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[180px] bg-slate-800 border-slate-600 text-white">
              <SelectValue placeholder={t('projects.allStatuses')} />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-600 text-white">
              <SelectItem value="all">{t('projects.allStatuses')}</SelectItem>
              <SelectItem value="active">{t('projects.active')}</SelectItem>
              <SelectItem value="inactive">{t('projects.inactive')}</SelectItem>
              <SelectItem value="draft">{t('projects.draft')}</SelectItem>
              <SelectItem value="archived">{t('projects.archived')}</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            className="border-slate-600 text-slate-300 hover:bg-slate-800"
            onClick={() => refetch()}
          >
            <RefreshCw className="h-4 w-4 mr-1" />
            {t('projects.refresh')}
          </Button>
        </div>

        {/* Error */}
        {projectsError && (
          <Card className="border-red-500/30 bg-red-500/5">
            <CardContent className="p-4">
              <p className="text-red-400">{t('projects.errorLoading')}: {projectsError}</p>
            </CardContent>
          </Card>
        )}

        {/* Loading State with Skeletons */}
        {projectsLoading && (
          <div className="space-y-4">
            {[...Array(3)].map((_, index) => (
              <Card key={index} className="border-slate-700 bg-slate-800/80">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <Skeleton className="h-5 w-48 bg-slate-700" />
                      <Skeleton className="h-4 w-32 bg-slate-700 mt-2" />
                    </div>
                    <Skeleton className="h-9 w-24 rounded" />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4 text-sm text-slate-400">
                      <Skeleton className="h-4 w-24" />
                      <Skeleton className="h-4 w-20" />
                      <Skeleton className="h-4 w-16" />
                    </div>
                    <div className="flex gap-2">
                      <Skeleton className="h-8 w-8 rounded" />
                      <Skeleton className="h-8 w-8 rounded" />
                      <Skeleton className="h-8 w-8 rounded" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!projectsLoading && (!filteredProjects || filteredProjects.length === 0) && (
          <div className="py-12">
            <EmptyState
              icon={<Folder className="h-12 w-12" />}
              title={t('projects.noProjects')}
              description={t('projects.createFirst')}
              action={{
                label: t('projects.newProject'),
                onClick: () => setShowCreateForm(true),
              }}
            />
          </div>
        )}

        {/* Projects List */}
        {!projectsLoading && filteredProjects && filteredProjects.length > 0 && (
          <div className="space-y-4">
            {filteredProjects.map((project: Project) => (
              <Card key={project.id} className="border-slate-700 bg-slate-800/80">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-lg text-slate-100">{project.name}</CardTitle>
                      <CardDescription className="text-slate-400 mt-1">
                        {project.description || t('common.noData')}
                      </CardDescription>
                    </div>
                    <Badge
                      variant={project.status === 'active' ? 'default' : project.status === 'draft' ? 'secondary' : project.status === 'archived' ? 'outline' : 'destructive'}
                      className={
                        project.status === 'active'
                          ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/30'
                          : project.status === 'draft'
                          ? 'bg-amber-600/20 text-amber-400 border-amber-500/30'
                          : project.status === 'archived'
                          ? 'bg-slate-600/20 text-slate-400 border-slate-500/30'
                          : 'bg-slate-600/20 text-slate-400 border-slate-500/30'
                      }
                    >
                      {project.status === 'active' ? t('projects.active') : project.status === 'draft' ? t('projects.draft') : project.status === 'archived' ? t('projects.archived') : t('projects.inactive')}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4 text-sm text-slate-400">
                      <div className="flex items-center gap-1">
                        <User className="h-4 w-4" />
                        {project.author}
                      </div>
                      <div className="flex items-center gap-1">
                        <Clock className="h-4 w-4" />
                        {new Date(project.createdAt).toLocaleDateString()}
                      </div>
                      <div className="flex items-center gap-1">
                        <div className="w-4 h-4">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                          </svg>
                        </div>
                        {project.deviceCount} {t('projects.devices')}
                      </div>
                      <div className="flex items-center gap-1">
                        <LinkIcon className="h-4 w-4" />
                        {project.connectionCount} {t('projects.connections')}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="border-slate-600 text-slate-300"
                        onClick={() => setSyncTarget(project)}
                      >
                        {syncing && syncTarget?.id === project.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <RefreshCw className="h-4 w-4" />
                        )}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="border-slate-600 text-slate-300"
                        onClick={() => {
                          window.location.hash = `/projects/${project.id}`;
                        }}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="border-slate-600 text-slate-300"
                        onClick={() => setDeleteTarget(project)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Sync Confirmation Modal */}
        {syncTarget && (
          <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
            <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-md w-full p-6">
              <h3 className="text-lg font-semibold text-slate-100">{t('projects.sync')}</h3>
              <p className="text-slate-400 mt-2">
                {t('projects.syncConfirm', { name: syncTarget.name })}
              </p>
              <div className="flex justify-end gap-3 mt-6">
                <Button
                  variant="outline"
                  className="border-slate-600 text-slate-300"
                  onClick={() => setSyncTarget(null)}
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  className="bg-red-600 hover:bg-red-700 text-white border-none"
                  onClick={handleSync}
                  disabled={syncing}
                >
                  {syncing ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                      {t('projects.syncing')}
                    </>
                  ) : (
                    t('projects.sync')
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {deleteTarget && (
          <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
            <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-md w-full p-6">
              <h3 className="text-lg font-semibold text-slate-100">{t('projects.deleteProject')}</h3>
              <p className="text-slate-400 mt-2">
                {t('projects.deleteConfirmMessage', { name: deleteTarget.name })}
              </p>
              <div className="flex justify-end gap-3 mt-6">
                <Button
                  variant="outline"
                  className="border-slate-600 text-slate-300"
                  onClick={() => setDeleteTarget(null)}
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  className="bg-red-600 hover:bg-red-700 text-white border-none"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                      {t('common.deleting')}
                    </>
                  ) : (
                    t('projects.deleteProject')
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Form state types & defaults
// ============================================================================

interface DeviceFormState {
  category: string;
  type: string;
  name: string;
  x: number;
  y: number;
  z: number;
  voltage: number;
  current: number;
  load: number;
  loadUnit: 'A' | 'mA' | 'W';  // BUG-30 FIX: Track load unit
}

function getDefaultDeviceForm(): DeviceFormState {
  const firstCat = DEVICE_CATEGORIES[0];
  const firstDevice = getDevicesByCategory(firstCat.id)[0];
  return {
    category: firstCat.id,
    type: firstDevice?.id || '',
    name: firstDevice?.name || '',
    x: 0,
    y: 0,
    z: 0,
    voltage: firstDevice?.defaultVoltage || 24,
    current: firstDevice?.defaultCurrent || 0,
    load: firstDevice?.defaultLoad || 0,
    loadUnit: 'A',  // BUG-30 FIX: Default to Amperes
  };
}

interface ConnectionFormState {
  fromDeviceId: string;
  toDeviceId: string;
  type: string;
  cableSize: string;
  length: number;
}

function getDefaultConnectionForm(): ConnectionFormState {
  return {
    fromDeviceId: '',
    toDeviceId: '',
    type: '',
    cableSize: '',
    length: 0,
  };
}