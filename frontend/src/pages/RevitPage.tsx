// NOSONAR
/**
 * RevitPage.tsx — Revit Dashboard
 */

import {
        Activity,
        FileText,
        Loader2,
        Power,
        PowerOff,
        Wifi,
        WifiOff,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileUploader } from "@/components/shared/FileUploader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
        Card,
        CardContent,
        CardDescription,
        CardHeader,
        CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { revitService } from "@/services/revitService";

export function RevitPage() {
        const [connected, setConnected] = useState(false);
        const [connecting, setConnecting] = useState(false);
        const [status, setStatus] = useState<Record<string, unknown> | null>(null);
        const [visible, setVisible] = useState(true);
        const [filepath, setFilepath] = useState("");

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

        useEffect(() => {
                checkStatus();
        }, [checkStatus]);

        const handleConnect = async () => {
                setConnecting(true);
                try {
                        await revitService.connect("auto");
                        toast.success("Connected to Revit");
                        setConnected(true);
                        checkStatus();
                } catch (err) {
                        toast.error(
                                `Connection failed: ${err instanceof Error ? err.message : "Unknown error"}`,
                        );
                } finally {
                        setConnecting(false);
                }
        };

        const handleDisconnect = async () => {
                try {
                        await revitService.disconnect();
                        toast.success("Disconnected");
                        setConnected(false);
                        setStatus(null);
                } catch (err) {
                        toast.error(
                                `Failed: ${err instanceof Error ? err.message : "Unknown error"}`,
                        );
                }
        };

        const handleReadRvt = async () => {
                if (!filepath.trim()) {
                        toast.error("Enter file path");
                        return;
                }
                try {
                        await revitService.readRvt(filepath);
                        toast.success(`Read ${filepath}`);
                } catch (err) {
                        toast.error(
                                `Read failed: ${err instanceof Error ? err.message : "Unknown error"}`,
                        );
                }
        };

        const handleUpload = async (file: File) => {
                await revitService.uploadRvt(file);
                toast.success(`Uploaded ${file.name}`);
        };

        return (
                <div className="flex-1 overflow-auto p-6 max-w-6xl mx-auto space-y-6">
                        <div className="flex items-center justify-between">
                                <div>
                                        <h1 className="text-2xl font-bold text-foreground">Revit Dashboard</h1>
                                        <p className="text-sm text-muted-foreground mt-1">
                                                Connect, read, and manage RVT files
                                        </p>
                                </div>
                                <Badge
                                        variant={connected ? "default" : "outline"}
                                        className={
                                                connected ? "bg-emerald-600" : "border-border text-muted-foreground"
                                        }
                                >
                                        {connected ? (
                                                <>
                                                        <Wifi className="h-3 w-3 mr-1" /> Connected
                                                </>
                                        ) : (
                                                <>
                                                        <WifiOff className="h-3 w-3 mr-1" /> Disconnected
                                                </>
                                        )}
                                </Badge>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <Card className="border-border bg-card">
                                        <CardHeader>
                                                <CardTitle className="flex items-center gap-2 text-foreground">
                                                        <Power className="h-5 w-5 text-primary" /> Connection
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        Connect to Revit instance
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                                <div className="flex items-center gap-3">
                                                        <Switch
                                                                checked={visible}
                                                                onCheckedChange={setVisible}
                                                                id="revit-visible"
                                                        />
                                                        <Label htmlFor="revit-visible" className="text-foreground/90">
                                                                Visible window
                                                        </Label>
                                                </div>
                                                <div className="flex gap-2">
                                                        <Button
                                                                onClick={handleConnect}
                                                                disabled={connecting || connected}
                                                                className="bg-emerald-600 hover:bg-emerald-700 text-white"
                                                        >
                                                                {connecting ? (
                                                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                                                ) : (
                                                                        <Power className="h-4 w-4 mr-2" />
                                                                )}
                                                                Connect
                                                        </Button>
                                                        <Button
                                                                onClick={handleDisconnect}
                                                                disabled={!connected}
                                                                variant="destructive"
                                                        >
                                                                <PowerOff className="h-4 w-4 mr-2" /> Disconnect
                                                        </Button>
                                                </div>
                                        </CardContent>
                                </Card>

                                <Card className="border-border bg-card">
                                        <CardHeader>
                                                <CardTitle className="flex items-center gap-2 text-foreground">
                                                        <Activity className="h-5 w-5 text-primary" /> Status
                                                </CardTitle>
                                                <CardDescription className="text-muted-foreground">
                                                        Current Revit status
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                {status ? (
                                                        <pre className="text-xs text-muted-foreground bg-card p-3 rounded overflow-auto max-h-48">
                                                                {JSON.stringify(status, null, 2)}
                                                        </pre>
                                                ) : (
                                                        <p className="text-muted-foreground text-sm">Not connected</p>
                                                )}
                                        </CardContent>
                                </Card>
                        </div>

                        <Card className="border-border bg-card">
                                <CardHeader>
                                        <CardTitle className="flex items-center gap-2 text-foreground">
                                                <FileText className="h-5 w-5 text-primary" /> Read RVT File
                                        </CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                        <div className="flex gap-2">
                                                <Input
                                                        placeholder="/path/to/file.rvt"
                                                        value={filepath}
                                                        onChange={(e) => setFilepath(e.target.value)}
                                                        className="bg-card border-border text-foreground"
                                                />
                                                <Button
                                                        onClick={handleReadRvt}
                                                        disabled={!connected}
                                                        className="bg-primary hover:bg-orange-700 text-white"
                                                >
                                                        Read
                                                </Button>
                                        </div>
                                        <div className="pt-2">
                                                <FileUploader
                                                        accept=".rvt"
                                                        label="Or upload an RVT file"
                                                        onUpload={handleUpload}
                                                />
                                        </div>
                                </CardContent>
                        </Card>
                </div>
        );
}
