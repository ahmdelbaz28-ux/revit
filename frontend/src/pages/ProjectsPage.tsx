/**
 * ProjectsPage.tsx - Project management with full CRUD + Device & Connection creation
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  FolderKanban,
  Plus,
  Trash2,
  RefreshCw,
  Cpu,
  Cable,
  ChevronRight,
  ArrowLeft,
  Activity,
  Zap,
  RotateCw,
  Link as LinkIcon,
} from 'lucide-react';
import { useProjects, useDevices, useConnections, useCreateProject, useDeleteProject, useSyncProject } from '@/hooks/useApi';
import { api } from '@/services/digitalTwinApi';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DEVICE_LIBRARY, DEVICE_CATEGORIES, getDevicesByCategory } from '@/types/deviceLibrary';
import type { DeviceCategory, DeviceSpec } from '@/types/deviceLibrary';
import type { Project, Device, CreateDeviceInput, CreateConnectionInput } from '@/services/digitalTwinApi';

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
  const { data: projects, loading: projectsLoading, error: projectsError, refetch: refetchProjects } = useProjects();
  const { mutate: createProject, loading: creating, error: createError } = useCreateProject();
  const { mutate: deleteProject, loading: deleting } = useDeleteProject();
  const { mutate: syncProject, loading: syncing } = useSyncProject();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  // Fetch devices and connections for selected project
  const { data: devices, loading: devicesLoading, refetch: refetchDevices } = useDevices(selectedProjectId);
  const { data: connections, loading: connectionsLoading, refetch: refetchConnections } = useConnections(selectedProjectId);

  // Device creation modal state
  const [showDeviceModal, setShowDeviceModal] = useState(false);
  const [deviceForm, setDeviceForm] = useState<DeviceFormState>(getDefaultDeviceForm());
  const [creatingDevice, setCreatingDevice] = useState(false);
  const [deviceError, setDeviceError] = useState<string | null>(null);

  // Connection creation modal state
  const [showConnectionModal, setShowConnectionModal] = useState(false);
  const [connForm, setConnForm] = useState<ConnectionFormState>(getDefaultConnectionForm());
  const [creatingConnection, setCreatingConnection] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Delete confirmation dialog state
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; name: string } | null>(null);

  const selectedProject = projects?.find((p: Project) => p.id === selectedProjectId) || null;

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

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

  const handleDeleteProject = async (id: string) => {
    const result = await deleteProject(id);
    if (result !== null) {
      refetchProjects();
      if (selectedProjectId === id) {
        setSelectedProjectId(null);
      }
    }
    setDeleteConfirm(null);
  };

  const handleSyncProject = async (id: string) => {
    await syncProject(id);
    refetchProjects();
  };

  // Device creation
  const handleCreateDevice = async () => {
    if (!selectedProjectId || !deviceForm.name.trim() || !deviceForm.type) return;
    setCreatingDevice(true);
    setDeviceError(null);
    try {
      // SAFETY FIX (BUG-30 + BUG-33 + BUG-35): Always send load_unit with load value
      // to prevent wrong-unit errors in NFPA 72 battery calculations.
      // BUG-35: z=0 is valid (ground floor), voltage/current/load=0 is valid for passive devices.
      // Use nullish coalescing (??) instead of logical OR (||) to preserve zero values.
      // || treats 0 as falsy and replaces it with undefined — dangerous for engineering data.
      const input: CreateDeviceInput = {
        type: deviceForm.type,
        name: deviceForm.name.trim(),
        category: deviceForm.category,
        x: deviceForm.x,
        y: deviceForm.y,
        z: deviceForm.z ?? undefined,           // FIX: 0 is valid for z (ground floor)
        voltage: deviceForm.voltage ?? undefined, // FIX: 0V is valid for passive devices
        current: deviceForm.current ?? undefined, // FIX: 0A is valid for passive devices
        load: deviceForm.load ?? undefined,       // FIX: 0W is valid for passive devices
        load_unit: deviceForm.loadUnit,  // Always send unit
      };
      const res = await api.createDevice(selectedProjectId, input);
      if (res.success) {
        setShowDeviceModal(false);
        setDeviceForm(getDefaultDeviceForm());
        refetchDevices();
        refetchProjects();
      } else {
        setDeviceError(res.error || 'Failed to create device');
      }
    } catch (err: unknown) {
      setDeviceError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setCreatingDevice(false);
    }
  };

  // Connection creation
  const handleCreateConnection = async () => {
    if (!selectedProjectId || !connForm.fromDeviceId || !connForm.toDeviceId) return;
    if (connForm.fromDeviceId === connForm.toDeviceId) {
      setConnectionError('Source and target devices must be different');
      return;
    }
    setCreatingConnection(true);
    setConnectionError(null);
    try {
      const input: CreateConnectionInput = {
        fromId: connForm.fromDeviceId,
        toId: connForm.toDeviceId,
        cableSize: connForm.cableSize || undefined,
        length: connForm.length ?? undefined,   // FIX: 0-length is valid (co-located devices)
        type: connForm.type || undefined,
      };
      const res = await api.createConnection(selectedProjectId, input);
      if (res.success) {
        setShowConnectionModal(false);
        setConnForm(getDefaultConnectionForm());
        refetchConnections();
        refetchProjects();
      } else {
        setConnectionError(res.error || 'Failed to create connection');
      }
    } catch (err: unknown) {
      setConnectionError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setCreatingConnection(false);
    }
  };

  // When category changes, reset type and auto-fill defaults from library
  const handleCategoryChange = (category: string) => {
    const catDevices = getDevicesByCategory(category as DeviceCategory);
    const firstDevice = catDevices[0];
    setDeviceForm(prev => ({
      ...prev,
      category,
      type: firstDevice?.id || '',
      voltage: firstDevice?.defaultVoltage || 0,
      current: firstDevice?.defaultCurrent || 0,
      load: firstDevice?.defaultLoad || 0,
    }));
  };

  const handleDeviceTypeChange = (typeId: string) => {
    const spec = DEVICE_LIBRARY.find(d => d.id === typeId);
    setDeviceForm(prev => ({
      ...prev,
      type: typeId,
      name: spec?.name || prev.name,
      voltage: spec?.defaultVoltage ?? prev.voltage,
      current: spec?.defaultCurrent ?? prev.current,
      load: spec?.defaultLoad ?? prev.load,
    }));
  };

  // ---------------------------------------------------------------------------
  // Project detail view
  // ---------------------------------------------------------------------------

  if (selectedProjectId && selectedProject) {
    const categoryDevices = getDevicesByCategory(deviceForm.category as DeviceCategory);

    return (
      <div className="flex-1 overflow-auto">
        <div className="p-6 max-w-7xl mx-auto space-y-6">
          {/* Back button */}
          <Button
            variant="ghost"
            className="text-slate-400 hover:text-slate-200"
            onClick={() => setSelectedProjectId(null)}
          >
            <ArrowLeft className="h-4 w-4 mr-1" /> Back to Projects
          </Button>

          {/* Project Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-slate-100">{selectedProject.name}</h1>
              <p className="text-sm text-slate-400 mt-1">{selectedProject.description || 'No description'}</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                variant={selectedProject.status === 'active' ? 'default' : 'secondary'}
                className={
                  selectedProject.status === 'active'
                    ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/30'
                    : 'bg-yellow-600/20 text-yellow-400 border-yellow-500/30'
                }
              >
                {selectedProject.status}
              </Badge>
              <Button
                variant="outline"
                size="sm"
                className="border-slate-600 text-slate-300"
                onClick={() => handleSyncProject(selectedProject.id)}
                disabled={syncing}
              >
                <RotateCw className={`h-4 w-4 mr-1 ${syncing ? 'animate-spin' : ''}`} />
                {syncing ? 'Syncing...' : 'Sync'}
              </Button>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Card className="border-slate-700 bg-slate-800/80">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Cpu className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-slate-100">{selectedProject.deviceCount || devices?.length || 0}</div>
                  <div className="text-xs text-slate-400">Devices</div>
                </div>
              </CardContent>
            </Card>
            <Card className="border-slate-700 bg-slate-800/80">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
                  <Cable className="h-5 w-5 text-amber-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-slate-100">{selectedProject.connectionCount || connections?.length || 0}</div>
                  <div className="text-xs text-slate-400">Connections</div>
                </div>
              </CardContent>
            </Card>
            <Card className="border-slate-700 bg-slate-800/80">
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <Zap className="h-5 w-5 text-emerald-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-slate-100">
                    {devices ? devices.reduce((sum: number, d: Device) => sum + (d.load || 0), 0).toFixed(1) : '0'}
                  </div>
                  <div className="text-xs text-slate-400">Total Load (A)</div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Device List */}
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-lg text-slate-100">Devices</CardTitle>
                  <CardDescription className="text-slate-400">
                    {devicesLoading ? 'Loading...' : `${devices?.length || 0} devices`}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-600 text-slate-300"
                    onClick={() => refetchDevices()}
                  >
                    <RefreshCw className="h-3 w-3 mr-1" /> Refresh
                  </Button>
                  <Button
                    size="sm"
                    className="bg-red-600 hover:bg-red-700 text-white border-none"
                    onClick={() => {
                      setDeviceForm(getDefaultDeviceForm());
                      setDeviceError(null);
                      setShowDeviceModal(true);
                    }}
                  >
                    <Plus className="h-4 w-4 mr-1" /> Add Device
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {devicesLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Activity className="h-5 w-5 text-slate-400 animate-pulse" />
                  <span className="ml-2 text-slate-400">Loading devices...</span>
                </div>
              ) : !devices || devices.length === 0 ? (
                <div className="text-center py-8 text-slate-400">
                  <Cpu className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No devices in this project yet</p>
                  <Button
                    size="sm"
                    className="mt-3 bg-red-600 hover:bg-red-700 text-white border-none"
                    onClick={() => {
                      setDeviceForm(getDefaultDeviceForm());
                      setDeviceError(null);
                      setShowDeviceModal(true);
                    }}
                  >
                    <Plus className="h-4 w-4 mr-1" /> Add First Device
                  </Button>
                </div>
              ) : (
                <ScrollArea className="max-h-96">
                  <div className="space-y-2">
                    {devices.map((device: Device) => (
                      <div
                        key={device.id}
                        className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-700/50"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-7 h-7 rounded bg-blue-500/10 flex items-center justify-center">
                            <Cpu className="h-3.5 w-3.5 text-blue-400" />
                          </div>
                          <div>
                            <div className="text-sm font-medium text-slate-200">{device.name}</div>
                            <div className="text-xs text-slate-400">{device.type} • {device.category}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-slate-400">
                          <span>{device.voltage}V</span>
                          <span>{device.current}A</span>
                          <span>{device.load}A</span>  {/* Load stored in A after conversion */}
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          {/* Connections */}
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-lg text-slate-100">Connections</CardTitle>
                  <CardDescription className="text-slate-400">
                    {connectionsLoading ? 'Loading...' : `${connections?.length || 0} connections`}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-600 text-slate-300"
                    onClick={() => refetchConnections()}
                  >
                    <RefreshCw className="h-3 w-3 mr-1" /> Refresh
                  </Button>
                  <Button
                    size="sm"
                    className="bg-red-600 hover:bg-red-700 text-white border-none"
                    onClick={() => {
                      setConnForm(getDefaultConnectionForm());
                      setConnectionError(null);
                      setShowConnectionModal(true);
                    }}
                    disabled={!devices || devices.length < 2}
                  >
                    <Plus className="h-4 w-4 mr-1" /> Add Connection
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {connectionsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Activity className="h-5 w-5 text-slate-400 animate-pulse" />
                  <span className="ml-2 text-slate-400">Loading connections...</span>
                </div>
              ) : !connections || connections.length === 0 ? (
                <div className="text-center py-8 text-slate-400">
                  <Cable className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">
                    {!devices || devices.length < 2
                      ? 'Add at least 2 devices to create connections'
                      : 'No connections in this project yet'}
                  </p>
                </div>
              ) : (
                <ScrollArea className="max-h-60">
                  <div className="space-y-2">
                    {connections.map((conn) => {
                      const fromDevice = devices?.find((d: Device) => d.id === conn.fromId);
                      const toDevice = devices?.find((d: Device) => d.id === conn.toId);
                      return (
                        <div
                          key={conn.id}
                          className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-700/50"
                        >
                          <div className="flex items-center gap-2 text-sm text-slate-200">
                            <LinkIcon className="h-3.5 w-3.5 text-amber-400" />
                            <span className="text-slate-300">{fromDevice?.name || conn.fromId.slice(0, 8)}</span>
                            <span className="text-slate-500">→</span>
                            <span className="text-slate-300">{toDevice?.name || conn.toId.slice(0, 8)}</span>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-slate-400">
                            {conn.cableSize && <span>{conn.cableSize}</span>}
                            {conn.length > 0 && <span>{conn.length}m</span>}
                            {conn.type && (
                              <Badge variant="outline" className="text-[9px] border-slate-600 text-slate-400 py-0">
                                {conn.type}
                              </Badge>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ===== Device Creation Dialog ===== */}
        <Dialog open={showDeviceModal} onOpenChange={setShowDeviceModal}>
          <DialogContent className="bg-slate-800 border-slate-700 text-slate-100 max-w-lg max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-slate-100">Add Device</DialogTitle>
              <DialogDescription className="text-slate-400">
                Add a new device to {selectedProject.name}
              </DialogDescription>
            </DialogHeader>

            {deviceError && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                <p className="text-sm text-red-400">{deviceError}</p>
              </div>
            )}

            <div className="space-y-4 py-2">
              {/* Category */}
              <div className="space-y-2">
                <Label className="text-slate-300 text-xs">Category *</Label>
                <Select value={deviceForm.category} onValueChange={handleCategoryChange}>
                  <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    {DEVICE_CATEGORIES.map((cat) => (
                      <SelectItem key={cat.id} value={cat.id}>
                        {cat.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Type (based on category) */}
              <div className="space-y-2">
                <Label className="text-slate-300 text-xs">Device Type *</Label>
                <Select value={deviceForm.type} onValueChange={handleDeviceTypeChange}>
                  <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    {categoryDevices.map((spec: DeviceSpec) => (
                      <SelectItem key={spec.id} value={spec.id}>
                        {spec.name} ({spec.symbol})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Name */}
              <div className="space-y-2">
                <Label className="text-slate-300 text-xs">Device Name *</Label>
                <Input
                  placeholder="e.g., SD-2-08"
                  value={deviceForm.name}
                  onChange={(e) => setDeviceForm(prev => ({ ...prev, name: e.target.value }))}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                />
              </div>

              {/* Position */}
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-2">
                  <Label className="text-slate-300 text-xs">X *</Label>
                  <Input
                    type="number"
                    value={deviceForm.x}
                    onChange={(e) => setDeviceForm(prev => ({ ...prev, x: parseFloat(e.target.value) || 0 }))}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-xs">Y *</Label>
                  <Input
                    type="number"
                    value={deviceForm.y}
                    onChange={(e) => setDeviceForm(prev => ({ ...prev, y: parseFloat(e.target.value) || 0 }))}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-xs">Z</Label>
                  <Input
                    type="number"
                    value={deviceForm.z}
                    onChange={(e) => setDeviceForm(prev => ({ ...prev, z: parseFloat(e.target.value) || 0 }))}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                  />
                </div>
              </div>

              {/* Electrical */}
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-2">
                  <Label className="text-slate-300 text-xs">Voltage (V)</Label>
                  <Input
                    type="number"
                    value={deviceForm.voltage}
                    onChange={(e) => setDeviceForm(prev => ({ ...prev, voltage: parseFloat(e.target.value) || 0 }))}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-xs">Current (A)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={deviceForm.current}
                    onChange={(e) => setDeviceForm(prev => ({ ...prev, current: parseFloat(e.target.value) || 0 }))}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-xs">Load</Label>
                  <Input
                    type="number"
                    step="0.1"
                    value={deviceForm.load}
                    onChange={(e) => setDeviceForm(prev => ({ ...prev, load: parseFloat(e.target.value) || 0 }))}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                  />
                </div>
              </div>
              {/* Load Unit Selector — BUG-30 FIX */}
              <div className="space-y-2">
                <Label className="text-slate-300 text-xs">Load Unit</Label>
                <Select value={deviceForm.loadUnit} onValueChange={(v) => setDeviceForm(prev => ({ ...prev, loadUnit: v as 'A' | 'mA' | 'W' }))}>
                  <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    <SelectItem value="A">Amperes (A)</SelectItem>
                    <SelectItem value="mA">Milliamperes (mA)</SelectItem>
                    <SelectItem value="W">Watts (W)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <DialogFooter className="gap-2">
              <Button
                variant="outline"
                className="border-slate-600 text-slate-300"
                onClick={() => setShowDeviceModal(false)}
              >
                Cancel
              </Button>
              <Button
                className="bg-red-600 hover:bg-red-700 text-white border-none"
                onClick={handleCreateDevice}
                disabled={creatingDevice || !deviceForm.name.trim() || !deviceForm.type}
              >
                {creatingDevice ? 'Creating...' : 'Create Device'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* ===== Connection Creation Dialog ===== */}
        <Dialog open={showConnectionModal} onOpenChange={setShowConnectionModal}>
          <DialogContent className="bg-slate-800 border-slate-700 text-slate-100 max-w-lg">
            <DialogHeader>
              <DialogTitle className="text-slate-100">Add Connection</DialogTitle>
              <DialogDescription className="text-slate-400">
                Connect two devices in {selectedProject.name}
              </DialogDescription>
            </DialogHeader>

            {connectionError && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                <p className="text-sm text-red-400">{connectionError}</p>
              </div>
            )}

            <div className="space-y-4 py-2">
              {/* From Device */}
              <div className="space-y-2">
                <Label className="text-slate-300 text-xs">From Device *</Label>
                <Select value={connForm.fromDeviceId} onValueChange={(v) => setConnForm(prev => ({ ...prev, fromDeviceId: v }))}>
                  <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                    <SelectValue placeholder="Select source device" />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    {devices?.map((d: Device) => (
                      <SelectItem key={d.id} value={d.id} disabled={d.id === connForm.toDeviceId}>
                        {d.name} ({d.type})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* To Device */}
              <div className="space-y-2">
                <Label className="text-slate-300 text-xs">To Device *</Label>
                <Select value={connForm.toDeviceId} onValueChange={(v) => setConnForm(prev => ({ ...prev, toDeviceId: v }))}>
                  <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                    <SelectValue placeholder="Select target device" />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    {devices?.map((d: Device) => (
                      <SelectItem key={d.id} value={d.id} disabled={d.id === connForm.fromDeviceId}>
                        {d.name} ({d.type})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Connection Details */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label className="text-slate-300 text-xs">Connection Type</Label>
                  <Select value={connForm.type} onValueChange={(v) => setConnForm(prev => ({ ...prev, type: v }))}>
                    <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-800 border-slate-700">
                      {CONNECTION_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300 text-xs">Cable Size</Label>
                  <Select value={connForm.cableSize} onValueChange={(v) => setConnForm(prev => ({ ...prev, cableSize: v }))}>
                    <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                      <SelectValue placeholder="Select size" />
                    </SelectTrigger>
                    <SelectContent className="bg-slate-800 border-slate-700">
                      {CABLE_SIZES.map((s) => (
                        <SelectItem key={s} value={s}>
                          {s}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-xs">Cable Length (m)</Label>
                <Input
                  type="number"
                  placeholder="e.g., 25"
                  value={connForm.length || ''}
                  onChange={(e) => setConnForm(prev => ({ ...prev, length: parseFloat(e.target.value) || 0 }))}
                  className="bg-slate-900 border-slate-600 text-slate-100"
                />
              </div>
            </div>

            <DialogFooter className="gap-2">
              <Button
                variant="outline"
                className="border-slate-600 text-slate-300"
                onClick={() => setShowConnectionModal(false)}
              >
                Cancel
              </Button>
              <Button
                className="bg-red-600 hover:bg-red-700 text-white border-none"
                onClick={handleCreateConnection}
                disabled={creatingConnection || !connForm.fromDeviceId || !connForm.toDeviceId}
              >
                {creatingConnection ? 'Creating...' : 'Create Connection'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Projects list view
  // ---------------------------------------------------------------------------

  return (
    <div className="flex-1 overflow-auto" aria-label={t('projects.title')}>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">{t('projects.title')}</h1>
            <p className="text-sm text-slate-400 mt-1">{t('projects.subtitle')}</p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              className="border-slate-600 text-slate-300 hover:bg-slate-800"
              onClick={() => refetchProjects()}
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

        {/* Error banner */}
        {projectsError && (
          <Card className="border-red-500/30 bg-red-500/5">
            <CardContent className="p-3">
              <p className="text-sm text-red-400">Error loading projects: {projectsError}</p>
            </CardContent>
          </Card>
        )}

        {createError && (
          <Card className="border-red-500/30 bg-red-500/5">
            <CardContent className="p-3">
              <p className="text-sm text-red-400">Error creating project: {createError}</p>
            </CardContent>
          </Card>
        )}

        {/* Create Project Form */}
        {showCreateForm && (
          <Card className="border-slate-700 bg-slate-800/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg text-slate-100">Create New Project</CardTitle>
              <CardDescription className="text-slate-400">Add a new digital twin project</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-slate-300">Project Name *</Label>
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
                    placeholder="Brief description"
                    value={newProjectDesc}
                    onChange={(e) => setNewProjectDesc(e.target.value)}
                    className="bg-slate-900 border-slate-600 text-slate-100"
                  />
                </div>
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
                  onClick={() => { setShowCreateForm(false); setNewProjectName(''); setNewProjectDesc(''); }}
                >
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Projects Grid */}
        {projectsLoading ? (
          <div className="flex items-center justify-center py-16">
            <Activity className="h-8 w-8 text-slate-400 animate-pulse" />
            <span className="ml-3 text-slate-400">Loading projects...</span>
          </div>
        ) : !projects || projects.length === 0 ? (
          <Card className="border-slate-700 bg-slate-800/80">
            <CardContent className="py-16 text-center">
              <FolderKanban className="h-12 w-12 mx-auto mb-3 text-slate-500" />
              <h3 className="text-lg font-medium text-slate-300 mb-1">No Projects Yet</h3>
              <p className="text-sm text-slate-400 mb-4">Create your first digital twin project to get started.</p>
              <Button
                className="bg-red-600 hover:bg-red-700 text-white border-none"
                onClick={() => setShowCreateForm(true)}
              >
                <Plus className="h-4 w-4 mr-1" /> Create First Project
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((project: Project) => (
              <Card
                key={project.id}
                className="border-slate-700 bg-slate-800/80 hover:border-slate-600 transition-colors cursor-pointer group"
                onClick={() => setSelectedProjectId(project.id)}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <Badge
                      variant={project.status === 'active' ? 'default' : 'secondary'}
                      className={
                        project.status === 'active'
                          ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/30 text-[10px]'
                          : project.status === 'draft'
                          ? 'bg-yellow-600/20 text-yellow-400 border-yellow-500/30 text-[10px]'
                          : 'bg-slate-600/20 text-slate-400 border-slate-500/30 text-[10px]'
                      }
                    >
                      {project.status}
                    </Badge>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                        onClick={(e) => { e.stopPropagation(); setDeleteConfirm({ id: project.id, name: project.name }); }}
                        disabled={deleting}
                        aria-label={t('projects.deleteProject')}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                  <CardTitle className="text-base text-slate-200 group-hover:text-slate-100 flex items-center justify-between">
                    {project.name}
                    <ChevronRight className="h-4 w-4 text-slate-500 group-hover:text-slate-300 transition-colors" />
                  </CardTitle>
                  <CardDescription className="text-xs text-slate-400 line-clamp-2">
                    {project.description || 'No description'}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0">
                  <Separator className="mb-3 bg-slate-700" />
                  <div className="flex items-center gap-4 text-xs text-slate-400">
                    <span className="flex items-center gap-1">
                      <Cpu className="h-3 w-3" /> {project.deviceCount || 0} devices
                    </span>
                    <span className="flex items-center gap-1">
                      <Cable className="h-3 w-3" /> {project.connectionCount || 0} connections
                    </span>
                  </div>
                  {project.author && (
                    <div className="text-xs text-slate-500 mt-2">
                      By {project.author} • {new Date(project.createdAt).toLocaleDateString()}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Accessible Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm !== null}
        title={t('projects.deleteConfirmTitle')}
        message={t('projects.deleteConfirmMessage', { name: deleteConfirm?.name || 'this project' })}
        confirmLabel={t('common.delete')}
        cancelLabel={t('common.cancel')}
        onConfirm={() => deleteConfirm && handleDeleteProject(deleteConfirm.id)}
        onCancel={() => setDeleteConfirm(null)}
        variant="danger"
      />
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
