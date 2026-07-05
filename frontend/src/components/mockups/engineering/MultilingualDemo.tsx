import {
	ArrowRight,
	CheckCircle2,
	ChevronDown,
	ChevronUp,
	Download,
	Globe,
	Plus,
	Settings,
	X,
} from "lucide-react";
import React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";

export function MultilingualDemo() {
	return (
		<div className="min-h-screen bg-slate-950 text-slate-100 font-sans p-6 overflow-y-auto">
			{/* Header */}
			<div className="max-w-7xl mx-auto space-y-8">
				<div className="flex items-center justify-between">
					<div>
						<h1 className="text-2xl font-bold tracking-tight text-white mb-2">
							NexusCAD Pro — Language & Localization System
						</h1>
						<p className="text-sm text-slate-400">
							Supporting Arabic (RTL), English (LTR), and French (LTR) — ISO
							639-1 compliant
						</p>
					</div>
					<div className="flex gap-2">
						<Button
							variant="outline"
							size="sm"
							className="bg-slate-900 border-slate-700"
						>
							<Settings className="w-4 h-4 mr-2" />
							Language Settings
						</Button>
						<Button
							variant="outline"
							size="sm"
							className="bg-slate-900 border-slate-700"
						>
							<Plus className="w-4 h-4 mr-2" />
							Add Language
						</Button>
						<Button
							variant="default"
							size="sm"
							className="bg-blue-600 hover:bg-blue-700 text-white"
						>
							<Download className="w-4 h-4 mr-2" />
							Export Translations
						</Button>
					</div>
				</div>

				{/* Top language selector bar */}
				<div className="grid grid-cols-3 gap-4">
					<LanguageCard
						id="EN"
						name="English"
						badge="Active"
						badgeColor="bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
						direction="LTR direction"
						completion="100% translated"
						isActive
					/>
					<LanguageCard
						id="AR"
						name="العربية"
						badge="Active Demo"
						badgeColor="bg-blue-500/20 text-blue-400 border-blue-500/30"
						direction="RTL — Right to Left"
						completion="98% translated"
						isActive={false}
					/>
					<LanguageCard
						id="FR"
						name="Français"
						badge="Available"
						badgeColor="bg-slate-500/20 text-slate-400 border-slate-500/30"
						direction="LTR direction"
						completion="95% translated"
						isActive={false}
					/>
				</div>

				{/* 3-column comparison */}
				<div className="grid grid-cols-3 gap-6 pt-4">
					{/* English Column */}
					<div className="flex flex-col gap-3">
						<div className="flex items-center justify-between pb-2 border-b border-slate-800">
							<div className="flex items-center gap-2">
								<span className="font-semibold text-slate-200">English</span>
								<Badge
									variant="outline"
									className="text-[10px] px-1 py-0 border-slate-700 text-slate-400"
								>
									LTR
								</Badge>
							</div>
							<span className="text-xs text-emerald-400">100%</span>
						</div>

						<div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden flex flex-col h-[320px]">
							{/* Header */}
							<div className="h-8 border-b border-slate-800 flex items-center justify-between px-3 bg-slate-900/50">
								<span className="text-xs font-semibold text-slate-200">
									Engineering Log
								</span>
								<span className="text-[10px] text-slate-500 flex gap-2">
									<span className="text-red-400">3 Errors</span>
									<span className="text-orange-400">5 Warnings</span>
									<span className="text-blue-400">12 Info</span>
								</span>
							</div>
							{/* Tabs */}
							<div className="flex text-[10px] font-mono border-b border-slate-800 bg-slate-900">
								<div className="px-3 py-1.5 border-b-2 border-blue-500 text-blue-400">
									Errors
								</div>
								<div className="px-3 py-1.5 text-slate-500">Warnings</div>
								<div className="px-3 py-1.5 text-slate-500">Output</div>
								<div className="px-3 py-1.5 text-slate-500">Commands</div>
							</div>
							{/* Content */}
							<div className="flex-1 bg-[#0a0a0a] overflow-hidden p-1 space-y-1">
								<DemoErrorRow
									text="Panel LP-3A: Neutral bar spacing violates NEC §408.36 — clearance 38mm < 50mm required"
									ltr
								/>
								<DemoErrorRow
									text="MDB-B overloaded: demand 978A exceeds 800A bus rating (122.3%)"
									ltr
								/>
								<DemoErrorRow
									text="Panel LP-3A: Arc flash label missing. Incident energy 52.4 cal/cm²"
									ltr
								/>
							</div>
							{/* Footer */}
							<div className="h-7 border-t border-slate-800 flex items-center justify-between px-3 bg-slate-900/50">
								<span className="text-[9px] font-mono text-slate-500">
									X: 2847.32 | Y: 1203.48 | Layer: Electrical | Project: Tower-B
									| Rev: 14
								</span>
								<div className="flex items-center text-[10px] text-slate-400 gap-1 cursor-pointer">
									Hide Panel <ChevronDown className="w-3 h-3" />
								</div>
							</div>
						</div>
					</div>

					{/* Arabic Column */}
					<div className="flex flex-col gap-3 relative">
						<div className="absolute left-[-12px] top-0 bottom-0 w-px bg-slate-800"></div>

						<div
							className="flex items-center justify-between pb-2 border-b border-slate-800"
							dir="rtl"
						>
							<div className="flex items-center gap-2">
								<span className="font-semibold text-slate-200">العربية</span>
								<Badge
									variant="outline"
									className="text-[10px] px-1 py-0 border-slate-700 text-slate-400"
								>
									RTL
								</Badge>
							</div>
							<span className="text-xs text-emerald-400">98%</span>
						</div>

						<div
							className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden flex flex-col h-[320px]"
							dir="rtl"
						>
							{/* Header */}
							<div className="h-8 border-b border-slate-800 flex items-center justify-between px-3 bg-slate-900/50">
								<span className="text-xs font-semibold text-slate-200">
									سجل الهندسة
								</span>
								<span className="text-[10px] text-slate-500 flex gap-2">
									<span className="text-red-400">3 أخطاء</span>
									<span className="text-orange-400">5 تحذيرات</span>
									<span className="text-blue-400">12 معلومة</span>
								</span>
							</div>
							{/* Tabs */}
							<div className="flex text-[10px] font-mono border-b border-slate-800 bg-slate-900">
								<div className="px-3 py-1.5 border-b-2 border-blue-500 text-blue-400">
									الأخطاء
								</div>
								<div className="px-3 py-1.5 text-slate-500">التحذيرات</div>
								<div className="px-3 py-1.5 text-slate-500">المخرجات</div>
								<div className="px-3 py-1.5 text-slate-500">الأوامر</div>
							</div>
							{/* Content */}
							<div className="flex-1 bg-[#0a0a0a] overflow-hidden p-1 space-y-1">
								<DemoErrorRow text="لوحة LP-3A: تباعد شريط المحايد يخالف NEC §408.36 — المسافة 38مم < 50مم مطلوب" />
								<DemoErrorRow text="MDB-B محملة زائداً: الطلب 978A يتجاوز تقييم الحافلة 800A (122.3%)" />
								<DemoErrorRow text="لوحة LP-3A: ملصق وميض القوس مفقود. طاقة الحادثة 52.4 cal/cm²" />
							</div>
							{/* Footer */}
							<div className="h-7 border-t border-slate-800 flex items-center justify-between px-3 bg-slate-900/50">
								<span className="text-[9px] font-mono text-slate-500">
									س: 2847.32 | ص: 1203.48 | الطبقة: الكهربائي | المشروع: برج-ب |
									المراجعة: 14
								</span>
								<div className="flex items-center text-[10px] text-slate-400 gap-1 cursor-pointer">
									إخفاء اللوحة <ChevronDown className="w-3 h-3" />
								</div>
							</div>
						</div>
					</div>

					{/* French Column */}
					<div className="flex flex-col gap-3 relative">
						<div className="absolute left-[-12px] top-0 bottom-0 w-px bg-slate-800"></div>

						<div className="flex items-center justify-between pb-2 border-b border-slate-800">
							<div className="flex items-center gap-2">
								<span className="font-semibold text-slate-200">Français</span>
								<Badge
									variant="outline"
									className="text-[10px] px-1 py-0 border-slate-700 text-slate-400"
								>
									LTR
								</Badge>
							</div>
							<span className="text-xs text-yellow-500">95%</span>
						</div>

						<div className="bg-slate-900 rounded-lg border border-slate-800 overflow-hidden flex flex-col h-[320px]">
							{/* Header */}
							<div className="h-8 border-b border-slate-800 flex items-center justify-between px-3 bg-slate-900/50">
								<span className="text-xs font-semibold text-slate-200">
									Journal d'ingénierie
								</span>
								<span className="text-[10px] text-slate-500 flex gap-2">
									<span className="text-red-400">3 Erreurs</span>
									<span className="text-orange-400">5 Avertissements</span>
									<span className="text-blue-400">12 Infos</span>
								</span>
							</div>
							{/* Tabs */}
							<div className="flex text-[10px] font-mono border-b border-slate-800 bg-slate-900">
								<div className="px-3 py-1.5 border-b-2 border-blue-500 text-blue-400">
									Erreurs
								</div>
								<div className="px-3 py-1.5 text-slate-500">Avertissements</div>
								<div className="px-3 py-1.5 text-slate-500">Sortie</div>
								<div className="px-3 py-1.5 text-slate-500">Commandes</div>
							</div>
							{/* Content */}
							<div className="flex-1 bg-[#0a0a0a] overflow-hidden p-1 space-y-1">
								<DemoErrorRow
									text="Tableau LP-3A: Espacement barre neutre viole NEC §408.36 — Jeu 38mm < 50mm requis"
									ltr
								/>
								<DemoErrorRow
									text="MDB-B surchargé: demande 978A dépasse 800A capacité du bus (122,3%)"
									ltr
								/>
								<DemoErrorRow
									text="Tableau LP-3A: Étiquette arc électrique manquante. Énergie 52,4 cal/cm²"
									ltr
								/>
							</div>
							{/* Footer */}
							<div className="h-7 border-t border-slate-800 flex items-center justify-between px-3 bg-slate-900/50">
								<span className="text-[9px] font-mono text-slate-500">
									X: 2847.32 | Y: 1203.48 | Calque: Électrique | Projet: Tour-B
									| Rév: 14
								</span>
								<div className="flex items-center text-[10px] text-slate-400 gap-1 cursor-pointer">
									Masquer le panneau <ChevronDown className="w-3 h-3" />
								</div>
							</div>
						</div>
					</div>
				</div>

				<div className="grid grid-cols-2 gap-8 pt-8">
					{/* Section: Auto-Expand Behavior */}
					<div className="space-y-4">
						<h3 className="text-lg font-semibold text-slate-200">
							Auto-Expand on Error Behavior
						</h3>
						<div className="space-y-3">
							<div className="flex items-center gap-4">
								<div className="w-48 h-16 bg-slate-900 border border-slate-800 rounded relative overflow-hidden">
									<div className="absolute bottom-0 w-full h-2 bg-slate-800 border-t border-slate-700"></div>
								</div>
								<span className="text-sm text-slate-400">
									1. No errors — panel collapsed
								</span>
							</div>
							<div className="flex items-center gap-4">
								<div className="w-48 h-16 bg-slate-900 border border-slate-800 rounded relative overflow-hidden shadow-[0_0_15px_rgba(239,68,68,0.15)]">
									<div className="absolute bottom-0 w-full h-8 bg-slate-800 border-t border-red-500/50 flex flex-col">
										<div className="h-2 w-full bg-red-500/10"></div>
										<div className="flex-1 bg-red-950/20"></div>
									</div>
									<div className="absolute top-2 right-2 text-[8px] text-red-400 animate-pulse">
										Auto-expanding...
									</div>
								</div>
								<span className="text-sm text-slate-400">
									2. New error detected — panel auto-expands
								</span>
							</div>
							<div className="flex items-center gap-4">
								<div className="w-48 h-16 bg-slate-900 border border-slate-800 rounded relative overflow-hidden">
									<div className="absolute bottom-0 w-full h-2 bg-slate-800 border-t border-slate-700 flex justify-end items-center pr-2">
										<div className="w-3 h-1.5 bg-red-500 rounded-sm"></div>
									</div>
								</div>
								<span className="text-sm text-slate-400">
									3. User dismisses — collapses, badge remains
								</span>
							</div>
						</div>
					</div>

					{/* RTL Layout Engine */}
					<div className="space-y-4">
						<h3 className="text-lg font-semibold text-slate-200">
							RTL Layout Engine
						</h3>
						<ul className="list-disc pl-4 space-y-2 text-sm text-slate-400">
							<li>
								Automatic mirror of all panels, toolbars, and navigation for RTL
								languages
							</li>
							<li>
								Numbers and engineering values remain LTR (IEC 80000-1
								compliant)
							</li>
							<li>Mixed-direction text handled via Unicode BiDi algorithm</li>
						</ul>
						<div className="flex gap-4 mt-4">
							<div className="flex-1 h-24 bg-slate-900 border border-slate-800 rounded p-2 flex">
								<div className="w-1/4 h-full bg-slate-800 rounded-sm mr-2 border-r-2 border-blue-500"></div>
								<div className="flex-1 h-full bg-slate-950 rounded-sm"></div>
								<div className="w-1/3 h-full bg-slate-800 rounded-sm ml-2"></div>
							</div>
							<div className="flex items-center">
								<ArrowRight className="text-slate-600" />
							</div>
							<div
								className="flex-1 h-24 bg-slate-900 border border-slate-800 rounded p-2 flex"
								dir="rtl"
							>
								<div className="w-1/4 h-full bg-slate-800 rounded-sm ml-2 border-l-2 border-blue-500"></div>
								<div className="flex-1 h-full bg-slate-950 rounded-sm"></div>
								<div className="w-1/3 h-full bg-slate-800 rounded-sm mr-2"></div>
							</div>
						</div>
						<div className="flex justify-between text-[10px] text-slate-500 px-8">
							<span>LTR Default</span>
							<span>RTL Mirrored</span>
						</div>
					</div>
				</div>

				{/* Terminology Table */}
				<div className="pt-8 pb-12">
					<h3 className="text-lg font-semibold text-slate-200 mb-4">
						Supported Engineering Terminology Databases
					</h3>
					<div className="border border-slate-800 rounded-lg overflow-hidden bg-slate-900/50">
						<Table>
							<TableHeader className="bg-slate-900 border-b border-slate-800">
								<TableRow className="hover:bg-transparent border-slate-800">
									<TableHead className="text-slate-300">Domain</TableHead>
									<TableHead className="text-slate-300 text-right">
										EN Terms
									</TableHead>
									<TableHead className="text-slate-300 text-right">
										AR Terms
									</TableHead>
									<TableHead className="text-slate-300 text-right">
										FR Terms
									</TableHead>
									<TableHead className="text-slate-300 text-center">
										Status
									</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								<TermRow
									domain="Electrical"
									en="4,847"
									ar="4,712"
									fr="4,391"
									status="Complete"
								/>
								<TermRow
									domain="Fire Alarm"
									en="1,203"
									ar="1,189"
									fr="1,098"
									status="Complete"
								/>
								<TermRow
									domain="BIM/Structural"
									en="3,421"
									ar="3,156"
									fr="3,287"
									status="Complete"
								/>
								<TermRow
									domain="HVAC/Mechanical"
									en="2,891"
									ar="2,834"
									fr="2,756"
									status="Complete"
								/>
								<TermRow
									domain="Standards & Codes"
									en="892"
									ar="743"
									fr="681"
									status="Partial"
								/>
								<TermRow
									domain="UI Labels"
									en="2,341"
									ar="2,341"
									fr="2,228"
									status="Complete"
								/>
							</TableBody>
						</Table>
					</div>
				</div>
			</div>
		</div>
	);
}

function LanguageCard({
	id,
	name,
	badge,
	badgeColor,
	direction,
	completion,
	isActive,
}: {
	id: string;
	name: string;
	badge: string;
	badgeColor: string;
	direction: string;
	completion: string;
	isActive: boolean;
}) {
	return (
		<Card
			className={`bg-slate-900 border ${isActive ? "border-blue-500/50" : "border-slate-800"} p-4 flex flex-col gap-3 relative overflow-hidden group`}
		>
			{isActive && (
				<div className="absolute top-0 left-0 right-0 h-0.5 bg-blue-500" />
			)}
			<div className="flex justify-between items-start">
				<div className="flex items-center gap-3">
					<div className="w-8 h-8 rounded bg-slate-800 flex items-center justify-center font-bold text-slate-300 border border-slate-700">
						{id}
					</div>
					<div>
						<h3 className="font-semibold text-slate-200">{name}</h3>
						<p className="text-xs text-slate-500">{direction}</p>
					</div>
				</div>
				<Badge className={`text-[10px] ${badgeColor}`}>{badge}</Badge>
			</div>
			<div className="pt-2 border-t border-slate-800 flex items-center justify-between">
				<div className="flex flex-col gap-1">
					<span className="text-xs text-slate-400">{completion}</span>
					<div className="w-32 h-1 bg-slate-800 rounded-full overflow-hidden">
						<div
							className={`h-full ${completion.startsWith("100") ? "bg-emerald-500" : "bg-blue-500"}`}
							style={{ width: completion.split("%")[0] + "%" }}
						/>
					</div>
				</div>
				<Button
					variant={isActive ? "secondary" : "ghost"}
					size="sm"
					className="h-7 text-xs"
				>
					{isActive ? (
						<>
							<CheckCircle2 className="w-3 h-3 mr-1" /> Active
						</>
					) : (
						"Set Active"
					)}
				</Button>
			</div>
		</Card>
	);
}

function DemoErrorRow({ text, ltr = false }: { text: string; ltr?: boolean }) {
	return (
		<div
			className={`text-[9px] font-mono p-1.5 bg-red-950/20 border border-red-900/30 rounded flex items-center gap-2 ${ltr ? "border-l-2 border-l-red-500" : "border-r-2 border-r-red-500"}`}
		>
			<div className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0"></div>
			<span className="text-slate-300 truncate leading-tight">{text}</span>
		</div>
	);
}

function TermRow({
	domain,
	en,
	ar,
	fr,
	status,
}: {
	domain: string;
	en: string;
	ar: string;
	fr: string;
	status: string;
}) {
	const isComplete = status === "Complete";
	return (
		<TableRow className="border-slate-800 hover:bg-slate-800/50">
			<TableCell className="font-medium text-slate-300 py-3">
				{domain}
			</TableCell>
			<TableCell className="text-right font-mono text-slate-400">
				{en}
			</TableCell>
			<TableCell className="text-right font-mono text-slate-400">
				{ar}
			</TableCell>
			<TableCell className="text-right font-mono text-slate-400">
				{fr}
			</TableCell>
			<TableCell className="text-center">
				<Badge
					variant="outline"
					className={`text-[10px] ${isComplete ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" : "text-yellow-400 border-yellow-500/30 bg-yellow-500/10"}`}
				>
					{status}
				</Badge>
			</TableCell>
		</TableRow>
	);
}
