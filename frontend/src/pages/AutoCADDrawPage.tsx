// NOSONAR
/**
 * AutoCADDrawPage.tsx — Drawing tools for AutoCAD
 */

import { Circle, Loader2, Minus, Spline, Type } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { autocadService } from "@/services/autocadService";

export function AutoCADDrawPage() {
	const [drawing, setDrawing] = useState(false);
	const [activeTool, setActiveTool] = useState("line");

	// Line state
	const [lineStart, setLineStart] = useState("");
	const [lineEnd, setLineEnd] = useState("");
	const [lineLayer, setLineLayer] = useState("");

	// Polyline state
	const [polyPoints, setPolyPoints] = useState("");
	const [polyLayer, setPolyLayer] = useState("");

	// Circle state
	const [circleCenter, setCircleCenter] = useState("");
	const [circleRadius, setCircleRadius] = useState("");
	const [circleLayer, setCircleLayer] = useState("");

	// Text state
	const [textPoint, setTextPoint] = useState("");
	const [textContent, setTextContent] = useState("");
	const [textHeight, setTextHeight] = useState("2.5");
	const [textLayer, setTextLayer] = useState("");

	const parsePoint = (s: string): number[] => {
		return s.split(",").map((v) => parseFloat(v.trim()));  // NOSONAR - typescript:S7773
	};

	const drawLine = async () => {
		setDrawing(true);
		try {
			await autocadService.drawLine(
				parsePoint(lineStart),
				parsePoint(lineEnd),
				lineLayer || undefined,
			);
			toast.success("Line drawn");
		} catch (err) {
			toast.error(
				`Draw failed: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
		} finally {
			setDrawing(false);
		}
	};

	const drawPolyline = async () => {
		setDrawing(true);
		try {
			const points = polyPoints.split(";").map((p) => parsePoint(p.trim()));
			await autocadService.drawPolyline(points, polyLayer || undefined);
			toast.success("Polyline drawn");
		} catch (err) {
			toast.error(
				`Draw failed: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
		} finally {
			setDrawing(false);
		}
	};

	const drawCircle = async () => {
		setDrawing(true);
		try {
			await autocadService.drawCircle(
				parsePoint(circleCenter),
				parseFloat(circleRadius),  // NOSONAR - typescript:S7773
				circleLayer || undefined,
			);
			toast.success("Circle drawn");
		} catch (err) {
			toast.error(
				`Draw failed: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
		} finally {
			setDrawing(false);
		}
	};

	const drawText = async () => {
		setDrawing(true);
		try {
			await autocadService.drawText(
				parsePoint(textPoint),
				textContent,
				parseFloat(textHeight),  // NOSONAR - typescript:S7773
				textLayer || undefined,
			);
			toast.success("Text drawn");
		} catch (err) {
			toast.error(
				`Draw failed: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
		} finally {
			setDrawing(false);
		}
	};

	return (
		<div className="flex-1 overflow-auto p-6 max-w-4xl mx-auto space-y-6">
			<div>
				<h1 className="text-2xl font-bold text-foreground">
					AutoCAD Drawing Tools
				</h1>
				<p className="text-sm text-muted-foreground mt-1">
					Draw lines, polylines, circles, and text in AutoCAD
				</p>
			</div>

			<Tabs value={activeTool} onValueChange={setActiveTool}>
				<TabsList className="bg-card border border-border">
					<TabsTrigger
						value="line"
						className="data-[state=active]:bg-primary data-[state=active]:text-white"
					>
						<Minus className="h-4 w-4 mr-1" /> Line
					</TabsTrigger>
					<TabsTrigger
						value="polyline"
						className="data-[state=active]:bg-primary data-[state=active]:text-white"
					>
						<Spline className="h-4 w-4 mr-1" /> Polyline
					</TabsTrigger>
					<TabsTrigger
						value="circle"
						className="data-[state=active]:bg-primary data-[state=active]:text-white"
					>
						<Circle className="h-4 w-4 mr-1" /> Circle
					</TabsTrigger>
					<TabsTrigger
						value="text"
						className="data-[state=active]:bg-primary data-[state=active]:text-white"
					>
						<Type className="h-4 w-4 mr-1" /> Text
					</TabsTrigger>
				</TabsList>

				<TabsContent value="line">
					<Card className="border-border bg-card">
						<CardHeader>
							<CardTitle className="text-foreground">Draw Line</CardTitle>
							<CardDescription className="text-muted-foreground">
								Draw a line between two points
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-3">
							<div className="grid grid-cols-2 gap-3">
								<div>
									<Label className="text-foreground/90">Start (x,y,z)</Label>
									<Input
										placeholder="0,0,0"
										value={lineStart}
										onChange={(e) => setLineStart(e.target.value)}
										className="bg-card border-border text-foreground"
									/>
								</div>
								<div>
									<Label className="text-foreground/90">End (x,y,z)</Label>
									<Input
										placeholder="100,0,0"
										value={lineEnd}
										onChange={(e) => setLineEnd(e.target.value)}
										className="bg-card border-border text-foreground"
									/>
								</div>
							</div>
							<div>
								<Label className="text-foreground/90">Layer (optional)</Label>
								<Input
									placeholder="Walls"
									value={lineLayer}
									onChange={(e) => setLineLayer(e.target.value)}
									className="bg-card border-border text-foreground"
								/>
							</div>
							<Button
								onClick={drawLine}
								disabled={drawing}
								className="bg-primary hover:bg-orange-700 text-white"
							>
								{drawing ? (
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
								) : (
									<Minus className="h-4 w-4 mr-2" />
								)}
								Draw Line
							</Button>
						</CardContent>
					</Card>
				</TabsContent>

				<TabsContent value="polyline">
					<Card className="border-border bg-card">
						<CardHeader>
							<CardTitle className="text-foreground">Draw Polyline</CardTitle>
							<CardDescription className="text-muted-foreground">
								Draw a polyline through multiple points
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-3">
							<div>
								<Label className="text-foreground/90">
									Points (x,y,z separated by ;)
								</Label>
								<Input
									placeholder="0,0,0; 100,0,0; 100,50,0"
									value={polyPoints}
									onChange={(e) => setPolyPoints(e.target.value)}
									className="bg-card border-border text-foreground"
								/>
							</div>
							<div>
								<Label className="text-foreground/90">Layer (optional)</Label>
								<Input
									placeholder="Boundary"
									value={polyLayer}
									onChange={(e) => setPolyLayer(e.target.value)}
									className="bg-card border-border text-foreground"
								/>
							</div>
							<Button
								onClick={drawPolyline}
								disabled={drawing}
								className="bg-primary hover:bg-orange-700 text-white"
							>
								{drawing ? (
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
								) : (
									<Spline className="h-4 w-4 mr-2" />
								)}
								Draw Polyline
							</Button>
						</CardContent>
					</Card>
				</TabsContent>

				<TabsContent value="circle">
					<Card className="border-border bg-card">
						<CardHeader>
							<CardTitle className="text-foreground">Draw Circle</CardTitle>
							<CardDescription className="text-muted-foreground">
								Draw a circle at center with radius
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-3">
							<div className="grid grid-cols-2 gap-3">
								<div>
									<Label className="text-foreground/90">Center (x,y,z)</Label>
									<Input
										placeholder="50,50,0"
										value={circleCenter}
										onChange={(e) => setCircleCenter(e.target.value)}
										className="bg-card border-border text-foreground"
									/>
								</div>
								<div>
									<Label className="text-foreground/90">Radius</Label>
									<Input
										placeholder="25"
										value={circleRadius}
										onChange={(e) => setCircleRadius(e.target.value)}
										className="bg-card border-border text-foreground"
									/>
								</div>
							</div>
							<div>
								<Label className="text-foreground/90">Layer (optional)</Label>
								<Input
									placeholder="Annotations"
									value={circleLayer}
									onChange={(e) => setCircleLayer(e.target.value)}
									className="bg-card border-border text-foreground"
								/>
							</div>
							<Button
								onClick={drawCircle}
								disabled={drawing}
								className="bg-primary hover:bg-orange-700 text-white"
							>
								{drawing ? (
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
								) : (
									<Circle className="h-4 w-4 mr-2" />
								)}
								Draw Circle
							</Button>
						</CardContent>
					</Card>
				</TabsContent>

				<TabsContent value="text">
					<Card className="border-border bg-card">
						<CardHeader>
							<CardTitle className="text-foreground">Draw Text</CardTitle>
							<CardDescription className="text-muted-foreground">
								Insert text at a point
							</CardDescription>
						</CardHeader>
						<CardContent className="space-y-3">
							<div>
								<Label className="text-foreground/90">
									Insertion Point (x,y,z)
								</Label>
								<Input
									placeholder="10,10,0"
									value={textPoint}
									onChange={(e) => setTextPoint(e.target.value)}
									className="bg-card border-border text-foreground"
								/>
							</div>
							<div>
								<Label className="text-foreground/90">Text Content</Label>
								<Input
									placeholder="Room 101"
									value={textContent}
									onChange={(e) => setTextContent(e.target.value)}
									className="bg-card border-border text-foreground"
								/>
							</div>
							<div className="grid grid-cols-2 gap-3">
								<div>
									<Label className="text-foreground/90">Height</Label>
									<Input
										placeholder="2.5"
										value={textHeight}
										onChange={(e) => setTextHeight(e.target.value)}
										className="bg-card border-border text-foreground"
									/>
								</div>
								<div>
									<Label className="text-foreground/90">Layer (optional)</Label>
									<Input
										placeholder="Labels"
										value={textLayer}
										onChange={(e) => setTextLayer(e.target.value)}
										className="bg-card border-border text-foreground"
									/>
								</div>
							</div>
							<Button
								onClick={drawText}
								disabled={drawing}
								className="bg-primary hover:bg-orange-700 text-white"
							>
								{drawing ? (
									<Loader2 className="h-4 w-4 mr-2 animate-spin" />
								) : (
									<Type className="h-4 w-4 mr-2" />
								)}
								Draw Text
							</Button>
						</CardContent>
					</Card>
				</TabsContent>
			</Tabs>
		</div>
	);
}
