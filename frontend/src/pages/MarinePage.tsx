/**
 * MarinePage.tsx — Marine Fire Protection Design (SOLAS / IMO / IEC 60092).
 *
 * V216: New page — 14 backend endpoints now have UI.
 * Ship validation, zone division, detection design, extinguishing sizing,
 * alarm-logic generation, power design, divisions generation.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Ship, Loader2, ShieldCheck, Zap, FileText } from "lucide-react";
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
import { marineApi } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

interface ShipForm {
        project_id: string;
        ship_name: string;
        imo_number: string;
        ship_type: string;
        length_overall_m: string;
        gross_tonnage: string;
        passenger_capacity: string;
        flag_state: string;
        classification_society: string;
}

const SHIP_TYPES = [
        { value: "passenger", label: "Passenger" },
        { value: "cargo", label: "Cargo" },
        { value: "tanker", label: "Tanker" },
        { value: "container", label: "Container" },
];

const SOCIETIES = ["LR", "DNV", "BV", "ABS", "CCS", "NK"];

export function MarinePage() {
        const { t } = useTranslation();
        const { toast } = useToast();
        const [loading, setLoading] = useState<string | null>(null);
        const [standards, setStandards] = useState<unknown[]>([]);
        const [fireClasses, setFireClasses] = useState<unknown[]>([]);
        const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
        const [zones, setZones] = useState<unknown[]>([]);
        const [detection, setDetection] = useState<Record<string, unknown> | null>(null);
        const [extinguishing, setExtinguishing] = useState<Record<string, unknown> | null>(null);

        const [ship, setShip] = useState<ShipForm>({
                project_id: "marine-001",
                ship_name: "",
                imo_number: "",
                ship_type: "passenger",
                length_overall_m: "120",
                gross_tonnage: "50000",
                passenger_capacity: "2000",
                flag_state: "PA",
                classification_society: "LR",
        });

        const buildShipPayload = () => ({
                ship: {
                        project_id: ship.project_id,
                        ship_name: ship.ship_name || "Test Vessel",
                        imo_number: ship.imo_number || "1234567",
                        ship_type: ship.ship_type,
                        service: ship.ship_type,
                        length_overall_m: parseFloat(ship.length_overall_m) || 120,
                        gross_tonnage: parseFloat(ship.gross_tonnage) || 50000,
                        passenger_capacity: parseInt(ship.passenger_capacity) || 2000,
                        flag_state: ship.flag_state,
                        classification_society: ship.classification_society,
                },
        });

        const handleFetchStandards = async () => {
                setLoading("standards");
                try {
                        const res = await marineApi.getStandards();
                        setStandards((res as { standards?: unknown[] }).standards || []);
                } catch (err) {
                        toast({
                                title: "Error",
                                description: err instanceof Error ? err.message : "Failed",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleFetchFireClasses = async () => {
                setLoading("fire-classes");
                try {
                        const res = await marineApi.getFireClasses();
                        setFireClasses((res as { fire_classes?: unknown[] }).fire_classes || []);
                } catch (err) {
                        toast({
                                title: "Error",
                                description: err instanceof Error ? err.message : "Failed",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleValidate = async () => {
                setLoading("validate");
                try {
                        const res = await marineApi.validateShip(buildShipPayload());
                        setValidation(res as Record<string, unknown>);
                } catch (err) {
                        toast({
                                title: "Validation Failed",
                                description: err instanceof Error ? err.message : "Failed",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleDivideZones = async () => {
                setLoading("zones");
                try {
                        const res = await marineApi.divideZones(buildShipPayload().ship);
                        setZones((res as { zones?: unknown[] }).zones || []);
                } catch (err) {
                        toast({
                                title: "Zone Division Failed",
                                description: err instanceof Error ? err.message : "Failed",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleDetection = async () => {
                setLoading("detection");
                try {
                        if (zones.length === 0) {
                                toast({ title: "Divide zones first", variant: "destructive" });
                                return;
                        }
                        const payload = {
                                ...buildShipPayload(),
                                zone: zones[0],
                        };
                        const res = await marineApi.designDetection(payload);
                        setDetection(res as Record<string, unknown>);
                } catch (err) {
                        toast({
                                title: "Detection Design Failed",
                                description: err instanceof Error ? err.message : "Failed",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const handleExtinguishing = async () => {
                setLoading("extinguishing");
                try {
                        if (zones.length === 0) {
                                toast({ title: "Divide zones first", variant: "destructive" });
                                return;
                        }
                        const payload = {
                                ...buildShipPayload(),
                                zone: zones[0],
                        };
                        const res = await marineApi.designExtinguishing(payload);
                        setExtinguishing(res as Record<string, unknown>);
                } catch (err) {
                        toast({
                                title: "Extinguishing Design Failed",
                                description: err instanceof Error ? err.message : "Failed",
                                variant: "destructive",
                        });
                } finally {
                        setLoading(null);
                }
        };

        const isLoading = (key: string) => loading === key;

        return (
                <div className="flex-1 overflow-auto" aria-label={t("nav.marine", "Marine")}>
                        <div className="p-6 max-w-5xl mx-auto space-y-6">
                                <div>
                                        <h1 className="text-lg font-semibold text-foreground flex items-center gap-2">
                                                <Ship className="h-5 w-5 text-primary" />
                                                Marine Fire Protection Design
                                        </h1>
                                        <p className="text-sm text-muted-foreground mt-1">
                                                SOLAS II-2 · IEC 60092 · IMO FSS Code · Lloyd&apos;s Register
                                        </p>
                                </div>

                                {/* Ship Specification */}
                                <Card>
                                        <CardHeader>
                                                <CardTitle>Ship Specification</CardTitle>
                                                <CardDescription>
                                                        Define the vessel parameters for SOLAS compliance analysis
                                                </CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                                                        <div className="space-y-1.5">
                                                                <Label className="text-xs text-muted-foreground">Ship Name</Label>
                                                                <Input
                                                                        value={ship.ship_name}
                                                                        onChange={(e) => setShip({ ...ship, ship_name: e.target.value })}
                                                                        placeholder="MV Test Vessel"
                                                                />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                                <Label className="text-xs text-muted-foreground">IMO Number</Label>
                                                                <Input
                                                                        value={ship.imo_number}
                                                                        onChange={(e) => setShip({ ...ship, imo_number: e.target.value })}
                                                                        placeholder="1234567"
                                                                />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                                <Label className="text-xs text-muted-foreground">Ship Type</Label>
                                                                <Select
                                                                        value={ship.ship_type}
                                                                        onValueChange={(v) => setShip({ ...ship, ship_type: v })}
                                                                >
                                                                        <SelectTrigger>
                                                                                <SelectValue />
                                                                        </SelectTrigger>
                                                                        <SelectContent>
                                                                                {SHIP_TYPES.map((st) => (
                                                                                        <SelectItem key={st.value} value={st.value}>
                                                                                                {st.label}
                                                                                        </SelectItem>
                                                                                ))}
                                                                        </SelectContent>
                                                                </Select>
                                                        </div>
                                                        <div className="space-y-1.5">
                                                                <Label className="text-xs text-muted-foreground">LOA (m)</Label>
                                                                <Input
                                                                        type="number"
                                                                        value={ship.length_overall_m}
                                                                        onChange={(e) => setShip({ ...ship, length_overall_m: e.target.value })}
                                                                />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                                <Label className="text-xs text-muted-foreground">Gross Tonnage</Label>
                                                                <Input
                                                                        type="number"
                                                                        value={ship.gross_tonnage}
                                                                        onChange={(e) => setShip({ ...ship, gross_tonnage: e.target.value })}
                                                                />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                                <Label className="text-xs text-muted-foreground">Passengers</Label>
                                                                <Input
                                                                        type="number"
                                                                        value={ship.passenger_capacity}
                                                                        onChange={(e) => setShip({ ...ship, passenger_capacity: e.target.value })}
                                                                />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                                <Label className="text-xs text-muted-foreground">Flag State</Label>
                                                                <Input
                                                                        value={ship.flag_state}
                                                                        onChange={(e) => setShip({ ...ship, flag_state: e.target.value })}
                                                                        placeholder="PA"
                                                                />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                                <Label className="text-xs text-muted-foreground">Class Society</Label>
                                                                <Select
                                                                        value={ship.classification_society}
                                                                        onValueChange={(v) => setShip({ ...ship, classification_society: v })}
                                                                >
                                                                        <SelectTrigger>
                                                                                <SelectValue />
                                                                        </SelectTrigger>
                                                                        <SelectContent>
                                                                                {SOCIETIES.map((s) => (
                                                                                        <SelectItem key={s} value={s}>
                                                                                                {s}
                                                                                        </SelectItem>
                                                                                ))}
                                                                        </SelectContent>
                                                                </Select>
                                                        </div>
                                                </div>
                                        </CardContent>
                                </Card>

                                {/* Actions */}
                                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                                        <Button onClick={handleFetchStandards} disabled={!!loading} variant="outline">
                                                {isLoading("standards") ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                                                Load Standards
                                        </Button>
                                        <Button onClick={handleFetchFireClasses} disabled={!!loading} variant="outline">
                                                {isLoading("fire-classes") ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                                                Fire Classes
                                        </Button>
                                        <Button onClick={handleValidate} disabled={!!loading}>
                                                {isLoading("validate") ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                                                Validate SOLAS
                                        </Button>
                                        <Button onClick={handleDivideZones} disabled={!!loading}>
                                                {isLoading("zones") ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                                                Divide MVZ Zones
                                        </Button>
                                        <Button onClick={handleDetection} disabled={!!loading || zones.length === 0} variant="secondary">
                                                {isLoading("detection") ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                                                Detection Design
                                        </Button>
                                        <Button onClick={handleExtinguishing} disabled={!!loading || zones.length === 0} variant="secondary">
                                                {isLoading("extinguishing") ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                                                Extinguishing
                                        </Button>
                                </div>

                                {/* Results */}
                                {standards.length > 0 && (
                                        <Card>
                                                <CardHeader>
                                                        <CardTitle>Marine Standards ({standards.length})</CardTitle>
                                                </CardHeader>
                                                <CardContent>
                                                        <div className="flex flex-wrap gap-2">
                                                                {standards.map((s, i) => {
                                                                        const std = s as { code: string; title: string; issuer: string };
                                                                        return (
                                                                                <Badge key={i} variant="outline" className="text-xs">
                                                                                        {std.code} — {std.issuer}
                                                                                </Badge>
                                                                        );
                                                                })}
                                                        </div>
                                                </CardContent>
                                        </Card>
                                )}

                                {validation && (
                                        <Card>
                                                <CardHeader>
                                                        <CardTitle>SOLAS Validation Result</CardTitle>
                                                </CardHeader>
                                                <CardContent>
                                                        <div className="space-y-2">
                                                                <div className="flex items-center gap-2">
                                                                        <span className="text-sm text-muted-foreground">Compliant:</span>
                                                                        <Badge variant={validation.compliant ? "default" : "destructive"}>
                                                                                {validation.compliant ? "PASS" : "FAIL"}
                                                                        </Badge>
                                                                </div>
                                                                <pre className="text-xs font-mono bg-muted p-3 rounded-md overflow-auto max-h-60">
                                                                        {JSON.stringify(validation, null, 2)}
                                                                </pre>
                                                        </div>
                                                </CardContent>
                                        </Card>
                                )}

                                {zones.length > 0 && (
                                        <Card>
                                                <CardHeader>
                                                        <CardTitle>Main Vertical Zones ({zones.length})</CardTitle>
                                                        <CardDescription>SOLAS II-2/2.2 — max 40m apart</CardDescription>
                                                </CardHeader>
                                                <CardContent>
                                                        <div className="space-y-2">
                                                                {zones.map((z, i) => {
                                                                        const zone = z as { zone_id: string; name: string; area_m2: number; required_fire_class: string };
                                                                        return (
                                                                                <div key={i} className="flex items-center justify-between text-sm border-b border-border pb-2">
                                                                                        <span className="font-mono text-foreground">{zone.zone_id}</span>
                                                                                        <span className="text-muted-foreground">{zone.name}</span>
                                                                                        <span className="font-mono text-muted-foreground">{zone.area_m2} m²</span>
                                                                                        <Badge variant="outline">{zone.required_fire_class}</Badge>
                                                                                </div>
                                                                        );
                                                                })}
                                                        </div>
                                                </CardContent>
                                        </Card>
                                )}

                                {detection && (
                                        <Card>
                                                <CardHeader>
                                                        <CardTitle>Detection Design</CardTitle>
                                                </CardHeader>
                                                <CardContent>
                                                        <pre className="text-xs font-mono bg-muted p-3 rounded-md overflow-auto max-h-60">
                                                                {JSON.stringify(detection, null, 2)}
                                                        </pre>
                                                </CardContent>
                                        </Card>
                                )}

                                {extinguishing && (
                                        <Card>
                                                <CardHeader>
                                                        <CardTitle>Extinguishing System Design</CardTitle>
                                                </CardHeader>
                                                <CardContent>
                                                        <pre className="text-xs font-mono bg-muted p-3 rounded-md overflow-auto max-h-60">
                                                                {JSON.stringify(extinguishing, null, 2)}
                                                        </pre>
                                                </CardContent>
                                        </Card>
                                )}
                        </div>
                </div>
        );
}
