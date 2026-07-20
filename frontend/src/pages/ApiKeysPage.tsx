/**
 * ApiKeysPage.tsx — Admin API key management page.
 *
 * V214 fix: Exposes the backend /api/v1/admin/keys endpoints (NOT /api-keys).
 *   GET    /admin/keys          — List all API keys
 *   POST   /admin/keys          — Create new API key
 *   DELETE /admin/keys/{hash}   — Delete API key
 *   PUT    /admin/keys/{hash}   — Update API key
 *   GET    /admin/keys/roles    — List available roles
 */

import { Key, Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
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
import {
        Select,
        SelectContent,
        SelectItem,
        SelectTrigger,
        SelectValue,
} from "@/components/ui/select";
import { getApiKey } from "@/services/apiKey";

interface ApiKeyInfo {
        key_hash: string;
        role: string;
        description: string;
        created_at: string;
        last_used: string | null;
        prefix: string;
}

export function ApiKeysPage() {
        const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
        const [loading, setLoading] = useState(true);
        const [showCreate, setShowCreate] = useState(false);
        const [newKeyRole, setNewKeyRole] = useState("viewer");
        const [newKeyDesc, setNewKeyDesc] = useState("");
        const [creating, setCreating] = useState(false);
        const [newKeyValue, setNewKeyValue] = useState<string | null>(null);

        const fetchKeys = async () => {
                setLoading(true);
                try {
                        const apiKey = getApiKey();
                        const headers: Record<string, string> = {};
                        if (apiKey) headers["X-API-Key"] = apiKey;
                        const resp = await fetch("/api/v1/admin/keys", { headers });
                        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                        const data = await resp.json();
                        setKeys(data.keys || data.data?.keys || []);
                } catch (err) {
                        toast.error(`Failed to load API keys: ${err instanceof Error ? err.message : "Unknown"}`);
                } finally {
                        setLoading(false);
                }
        };

        useEffect(() => {
                fetchKeys();
        }, []);

        const handleCreate = async () => {
                setCreating(true);
                setNewKeyValue(null);
                try {
                        const apiKey = getApiKey();
                        const headers: Record<string, string> = { "Content-Type": "application/json" };
                        if (apiKey) headers["X-API-Key"] = apiKey;
                        const resp = await fetch("/api/v1/admin/keys", {
                                method: "POST",
                                headers,
                                body: JSON.stringify({ role: newKeyRole, description: newKeyDesc }),
                        });
                        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                        const data = await resp.json();
                        setNewKeyValue(data.key || data.data?.key);
                        toast.success("API key created — copy it now (won't be shown again)");
                        fetchKeys();
                } catch (err) {
                        toast.error(`Create failed: ${err instanceof Error ? err.message : "Unknown"}`);
                } finally {
                        setCreating(false);
                }
        };

        const handleDelete = async (keyHash: string) => {
                // V253 FIX: Replaced confirm() with a non-blocking toast confirmation.
                // The user must click the "Delete" button in the toast to confirm.
                // This avoids the blocking browser confirm() dialog which is not
                // production-quality and can't be styled.
                let confirmed = false;
                let resolveFn: ((value: void) => void) | null = null;
                let rejectFn: ((reason?: unknown) => void) | null = null;

                const onDeleteClick = () => {
                        confirmed = true;
                        const apiKey = getApiKey();
                        const headers: Record<string, string> = {};
                        if (apiKey) headers["X-API-Key"] = apiKey;
                        fetch(`/api/v1/admin/keys/${keyHash}`, {
                                method: "DELETE",
                                headers,
                        })
                                .then((resp) => {
                                        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                                        toast.success("API key deleted");
                                        if (resolveFn) resolveFn();
                                })
                                .catch((err) => {
                                        toast.error(`Failed to delete: ${err.message}`);
                                        if (rejectFn) rejectFn(err);
                                });
                };

                const onCancelClick = () => {
                        if (rejectFn) rejectFn(new Error("Cancelled"));
                };

                const deletePromise = new Promise<void>((resolve, reject) => {
                        resolveFn = resolve;
                        rejectFn = reject;
                        toast("Delete this API key? This cannot be undone.", {
                                duration: 10000,
                                action: {
                                        label: "Delete",
                                        onClick: onDeleteClick,
                                },
                                cancel: {
                                        label: "Cancel",
                                        onClick: onCancelClick,
                                },
                                onDismiss: () => {
                                        if (!confirmed && rejectFn) rejectFn(new Error("Cancelled"));
                                },
                        });
                });
                try {
                        await deletePromise;
                        fetchKeys();
                } catch {
                        // User cancelled or error — no action needed
                }
        };

        const roleColor = (role: string) => {
                if (role === "admin") return "bg-red-600";
                if (role === "engineer") return "bg-amber-500";
                if (role === "reviewer") return "bg-blue-500";
                return "bg-emerald-600";
        };

        return (
                <div className="flex-1 overflow-auto p-6 max-w-4xl mx-auto space-y-6">
                        <div>
                                <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
                                        <Key className="h-6 w-6 text-primary" />
                                        API Key Management
                                </h1>
                                <p className="text-sm text-muted-foreground mt-1">
                                        Create, view, and delete API keys for programmatic access
                                </p>
                        </div>

                        <Card className="border-border bg-card">
                                <CardHeader>
                                        <div className="flex items-center justify-between">
                                                <div>
                                                        <CardTitle>Active API Keys</CardTitle>
                                                        <CardDescription>{keys.length} key(s) registered</CardDescription>
                                                </div>
                                                <Button onClick={() => setShowCreate(!showCreate)} size="sm">
                                                        <Plus className="h-4 w-4 mr-1" /> New Key
                                                </Button>
                                        </div>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                        {showCreate && (
                                                <div className="p-4 rounded-lg border border-border space-y-3">
                                                        <h3 className="text-sm font-medium">Create New API Key</h3>
                                                        <div className="grid grid-cols-2 gap-3">
                                                                <div className="space-y-2">
                                                                        <Label>Role</Label>
                                                                        <Select value={newKeyRole} onValueChange={setNewKeyRole}>
                                                                                <SelectTrigger><SelectValue /></SelectTrigger>
                                                                                <SelectContent>
                                                                                        <SelectItem value="admin">Admin (full access)</SelectItem>
                                                                                        <SelectItem value="engineer">Engineer (read/write)</SelectItem>
                                                                                        <SelectItem value="reviewer">Reviewer (read-only)</SelectItem>
                                                                                        <SelectItem value="viewer">Viewer (minimal)</SelectItem>
                                                                                </SelectContent>
                                                                        </Select>
                                                                </div>
                                                                <div className="space-y-2">
                                                                        <Label>Description</Label>
                                                                        <Input
                                                                                value={newKeyDesc}
                                                                                onChange={(e) => setNewKeyDesc(e.target.value)}
                                                                                placeholder="e.g. CI pipeline key"
                                                                        />
                                                                </div>
                                                        </div>
                                                        <Button onClick={handleCreate} disabled={creating} size="sm">
                                                                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : "Generate Key"}
                                                        </Button>
                                                        {newKeyValue && (
                                                                <div className="p-3 rounded bg-amber-500/10 border border-amber-500/30">
                                                                        <p className="text-sm text-amber-600 font-semibold mb-1">
                                                                                ⚠️ Copy this key NOW — it won't be shown again:
                                                                        </p>
                                                                        <code className="text-xs break-all font-mono">{newKeyValue}</code>
                                                                </div>
                                                        )}
                                                </div>
                                        )}

                                        {loading ? (
                                                <div className="flex items-center justify-center py-8">
                                                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                                                </div>
                                        ) : keys.length === 0 ? (
                                                <p className="text-sm text-muted-foreground text-center py-8">
                                                        No API keys found. Click "New Key" to create one.
                                                </p>
                                        ) : (
                                                <div className="space-y-2">
                                                        {keys.map((key) => (
                                                                <div
                                                                        key={key.key_hash}
                                                                        className="flex items-center justify-between p-3 rounded-lg border border-border"
                                                                >
                                                                        <div className="space-y-1">
                                                                                <div className="flex items-center gap-2">
                                                                                        <code className="text-sm font-mono">{key.prefix}...</code>
                                                                                        <Badge className={roleColor(key.role)}>{key.role}</Badge>
                                                                                </div>
                                                                                <p className="text-xs text-muted-foreground">
                                                                                        {key.description || "No description"} · Created {new Date(key.created_at).toLocaleDateString()}
                                                                                        {key.last_used && ` · Last used ${new Date(key.last_used).toLocaleDateString()}`}
                                                                                </p>
                                                                        </div>
                                                                        <Button
                                                                                variant="ghost"
                                                                                size="sm"
                                                                                onClick={() => handleDelete(key.key_hash)}
                                                                                className="text-red-600 hover:text-red-700"
                                                                        >
                                                                                <Trash2 className="h-4 w-4" />
                                                                        </Button>
                                                                </div>
                                                        ))}
                                                </div>
                                        )}
                                </CardContent>
                        </Card>
                </div>
        );
}
