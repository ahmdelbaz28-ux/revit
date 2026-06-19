/**
 * CADSettingsPage.tsx — AutoCAD & Revit Connection Configuration
 * 
 * Provides UI for:
 * - AutoCAD connection parameters (path, version, template)
 * - Revit connection parameters (path, version, template)
 * - Connection status monitoring
 * - File import/export preferences
 */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { 
  Settings, 
  CheckCircle2, 
  XCircle, 
  Loader2, 
  FolderOpen, 
  RefreshCw,
  AlertCircle,
  Monitor,
  FileText,
  Wrench,
} from 'lucide-react';
import { toast } from 'sonner';

interface CADConnectionStatus {
  connected: boolean;
  version?: string;
  document?: string;
  lastChecked: string;
}

interface RevitConnectionStatus {
  connected: boolean;
  version?: string;
  document?: string;
  lastChecked: string;
}

export function CADSettingsPage() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('autocad');
  
  // AutoCAD settings
  const [acadPath, setAcadPath] = useState('');
  const [acadVersion, setAcadVersion] = useState('2024');
  const [acadTemplate, setAcadTemplate] = useState('');
  const [acadUnits, setAcadUnits] = useState('Millimeters');
  const [acadStatus, setAcadStatus] = useState<CADConnectionStatus | null>(null);
  const [checkingAcad, setCheckingAcad] = useState(false);
  
  // Revit settings
  const [revitPath, setRevitPath] = useState('');
  const [revitVersion, setRevitVersion] = useState('2024');
  const [revitTemplate, setRevitTemplate] = useState('');
  const [revitUnits, setRevitUnits] = useState('Millimeters');
  const [revitStatus, setRevitStatus] = useState<RevitConnectionStatus | null>(null);
  const [checkingRevit, setCheckingRevit] = useState(false);
  
  // Load saved settings on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem('cad_settings');
      if (saved) {
        const settings = JSON.parse(saved);
        if (settings.autocad) {
          setAcadPath(settings.autocad.path || '');
          setAcadVersion(settings.autocad.version || '2024');
          setAcadTemplate(settings.autocad.template || '');
          setAcadUnits(settings.autocad.units || 'Millimeters');
        }
        if (settings.revit) {
          setRevitPath(settings.revit.path || '');
          setRevitVersion(settings.revit.version || '2024');
          setRevitTemplate(settings.revit.template || '');
          setRevitUnits(settings.revit.units || 'Millimeters');
        }
      }
    } catch {
      // Ignore parse errors
    }
  }, []);

  const checkAutoCADConnection = async () => {
    setCheckingAcad(true);
    try {
      // TODO: Implement actual API call to check AutoCAD connection
      // const response = await api.checkAutoCADConnection();
      // setAcadStatus(response);
      
      // Mock response for now
      await new Promise(resolve => setTimeout(resolve, 1000));
      setAcadStatus({
        connected: true,
        version: 'AutoCAD 2024',
        document: 'Drawing1.dwg',
        lastChecked: new Date().toISOString(),
      });
      toast.success('AutoCAD connection verified');
    } catch (error) {
      setAcadStatus({
        connected: false,
        lastChecked: new Date().toISOString(),
      });
      toast.error('AutoCAD connection failed');
    } finally {
      setCheckingAcad(false);
    }
  };

  const checkRevitConnection = async () => {
    setCheckingRevit(true);
    try {
      // TODO: Implement actual API call to check Revit connection
      // const response = await api.checkRevitConnection();
      // setRevitStatus(response);
      
      // Mock response for now
      await new Promise(resolve => setTimeout(resolve, 1000));
      setRevitStatus({
        connected: true,
        version: 'Revit 2024',
        document: 'Project1.rvt',
        lastChecked: new Date().toISOString(),
      });
      toast.success('Revit connection verified');
    } catch (error) {
      setRevitStatus({
        connected: false,
        lastChecked: new Date().toISOString(),
      });
      toast.error('Revit connection failed');
    } finally {
      setCheckingRevit(false);
    }
  };

  const saveAutoCADSettings = () => {
    try {
      const saved = localStorage.getItem('cad_settings');
      const settings = saved ? JSON.parse(saved) : {};
      settings.autocad = {
        path: acadPath,
        version: acadVersion,
        template: acadTemplate,
        units: acadUnits,
      };
      localStorage.setItem('cad_settings', JSON.stringify(settings));
      toast.success('AutoCAD settings saved');
    } catch (error) {
      toast.error('Failed to save settings');
    }
  };

  const saveRevitSettings = () => {
    try {
      const saved = localStorage.getItem('cad_settings');
      const settings = saved ? JSON.parse(saved) : {};
      settings.revit = {
        path: revitPath,
        version: revitVersion,
        template: revitTemplate,
        units: revitUnits,
      };
      localStorage.setItem('cad_settings', JSON.stringify(settings));
      toast.success('Revit settings saved');
    } catch (error) {
      toast.error('Failed to save settings');
    }
  };

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-100">CAD/BIM Connection Settings</h1>
          <p className="text-sm text-slate-400 mt-1">
            Configure AutoCAD and Revit connections for file operations
          </p>
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-slate-800 border border-slate-700">
            <TabsTrigger value="autocad" className="data-[state=active]:bg-slate-700">
              <Monitor className="h-4 w-4 mr-2" />
              AutoCAD
            </TabsTrigger>
            <TabsTrigger value="revit" className="data-[state=active]:bg-slate-700">
              <FileText className="h-4 w-4 mr-2" />
              Revit
            </TabsTrigger>
          </TabsList>

          {/* AutoCAD Tab */}
          <TabsContent value="autocad" className="space-y-6">
            {/* Connection Status */}
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader>
                <CardTitle className="text-lg text-slate-100 flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Monitor className="h-5 w-5 text-blue-400" />
                    AutoCAD Connection Status
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-600 text-slate-300 hover:bg-slate-800"
                    onClick={checkAutoCADConnection}
                    disabled={checkingAcad}
                  >
                    {checkingAcad ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCw className="h-4 w-4" />
                    )}
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {acadStatus ? (
                  <div className="flex items-center gap-4">
                    {acadStatus.connected ? (
                      <CheckCircle2 className="h-8 w-8 text-emerald-400" />
                    ) : (
                      <XCircle className="h-8 w-8 text-red-400" />
                    )}
                    <div className="flex-1">
                      <p className="text-sm font-medium text-slate-200">
                        {acadStatus.connected ? 'Connected' : 'Disconnected'}
                      </p>
                      {acadStatus.connected && (
                        <div className="text-xs text-slate-400 mt-1 space-y-1">
                          <p>Version: {acadStatus.version}</p>
                          <p>Document: {acadStatus.document}</p>
                          <p>Last checked: {new Date(acadStatus.lastChecked).toLocaleString()}</p>
                        </div>
                      )}
                    </div>
                    <Badge variant={acadStatus.connected ? 'default' : 'destructive'}>
                      {acadStatus.connected ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                ) : (
                  <div className="text-center py-6 text-slate-400">
                    <AlertCircle className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p>Connection status unknown</p>
                    <p className="text-xs mt-1">Click refresh to check</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* AutoCAD Configuration */}
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader>
                <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                  <Settings className="h-5 w-5 text-blue-400" />
                  AutoCAD Configuration
                </CardTitle>
                <CardDescription className="text-slate-400">
                  Configure AutoCAD installation and default settings
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label className="text-slate-300">Installation Path</Label>
                  <div className="flex gap-2">
                    <Input
                      value={acadPath}
                      onChange={(e) => setAcadPath(e.target.value)}
                      placeholder="C:\Program Files\Autodesk\AutoCAD 2024"
                      className="bg-slate-900 border-slate-600 text-slate-100 flex-1"
                    />
                    <Button
                      variant="outline"
                      className="border-slate-600 text-slate-300 hover:bg-slate-800"
                      onClick={() => {
                        // TODO: Implement file browser
                        toast.info('File browser not implemented yet');
                      }}
                    >
                      <FolderOpen className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-slate-400">
                    Path to AutoCAD executable (acad.exe)
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-slate-300">Version</Label>
                    <Select value={acadVersion} onValueChange={setAcadVersion}>
                      <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="2024">AutoCAD 2024</SelectItem>
                        <SelectItem value="2023">AutoCAD 2023</SelectItem>
                        <SelectItem value="2022">AutoCAD 2022</SelectItem>
                        <SelectItem value="2021">AutoCAD 2021</SelectItem>
                        <SelectItem value="2020">AutoCAD 2020</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-slate-300">Default Units</Label>
                    <Select value={acadUnits} onValueChange={setAcadUnits}>
                      <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Millimeters">Millimeters</SelectItem>
                        <SelectItem value="Meters">Meters</SelectItem>
                        <SelectItem value="Inches">Inches</SelectItem>
                        <SelectItem value="Feet">Feet</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label className="text-slate-300">Default Template</Label>
                  <div className="flex gap-2">
                    <Input
                      value={acadTemplate}
                      onChange={(e) => setAcadTemplate(e.target.value)}
                      placeholder="C:\Templates\architectural.dwt"
                      className="bg-slate-900 border-slate-600 text-slate-100 flex-1"
                    />
                    <Button
                      variant="outline"
                      className="border-slate-600 text-slate-300 hover:bg-slate-800"
                      onClick={() => {
                        toast.info('File browser not implemented yet');
                      }}
                    >
                      <FolderOpen className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-slate-400">
                    Default .dwt template file for new drawings
                  </p>
                </div>

                <Button
                  className="w-full bg-red-600 hover:bg-red-700 text-white border-none"
                  onClick={saveAutoCADSettings}
                >
                  Save AutoCAD Settings
                </Button>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Revit Tab */}
          <TabsContent value="revit" className="space-y-6">
            {/* Connection Status */}
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader>
                <CardTitle className="text-lg text-slate-100 flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <FileText className="h-5 w-5 text-blue-400" />
                    Revit Connection Status
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-600 text-slate-300 hover:bg-slate-800"
                    onClick={checkRevitConnection}
                    disabled={checkingRevit}
                  >
                    {checkingRevit ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCw className="h-4 w-4" />
                    )}
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {revitStatus ? (
                  <div className="flex items-center gap-4">
                    {revitStatus.connected ? (
                      <CheckCircle2 className="h-8 w-8 text-emerald-400" />
                    ) : (
                      <XCircle className="h-8 w-8 text-red-400" />
                    )}
                    <div className="flex-1">
                      <p className="text-sm font-medium text-slate-200">
                        {revitStatus.connected ? 'Connected' : 'Disconnected'}
                      </p>
                      {revitStatus.connected && (
                        <div className="text-xs text-slate-400 mt-1 space-y-1">
                          <p>Version: {revitStatus.version}</p>
                          <p>Document: {revitStatus.document}</p>
                          <p>Last checked: {new Date(revitStatus.lastChecked).toLocaleString()}</p>
                        </div>
                      )}
                    </div>
                    <Badge variant={revitStatus.connected ? 'default' : 'destructive'}>
                      {revitStatus.connected ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                ) : (
                  <div className="text-center py-6 text-slate-400">
                    <AlertCircle className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p>Connection status unknown</p>
                    <p className="text-xs mt-1">Click refresh to check</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Revit Configuration */}
            <Card className="border-slate-700 bg-slate-800/80">
              <CardHeader>
                <CardTitle className="text-lg text-slate-100 flex items-center gap-2">
                  <Wrench className="h-5 w-5 text-blue-400" />
                  Revit Configuration
                </CardTitle>
                <CardDescription className="text-slate-400">
                  Configure Revit installation and default settings
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label className="text-slate-300">Installation Path</Label>
                  <div className="flex gap-2">
                    <Input
                      value={revitPath}
                      onChange={(e) => setRevitPath(e.target.value)}
                      placeholder="C:\Program Files\Autodesk\Revit 2024"
                      className="bg-slate-900 border-slate-600 text-slate-100 flex-1"
                    />
                    <Button
                      variant="outline"
                      className="border-slate-600 text-slate-300 hover:bg-slate-800"
                      onClick={() => {
                        toast.info('File browser not implemented yet');
                      }}
                    >
                      <FolderOpen className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-slate-400">
                    Path to Revit executable (Revit.exe)
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-slate-300">Version</Label>
                    <Select value={revitVersion} onValueChange={setRevitVersion}>
                      <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="2024">Revit 2024</SelectItem>
                        <SelectItem value="2023">Revit 2023</SelectItem>
                        <SelectItem value="2022">Revit 2022</SelectItem>
                        <SelectItem value="2021">Revit 2021</SelectItem>
                        <SelectItem value="2020">Revit 2020</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-slate-300">Default Units</Label>
                    <Select value={revitUnits} onValueChange={setRevitUnits}>
                      <SelectTrigger className="bg-slate-900 border-slate-600 text-slate-100">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Millimeters">Millimeters</SelectItem>
                        <SelectItem value="Meters">Meters</SelectItem>
                        <SelectItem value="Inches">Inches</SelectItem>
                        <SelectItem value="Feet">Feet</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label className="text-slate-300">Default Template</Label>
                  <div className="flex gap-2">
                    <Input
                      value={revitTemplate}
                      onChange={(e) => setRevitTemplate(e.target.value)}
                      placeholder="C:\Templates\Architectural-Template.rte"
                      className="bg-slate-900 border-slate-600 text-slate-100 flex-1"
                    />
                    <Button
                      variant="outline"
                      className="border-slate-600 text-slate-300 hover:bg-slate-800"
                      onClick={() => {
                        toast.info('File browser not implemented yet');
                      }}
                    >
                      <FolderOpen className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-slate-400">
                    Default .rte template file for new projects
                  </p>
                </div>

                <Button
                  className="w-full bg-red-600 hover:bg-red-700 text-white border-none"
                  onClick={saveRevitSettings}
                >
                  Save Revit Settings
                </Button>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
