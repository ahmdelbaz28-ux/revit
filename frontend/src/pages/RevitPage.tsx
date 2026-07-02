/**
 * RevitPage.tsx — Revit Dashboard
 */
import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Power, PowerOff, Activity, FileText, Loader2, Wifi, WifiOff } from 'lucide-react';
import { revitService } from '@/services/revitService';
import { FileUploader } from '@/components/shared/FileUploader';
import { toast } from 'sonner';

export function RevitPage() {
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [visible, setVisible] = useState(true);
  const [filepath, setFilepath] = useState('');

  const checkStatus = async () => {
    try {
      const s = await revitService.getStatus();
      setStatus(s as Record<string, unknown>);
      setConnected(true);
    } catch {
      setConnected(false);
      setStatus(null);
    }
  };

  useEffect(() => { checkStatus(); }, []);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      await revitService.connect(visible);
      toast.success('Connected to Revit');
      setConnected(true);
      checkStatus();
    } catch (err) {
      toast.error(`Connection failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally { setConnecting(false); }
  };

  const handleDisconnect = async () => {
    try {
      await revitService.disconnect();
      toast.success('Disconnected');
      setConnected(false);
      setStatus(null);
    } catch (err) {
      toast.error(`Failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const handleReadRvt = async () => {
    if (!filepath.trim()) { toast.error('Enter file path'); return; }
    try {
      const result = await revitService.readRvt(filepath);
      toast.success(`Read ${filepath}`);
      console.log('RVT data:', result);
    } catch (err) {
      toast.error(`Read failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const handleUpload = async (file: File) => {
    const result = await revitService.uploadRvt(file);
    toast.success(`Uploaded ${file.name}`);
    console.log('Upload result:', result);
  };

  return (
    <div className="flex-1 overflow-auto p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Revit Dashboard</h1>
          <p className="text-sm text-slate-400 mt-1">Connect, read, and manage RVT files</p>
        </div>
        <Badge variant={connected ? 'default' : 'outline'} className={connected ? 'bg-emerald-600' : 'border-slate-600 text-slate-400'}>
          {connected ? <><Wifi className="h-3 w-3 mr-1" /> Connected</> : <><WifiOff className="h-3 w-3 mr-1" /> Disconnected</>}
        </Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="border-slate-700 bg-slate-800">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-slate-100"><Power className="h-5 w-5 text-orange-400" /> Connection</CardTitle>
            <CardDescription className="text-slate-400">Connect to Revit instance</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <Switch checked={visible} onCheckedChange={setVisible} id="revit-visible" />
              <Label htmlFor="revit-visible" className="text-slate-300">Visible window</Label>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleConnect} disabled={connecting || connected} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                {connecting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Power className="h-4 w-4 mr-2" />}
                Connect
              </Button>
              <Button onClick={handleDisconnect} disabled={!connected} variant="destructive">
                <PowerOff className="h-4 w-4 mr-2" /> Disconnect
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-700 bg-slate-800">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-slate-100"><Activity className="h-5 w-5 text-orange-400" /> Status</CardTitle>
            <CardDescription className="text-slate-400">Current Revit status</CardDescription>
          </CardHeader>
          <CardContent>
            {status ? (
              <pre className="text-xs text-slate-400 bg-slate-900 p-3 rounded overflow-auto max-h-48">{JSON.stringify(status, null, 2)}</pre>
            ) : <p className="text-slate-500 text-sm">Not connected</p>}
          </CardContent>
        </Card>
      </div>

      <Card className="border-slate-700 bg-slate-800">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-slate-100"><FileText className="h-5 w-5 text-orange-400" /> Read RVT File</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input placeholder="/path/to/file.rvt" value={filepath} onChange={(e) => setFilepath(e.target.value)} className="bg-slate-900 border-slate-700 text-slate-100" />
            <Button onClick={handleReadRvt} disabled={!connected} className="bg-orange-600 hover:bg-orange-700 text-white">Read</Button>
          </div>
          <div className="pt-2">
            <FileUploader accept=".rvt" label="Or upload an RVT file" onUpload={handleUpload} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
