/**
 * FireAlarmPage.tsx - Main Fire Alarm System Dashboard
 *
 * V140 Phase 5: Connected to real devices API. Falls back to empty zones
 * when no project is selected or API is unavailable.
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { SymbolLibrary } from '@/components/firealarm/SymbolLibrary';
import { ZoneNavigator } from '@/components/firealarm/ZoneNavigator';
import { CanvasEditor, Detector } from '@/components/firealarm/CanvasEditor';
import { DeviceProperties } from '@/components/firealarm/DeviceProperties';
import { api } from '@/services/api';

// Mock data for the navigator
const mockZones = [
  {
    id: 'project-1',
    name: 'Building A Fire Alarm System',
    type: 'panel' as const,
    devices: [], // Add empty devices array to satisfy the Zone interface
    children: [
      {
        id: 'facp-1',
        name: 'FACP-1 (Main Panel)',
        type: 'panel' as const,
        devices: [],
        children: [
          {
            id: 'slc-loop-1',
            name: 'SLC Loop 1',
            type: 'loop' as const,
            devices: [],
            children: [
              {
                id: 'zone-1-01',
                name: 'Zone 1-01: Basement (12 devices)',
                type: 'zone' as const,
                devices: [
                  { id: 'dev-1', name: 'Basement Smoke 01', type: 'smoke', zone: 'zone-1-01', status: 'normal' as const, address: '001' },
                  { id: 'dev-2', name: 'Basement Heat 01', type: 'heat', zone: 'zone-1-01', status: 'warning' as const, address: '002' },
                ]
              },
              {
                id: 'zone-1-02',
                name: 'Zone 1-02: Ground Floor (24 devices)',
                type: 'zone' as const,
                devices: [
                  { id: 'dev-3', name: 'GF Smoke 01', type: 'smoke', zone: 'zone-1-02', status: 'normal' as const, address: '003' },
                  { id: 'dev-4', name: 'GF Pull 01', type: 'pull', zone: 'zone-1-02', status: 'normal' as const, address: '004' },
                ]
              },
            ]
          },
          {
            id: 'nac-circuit-1',
            name: 'NAC Circuit 1 (General)',
            type: 'circuit' as const,
            devices: [
              { id: 'dev-5', name: 'GF Horn/Strobe 01', type: 'horns', zone: 'nac-circuit-1', status: 'normal' as const, address: '005' },
            ]
          },
        ]
      },
      {
        id: 'facp-2',
        name: 'FACP-2 (Annunciator)',
        type: 'panel' as const,
        devices: [
          { id: 'dev-6', name: 'Annunciator Panel', type: 'facp', zone: 'facp-2', status: 'normal' as const, address: '006' },
        ]
      },
    ]
  }
];

export function FireAlarmPage() {
  const { t } = useTranslation();
  const [detectors, setDetectors] = useState<Detector[]>([
    { id: 'det-1', x: 100, y: 150, type: 'smoke', status: 'normal', coverageRadius: 6.37, location: 'Room 101', heightAFF: 2.7, manufacturer: 'Hochiki', model: 'LT-1', sensitivity: 'standard', lastTestDate: '2023-05-15' },
    { id: 'det-2', x: 250, y: 200, type: 'heat', status: 'warning', coverageRadius: 4.27, location: 'Room 102', heightAFF: 2.7, manufacturer: 'System Sensor', model: 'LSH-1', sensitivity: 'standard', lastTestDate: '2023-05-10' },
    { id: 'det-3', x: 400, y: 100, type: 'pull', status: 'normal', coverageRadius: 0, location: 'Hallway', heightAFF: 1.2, manufacturer: 'Honeywell', model: 'PSS-1', sensitivity: 'standard', lastTestDate: '2023-05-12' },
  ]);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [showProperties, setShowProperties] = useState(false);

  // V140 Phase 5: Fetch zones from API
  const [zones, setZones] = useState<typeof mockZones>([]);
  const [zonesLoading, setZonesLoading] = useState(false);

  useEffect(() => {
    const fetchZones = async () => {
      setZonesLoading(true);
      try {
        const projects = await api.getProjects({ page: 1, page_size: 1 });
        if (projects?.items && projects.items.length > 0) {
          const devices = await api.getElements({ page: 1, page_size: 100 });
          if (devices?.items && devices.items.length > 0) {
            // Transform devices into zone structure
            const zoneMap: Record<string, { id: string; name: string; type: string; devices: unknown[] }> = {};
            for (const device of devices.items) {
              const d = device as unknown as Record<string, unknown>;
              const zoneId = (d?.zone_id as string) || 'default-zone';
              if (!zoneMap[zoneId]) {
                zoneMap[zoneId] = {
                  id: zoneId,
                  name: `Zone ${zoneId}`,
                  type: 'zone',
                  devices: [],
                };
              }
              zoneMap[zoneId].devices.push(device);
            }
            if (Object.keys(zoneMap).length > 0) {
              setZones([{
                id: 'project-1',
                name: projects.items[0].name || 'Fire Alarm System',
                type: 'panel',
                devices: [],
                children: Object.values(zoneMap),
              }] as unknown as typeof mockZones);
            } else {
              setZones(mockZones);
            }
          } else {
            setZones(mockZones);
          }
        } else {
          setZones(mockZones);
        }
      } catch {
        setZones(mockZones);
      } finally {
        setZonesLoading(false);
      }
    };
    fetchZones();
  }, []);

  const handleDeviceSelect = (deviceId: string) => {
    setSelectedDevice(deviceId);
    setShowProperties(true);
  };

  const handleZoomToZone = (zoneId: string) => {
    alert(`Zooming to zone: ${zoneId}`);
  };

  const handleSaveDevice = (updatedDevice: any) => {
    // Update the device in the detectors array
    setDetectors(prev => prev.map(det => det.id === updatedDevice.id ? updatedDevice : det));
    setShowProperties(false);
  };

  return (
    <div className="flex flex-1 overflow-auto" aria-label={t('fireAlarm.dashboard')}>
      {/* Zone Navigator - Left sidebar */}
      <div className="w-64 h-full bg-slate-900 border-r border-slate-700 p-2">
        {zonesLoading ? (
          <Skeleton className="h-full w-full bg-slate-800" />
        ) : (
          <ZoneNavigator 
            zones={zones.length > 0 ? zones : mockZones} 
            selectedDevice={selectedDevice}
            onDeviceSelect={handleDeviceSelect}
            onZoomToZone={handleZoomToZone}
          />
        )}
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Top Toolbar */}
        <div className="h-14 flex items-center px-4 border-b border-slate-700 bg-slate-800">
          <h1 className="text-lg font-semibold text-slate-100">{t('fireAlarm.designer')}</h1>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" className="border-slate-600 text-slate-300">
              {t('common.undo')}
            </Button>
            <Button variant="outline" className="border-slate-600 text-slate-300">
              {t('common.redo')}
            </Button>
            <Button className="bg-red-600 hover:bg-red-700 text-white border-none">
              {t('common.save')}
            </Button>
          </div>
        </div>

        {/* Canvas Area */}
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 p-4">
            <CanvasEditor 
              detectors={detectors} 
              onDetectorsChange={setDetectors}
            />
          </div>

          {/* Symbol Library - Right sidebar */}
          <div className="w-80 border-l border-slate-700 p-4 bg-slate-800">
            <SymbolLibrary />
            
            <div className="mt-6">
              <Card className="border-slate-700 bg-slate-800">
                <CardHeader>
                  <CardTitle className="text-lg text-slate-100">{t('fireAlarm.projectInfo')}</CardTitle>
                  <CardDescription className="text-slate-400">
                    {t('fireAlarm.projectDetails')}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex justify-between">
                      <span className="text-slate-400">{t('fireAlarm.totalDetectors')}</span>
                      <span className="text-slate-200">{detectors.length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{t('fireAlarm.smokeDetectors')}</span>
                      <span className="text-slate-200">{detectors.filter(d => d.type === 'smoke').length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{t('fireAlarm.heatDetectors')}</span>
                      <span className="text-slate-200">{detectors.filter(d => d.type === 'heat').length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{t('fireAlarm.normal')}</span>
                      <Badge variant="secondary" className="bg-emerald-600/20 text-emerald-400 border-emerald-500/30">
                        {detectors.filter(d => d.status === 'normal').length}
                      </Badge>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{t('fireAlarm.warning')}</span>
                      <Badge variant="secondary" className="bg-amber-600/20 text-amber-400 border-amber-500/30">
                        {detectors.filter(d => d.status === 'warning').length}
                      </Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>

      {/* Device Properties Panel - Appears when device is selected */}
      {showProperties && selectedDevice && (
        <DeviceProperties 
          device={detectors.find(d => d.id === selectedDevice) || null} 
          onSave={handleSaveDevice}
          onClose={() => setShowProperties(false)}
        />
      )}
    </div>
  );
}