/**
 * EnvironmentPage.tsx — Environmental context for fire protection design.
 *
 * V217: New page — 11 backend endpoints now have UI.
 * Weather, geocode, elevation, air quality, severe weather, hazmat, region.
 */
import { useState } from "react";
import { Cloud, MapPin, AlertTriangle, Loader2, Search } from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
import { environmentApi } from "@/services/fullApi";
import { useToast } from "@/hooks/use-toast";

export function EnvironmentPage() {
	const { toast } = useToast();
	const [loading, setLoading] = useState(false);
	const [address, setAddress] = useState("New York, NY");
	const [lat, setLat] = useState("40.7128");
	const [lon, setLon] = useState("-74.0060");
	const [weather, setWeather] = useState<Record<string, unknown> | null>(null);
	const [elevation, setElevation] = useState<Record<string, unknown> | null>(null);
	const [airQuality, setAirQuality] = useState<Record<string, unknown> | null>(null);
	const [severeWeather, setSevereWeather] = useState<Record<string, unknown> | null>(null);
	const [hazmatSubstance, setHazmatSubstance] = useState("gasoline");
	const [hazmatResult, setHazmatResult] = useState<Record<string, unknown> | null>(null);
	const [knownHazmat, setKnownHazmat] = useState<string[]>([]);

	const handleGeocode = async () => {
		setLoading(true);
		try {
			const res = await environmentApi.geocode(address);
			const data = res as Record<string, unknown>;
			if (data.latitude !== undefined) {
				setLat(String(data.latitude));
				setLon(String(data.longitude));
			}
		} catch (err) {
			toast({
				title: "Geocode Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleWeather = async () => {
		setLoading(true);
		try {
			const res = await environmentApi.getWeather(parseFloat(lat), parseFloat(lon));
			setWeather(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "Weather Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleElevation = async () => {
		setLoading(true);
		try {
			const res = await environmentApi.getElevation(parseFloat(lat), parseFloat(lon));
			setElevation(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "Elevation Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleAirQuality = async () => {
		setLoading(true);
		try {
			const res = await environmentApi.getAirQuality(parseFloat(lat), parseFloat(lon));
			setAirQuality(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "Air Quality Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleSevereWeather = async () => {
		setLoading(true);
		try {
			const res = await environmentApi.getSevereWeather(parseFloat(lat), parseFloat(lon));
			setSevereWeather(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "Severe Weather Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleHazmat = async () => {
		setLoading(true);
		try {
			const res = await environmentApi.getHazmat(hazmatSubstance);
			setHazmatResult(res as Record<string, unknown>);
		} catch (err) {
			toast({
				title: "Hazmat Lookup Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const handleKnownHazmat = async () => {
		setLoading(true);
		try {
			const res = await environmentApi.getKnownHazmat();
			setKnownHazmat((res as { substances?: string[] }).substances || []);
		} catch (err) {
			toast({
				title: "Failed",
				description: err instanceof Error ? err.message : "Failed",
				variant: "destructive",
			});
		} finally {
			setLoading(false);
		}
	};

	const renderJson = (data: Record<string, unknown> | null) =>
		data ? (
			<pre className="text-xs font-mono bg-muted p-3 rounded-md overflow-auto max-h-48">
				{JSON.stringify(data, null, 2)}
			</pre>
		) : null;

	return (
		<div className="flex-1 overflow-auto">
			<div className="p-6 max-w-5xl mx-auto space-y-6">
				<div>
					<h1 className="text-lg font-semibold text-foreground flex items-center gap-2">
						<Cloud className="h-5 w-5 text-primary" />
						Environmental Context
					</h1>
					<p className="text-sm text-muted-foreground mt-1">
						Weather · Elevation · Air Quality · Severe Weather · Hazmat — for site-specific fire protection design
					</p>
				</div>

				{/* Location Input */}
				<Card>
					<CardHeader>
						<CardTitle>Location</CardTitle>
						<CardDescription>Search by address or enter coordinates manually</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="grid grid-cols-1 md:grid-cols-4 gap-4">
							<div className="space-y-1.5 md:col-span-2">
								<Label className="text-xs text-muted-foreground">Address</Label>
								<div className="flex gap-2">
									<Input
										value={address}
										onChange={(e) => setAddress(e.target.value)}
										placeholder="123 Main St, New York, NY"
									/>
									<Button onClick={handleGeocode} disabled={loading} size="icon">
										{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
									</Button>
								</div>
							</div>
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">Latitude</Label>
								<Input value={lat} onChange={(e) => setLat(e.target.value)} />
							</div>
							<div className="space-y-1.5">
								<Label className="text-xs text-muted-foreground">Longitude</Label>
								<Input value={lon} onChange={(e) => setLon(e.target.value)} />
							</div>
						</div>
					</CardContent>
				</Card>

				{/* Quick Actions */}
				<div className="grid grid-cols-2 md:grid-cols-4 gap-3">
					<Button onClick={handleWeather} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Cloud className="h-4 w-4" />}
						Weather
					</Button>
					<Button onClick={handleElevation} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPin className="h-4 w-4" />}
						Elevation
					</Button>
					<Button onClick={handleAirQuality} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Cloud className="h-4 w-4" />}
						Air Quality
					</Button>
					<Button onClick={handleSevereWeather} disabled={loading} variant="outline">
						{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <AlertTriangle className="h-4 w-4" />}
						Severe Weather
					</Button>
				</div>

				{/* Results Grid */}
				<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
					{weather && (
						<Card>
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<Cloud className="h-4 w-4 text-primary" />
									Weather
								</CardTitle>
							</CardHeader>
							<CardContent>{renderJson(weather)}</CardContent>
						</Card>
					)}
					{elevation && (
						<Card>
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<MapPin className="h-4 w-4 text-primary" />
									Elevation
								</CardTitle>
							</CardHeader>
							<CardContent>{renderJson(elevation)}</CardContent>
						</Card>
					)}
					{airQuality && (
						<Card>
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<Cloud className="h-4 w-4 text-primary" />
									Air Quality
								</CardTitle>
							</CardHeader>
							<CardContent>{renderJson(airQuality)}</CardContent>
						</Card>
					)}
					{severeWeather && (
						<Card>
							<CardHeader>
								<CardTitle className="flex items-center gap-2">
									<AlertTriangle className="h-4 w-4 text-warning" />
									Severe Weather
								</CardTitle>
							</CardHeader>
							<CardContent>{renderJson(severeWeather)}</CardContent>
						</Card>
					)}
				</div>

				{/* Hazmat Lookup */}
				<Card>
					<CardHeader>
						<CardTitle>Hazmat Lookup</CardTitle>
						<CardDescription>
							Search for hazardous material properties (NFPA 704, flash point, UN number)
						</CardDescription>
					</CardHeader>
					<CardContent>
						<div className="flex gap-2 mb-4">
							<Input
								value={hazmatSubstance}
								onChange={(e) => setHazmatSubstance(e.target.value)}
								placeholder="gasoline, propane, ammonia..."
							/>
							<Button onClick={handleHazmat} disabled={loading}>
								{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
								Search
							</Button>
							<Button onClick={handleKnownHazmat} disabled={loading} variant="outline">
								List Known
							</Button>
						</div>
						{hazmatResult && renderJson(hazmatResult)}
						{knownHazmat.length > 0 && (
							<div className="flex flex-wrap gap-1.5 mt-3">
								{knownHazmat.map((s) => (
									<Badge
										key={s}
										variant="outline"
										className="cursor-pointer text-xs"
										onClick={() => {
											setHazmatSubstance(s);
										}}
									>
										{s}
									</Badge>
								))}
							</div>
						)}
					</CardContent>
				</Card>
			</div>
		</div>
	);
}
