import {
	Activity,
	ArrowRight,
	Bell,
	Box,
	CheckSquare,
	ChevronDown,
	ChevronUp,
	Cloud,
	Cpu,
	Crosshair,
	Eye,
	EyeOff,
	FileText,
	Focus,
	FolderOpen,
	Layers,
	Layout,
	Lock,
	Maximize,
	Mic,
	MinusSquare,
	Monitor,
	PenTool,
	Plus,
	Search,
	Settings,
	Triangle,
	User,
	X,
	Zap,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export function WorkspaceArabic() {
	const [activeTab, setActiveTab] = useState("كهربائي");
	const [activeFile, setActiveFile] = useState("Tower-B-Electrical.dwg");
	const [isErrorLogExpanded, setIsErrorLogExpanded] = useState(true);

	return (
		<div
			dir="rtl"
			className="flex flex-col h-screen w-screen overflow-hidden bg-background text-foreground font-sans"
		>
			{/* Top Ribbon */}
			<div className="h-24 flex flex-col border-b bg-card">
				{/* Top bar */}
				<div className="h-10 flex items-center justify-between px-4 border-b border-border/50">
					<div className="flex items-center gap-4">
						<div className="flex items-center gap-2 text-primary">
							<Zap className="h-5 w-5 fill-current" />
							<span className="font-bold tracking-wider text-sm">
								نيكساد برو
							</span>
						</div>
						<Separator orientation="vertical" className="h-5" />
						<div className="flex text-xs space-x-1">
							{[
								"ملف",
								"تحرير",
								"عرض",
								"إدراج",
								"تعليق",
								"الإنشائي",
								"كهربائي",
								"نمذجة معلومات البناء",
								"الذكاء الاصطناعي",
								"تعاون",
								"أدوات",
								"مساعدة",
							].map((tab) => (
								<button
									key={tab}
									className={`px-3 py-1 rounded-sm transition-colors ${activeTab === tab ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted"}`}
									onClick={() => setActiveTab(tab)}
								>
									{tab}
								</button>
							))}
						</div>
					</div>
					<div className="flex items-center gap-4 text-muted-foreground">
						{/* Language Switcher */}
						<div className="flex bg-muted/50 rounded-full p-0.5 mr-4 border border-border/50">
							<div className="px-2.5 py-0.5 text-[10px] font-semibold text-muted-foreground rounded-full hover:bg-muted cursor-pointer transition-colors">
								EN
							</div>
							<div className="px-2.5 py-0.5 text-[10px] font-semibold text-primary-foreground bg-primary rounded-full shadow-sm">
								عربي ✓
							</div>
							<div className="px-2.5 py-0.5 text-[10px] font-semibold text-muted-foreground rounded-full hover:bg-muted cursor-pointer transition-colors">
								FR
							</div>
						</div>

						<div className="flex items-center gap-2 text-xs">
							<Cloud className="h-4 w-4 text-emerald-400" />
							<span>متزامن</span>
						</div>
						<Separator orientation="vertical" className="h-5" />
						<div className="flex items-center gap-2 text-xs">
							<Cpu className="h-4 w-4" />
							<div
								className="w-16 h-1.5 bg-muted rounded-full overflow-hidden"
								dir="ltr"
							>
								<div className="bg-primary h-full w-[45%]"></div>
							</div>
						</div>
						<Separator orientation="vertical" className="h-5" />
						<Bell className="h-4 w-4 hover:text-foreground cursor-pointer" />
						<div className="h-6 w-6 rounded-full bg-primary/20 border border-primary/50 flex items-center justify-center text-xs font-bold text-primary">
							JS
						</div>
					</div>
				</div>
				{/* Sub-ribbon */}
				<div className="h-14 flex items-center px-2 space-x-1 bg-card/50 overflow-x-auto">
					{activeTab === "كهربائي" && (
						<>
							<RibbonBtn icon={<MinusSquare />} label="سلك جديد" />
							<RibbonBtn icon={<Plus />} label="إضافة مكون" />
							<Separator orientation="vertical" className="h-8 mx-1" />
							<RibbonBtn icon={<Layout />} label="شريط الحافلة" />
							<RibbonBtn icon={<Layers />} label="مجرى الكابلات" />
							<RibbonBtn icon={<Monitor />} label="لوحة توزيع" />
							<RibbonBtn icon={<Zap />} label="قاطع دائرة" />
							<RibbonBtn icon={<ArrowRight />} label="رمز الأرضي" />
							<Separator orientation="vertical" className="h-8 mx-1" />
							<RibbonBtn icon={<Activity />} label="حساب الحمل" />
							<RibbonBtn
								icon={<Zap className="text-amber-400" />}
								label="وميض القوس"
							/>
							<RibbonBtn icon={<Lock />} label="مرحل حماية" />
						</>
					)}
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Explorer (Right in RTL) */}
				<div className="w-60 flex flex-col border-l bg-card/30">
					<div className="px-3 py-2 text-xs font-semibold tracking-wider text-muted-foreground border-b flex justify-between items-center">
						<span>مستكشف المشروع</span>
						<Search className="h-3 w-3" />
					</div>
					<ScrollArea className="flex-1">
						<div className="p-2 text-sm">
							<TreeNode title="برج-ب مجمع مكاتب" defaultOpen>
								<TreeNode title="الرسومات" defaultOpen>
									<TreeNode title="الكهربائي" defaultOpen>
										<FileNode
											title="Tower-B-Electrical.dwg"
											type="dwg"
											active
										/>
										<FileNode title="Fire-Alarm-Plan.dwg" type="dwg" />
										<FileNode title="Lighting-Layout.dwg" type="dwg" />
									</TreeNode>
									<TreeNode title="الميكانيكي" />
									<TreeNode title="الإنشائي" />
								</TreeNode>
								<TreeNode title="نماذج BIM">
									<FileNode title="BIM-Model.rvt" type="rvt" />
								</TreeNode>
								<TreeNode title="التقارير">
									<FileNode title="Load-Calc.xlsx" type="xlsx" />
								</TreeNode>
								<TreeNode title="المعايير" />
							</TreeNode>
						</div>
					</ScrollArea>

					<div className="h-1/3 flex flex-col border-t bg-card/20">
						<div className="px-3 py-2 text-xs font-semibold tracking-wider text-muted-foreground border-b flex justify-between items-center bg-card/40">
							<span>مدير الطبقات</span>
							<Settings className="h-3 w-3" />
						</div>
						<ScrollArea className="flex-1 p-2">
							<LayerRow name="الشبكة" color="bg-slate-500" />
							<LayerRow name="الجدران" color="bg-zinc-400" />
							<LayerRow name="الكهربائي" color="bg-primary" active />
							<LayerRow name="الإضاءة" color="bg-yellow-400" />
							<LayerRow name="التدفئة والتبريد" color="bg-blue-300" hidden />
							<LayerRow name="السباكة" color="bg-cyan-400" hidden />
							<LayerRow name="الإنشائي" color="bg-orange-500" locked />
							<LayerRow name="التعليقات" color="bg-green-400" />
						</ScrollArea>
					</div>
				</div>

				{/* Central Canvas */}
				<div className="flex-1 flex flex-col relative bg-[#0f1115]">
					{/* File Tabs */}
					<div className="flex border-b bg-card" dir="ltr">
						{[
							"Tower-B-Electrical.dwg",
							"Fire-Alarm-Plan.dwg",
							"BIM-Model.rvt",
							"Load-Calc.xlsx",
						].map((file) => (
							<div
								key={file}
								className={`px-4 py-2 text-xs border-r flex items-center gap-2 cursor-pointer ${activeFile === file ? "bg-[#0f1115] text-primary border-t-2 border-t-primary" : "text-muted-foreground hover:bg-muted"}`}
								onClick={() => setActiveFile(file)}
							>
								{file.endsWith(".dwg") ? (
									<Layout className="h-3 w-3" />
								) : (
									<Box className="h-3 w-3" />
								)}
								{file}
								<X className="h-3 w-3 ml-2 opacity-50 hover:opacity-100" />
							</div>
						))}
					</div>

					{/* Canvas area */}
					<div
						className="flex-1 relative overflow-hidden flex"
						style={{
							backgroundImage: "radial-gradient(#1e293b 1px, transparent 1px)",
							backgroundSize: "20px 20px",
						}}
					>
						{/* Rulers */}
						<div
							className="absolute top-0 left-0 right-6 h-6 bg-card/80 border-b flex items-end overflow-hidden z-10"
							dir="ltr"
						>
							<div
								className="w-full border-b border-muted-foreground/30 relative"
								style={{ height: "5px" }}
							>
								{Array.from({ length: 40 }).map((_, i) => (
									<div
										key={i}
										className="absolute border-l border-muted-foreground/30 h-full"
										style={{ left: `${i * 50}px` }}
									></div>
								))}
							</div>
						</div>
						<div
							className="absolute top-0 bottom-0 right-0 w-6 bg-card/80 border-l flex justify-start overflow-hidden z-10"
							dir="ltr"
						>
							<div
								className="h-full border-r border-muted-foreground/30 relative"
								style={{ width: "5px" }}
							>
								{Array.from({ length: 20 }).map((_, i) => (
									<div
										key={i}
										className="absolute border-t border-muted-foreground/30 w-full"
										style={{ top: `${i * 50}px` }}
									></div>
								))}
							</div>
						</div>

						{/* Drawing Content */}
						<div
							className="absolute inset-0 pt-6 pr-6 overflow-hidden"
							dir="ltr"
						>
							{/* Fake diagram elements */}
							<div className="absolute top-32 right-40 w-64 h-80 border-2 border-slate-600 rounded-sm"></div>
							<div className="absolute top-[180px] right-40 w-[600px] h-0.5 bg-primary"></div>
							<div className="absolute top-[280px] right-40 w-[450px] h-0.5 bg-primary"></div>
							<div className="absolute top-[380px] right-40 w-[550px] h-0.5 bg-primary"></div>

							<div className="absolute top-[170px] right-[640px] w-8 h-12 border-2 border-primary bg-[#0f1115] z-10"></div>
							<div className="absolute top-[270px] right-[490px] w-8 h-12 border-2 border-primary bg-[#0f1115] z-10"></div>
							<div className="absolute top-[370px] right-[590px] w-8 h-12 border-2 border-primary bg-[#0f1115] z-10"></div>

							{/* Selected Element */}
							<div className="absolute top-[140px] right-32 w-16 h-100 border border-primary/50 bg-primary/10 backdrop-blur-sm shadow-[0_0_15px_rgba(0,168,255,0.2)] flex items-center justify-center group cursor-pointer z-10">
								<div className="absolute -top-6 text-[10px] text-primary whitespace-nowrap font-mono">
									LP-3A [400A]
								</div>
								<div className="w-2 h-2 rounded-full bg-primary absolute -top-1 -right-1"></div>
								<div className="w-2 h-2 rounded-full bg-primary absolute -top-1 -left-1"></div>
								<div className="w-2 h-2 rounded-full bg-primary absolute -bottom-1 -right-1"></div>
								<div className="w-2 h-2 rounded-full bg-primary absolute -bottom-1 -left-1"></div>
							</div>

							{/* Dimensions */}
							<div className="absolute top-28 right-40 w-64 border-t border-dashed border-emerald-500/50 flex justify-center items-center h-4">
								<div className="px-2 bg-[#0f1115] text-[10px] text-emerald-400 font-mono">
									4200mm
								</div>
							</div>
						</div>

						{/* Floating Mini Toolbar */}
						<div className="absolute top-10 left-4 bg-card/80 backdrop-blur border rounded-md shadow-lg flex flex-col p-1 gap-1 z-20">
							<ToolBtn icon={<Crosshair />} active />
							<ToolBtn icon={<Maximize />} />
							<ToolBtn icon={<Focus />} />
							<Separator />
							<ToolBtn icon={<PenTool />} />
							<ToolBtn icon={<Triangle />} />
						</div>

						{/* Canvas Footer */}
						<div
							className="absolute bottom-4 left-4 flex items-center gap-2 z-20 font-mono text-[10px] text-muted-foreground bg-card/80 backdrop-blur px-2 py-1 rounded border"
							dir="ltr"
						>
							<span>Zoom: 1:50</span>
							<Separator orientation="vertical" className="h-3" />
							<span>X: 2847.32 Y: 1203.48</span>
						</div>
					</div>
				</div>

				{/* Right Panel (Left in RTL) */}
				<div className="w-80 flex flex-col border-r bg-card/30">
					{/* Properties Panel */}
					<div className="h-1/2 flex flex-col border-b">
						<div className="px-3 py-2 text-xs font-semibold tracking-wider text-muted-foreground border-b flex justify-between items-center bg-card/40">
							<span>الخصائص</span>
							<Settings className="h-3 w-3" />
						</div>
						<ScrollArea className="flex-1">
							<div className="p-3">
								<div className="flex items-center gap-2 mb-4">
									<div className="h-8 w-8 rounded bg-primary/20 flex items-center justify-center">
										<Monitor className="h-4 w-4 text-primary" />
									</div>
									<div>
										<div className="font-medium text-sm">لوحة توزيع LP-3A</div>
										<div
											className="text-[10px] text-muted-foreground font-mono"
											dir="ltr"
										>
											ID: ELEC-PNL-8932
										</div>
									</div>
								</div>

								<div className="space-y-3">
									<PropRow label="الجهد" value="480V" />
									<PropRow label="الأوجه" value="3" />
									<PropRow label="سعة التيار" value="400A" />
									<PropRow label="حجم الإطار" value="600A" />
									<PropRow label="المُصنِّع" value="Eaton Corp" />
									<PropRow label="الموقع" value="المستوى 3، غرفة الكهـ ب" />

									<div className="pt-2 border-t mt-2">
										<div className="flex justify-between items-center text-xs mb-1">
											<span className="text-muted-foreground">الامتثال</span>
											<Badge
												variant="outline"
												className="text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
											>
												<CheckSquare className="w-3 h-3 ml-1" /> NFPA 70
											</Badge>
										</div>
									</div>

									<div className="pt-2 border-t mt-2">
										<div className="text-xs text-muted-foreground mb-1">
											ملاحظات
										</div>
										<div className="text-xs p-2 rounded bg-muted/50 border italic">
											مطلوب مساحة خلوص 36 بوصة في الأمام حسب NEC 110.26
										</div>
									</div>
								</div>
							</div>
						</ScrollArea>
					</div>

					{/* AI Copilot mini */}
					<div className="flex-1 flex flex-col bg-card/20">
						<div className="px-3 py-2 text-xs font-semibold tracking-wider text-primary border-b flex items-center gap-2 bg-card/40">
							<Zap className="h-3 w-3" />
							<span>مساعد الذكاء الاصطناعي</span>
						</div>
						<ScrollArea className="flex-1 p-3">
							<div className="space-y-4">
								<div className="flex flex-col gap-1 items-start">
									<div className="bg-primary/20 text-foreground px-3 py-2 rounded-lg rounded-tl-none text-xs max-w-[85%] border border-primary/20">
										تحقق من الحمل على LP-3A
									</div>
									<div className="text-[9px] text-muted-foreground" dir="ltr">
										14:28
									</div>
								</div>

								<div className="flex gap-2">
									<div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center text-primary-foreground shrink-0 mt-1">
										<Zap className="h-3 w-3" />
									</div>
									<div className="flex flex-col gap-1">
										<div className="bg-muted px-3 py-2 rounded-lg rounded-tr-none text-xs text-foreground border">
											يتم حالياً تحميل اللوحة LP-3A عند 285A (71% من السعة 400A).
											<br />
											<br />
											<span className="text-emerald-400 font-mono">
												الحالة: آمن
											</span>
											<br />
											السعة المتبقية: 115A.
										</div>
										<div className="flex gap-1 mt-1">
											<Badge
												variant="secondary"
												className="text-[10px] cursor-pointer hover:bg-secondary/80"
											>
												عرض التفاصيل
											</Badge>
											<Badge
												variant="secondary"
												className="text-[10px] cursor-pointer hover:bg-secondary/80"
											>
												إنشاء تقرير
											</Badge>
										</div>
									</div>
								</div>
							</div>
						</ScrollArea>

						<div className="p-2 border-t bg-card/50">
							<div className="flex gap-1 mb-2 overflow-x-auto pb-1 scrollbar-hide">
								<Badge
									variant="outline"
									className="text-[10px] whitespace-nowrap cursor-pointer"
								>
									فحص الامتثال
								</Badge>
								<Badge
									variant="outline"
									className="text-[10px] whitespace-nowrap cursor-pointer"
								>
									اقتراح المسار
								</Badge>
							</div>
							<div className="relative">
								<Input
									className="pl-8 pr-3 bg-background border-muted text-xs h-8"
									placeholder="اسأل المساعد..."
								/>
								<Button
									size="icon"
									variant="ghost"
									className="absolute left-0 top-0 h-8 w-8 text-primary"
								>
									<Mic className="h-4 w-4" />
								</Button>
							</div>
						</div>
					</div>
				</div>
			</div>

			{/* Error Log Panel */}
			<div
				className={`flex flex-col border-t bg-card/95 backdrop-blur-md transition-all duration-300 ease-in-out shrink-0 overflow-hidden ${isErrorLogExpanded ? "h-48" : "h-7"}`}
			>
				{/* Header row (always visible) */}
				<div
					className="h-7 flex items-center justify-between px-2 border-b cursor-pointer select-none shrink-0"
					onClick={() => setIsErrorLogExpanded(!isErrorLogExpanded)}
				>
					<div className="flex items-center gap-3">
						<div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
						<span className="text-[11px] font-semibold tracking-wider text-foreground">
							سجل الهندسة
						</span>
						<div className="flex gap-1.5 items-center">
							<Badge
								variant="destructive"
								className="h-4 text-[9px] px-1.5 py-0 border-red-500/50 bg-red-500"
							>
								3 أخطاء
							</Badge>
							<Badge
								variant="outline"
								className="h-4 text-[9px] px-1.5 py-0 text-orange-400 border-orange-500/50 bg-orange-500/10"
							>
								5 تحذيرات
							</Badge>
							<Badge
								variant="outline"
								className="h-4 text-[9px] px-1.5 py-0 text-blue-400 border-blue-500/50 bg-blue-500/10"
							>
								12 معلومات
							</Badge>
						</div>
					</div>
					<div className="flex items-center gap-2">
						<Button
							variant="ghost"
							size="sm"
							className="h-5 text-[10px] text-muted-foreground hover:text-foreground px-2"
							onClick={(e) => {
								e.stopPropagation();
							}}
						>
							مسح الكل
						</Button>
						<Button
							variant="ghost"
							size="sm"
							className="h-5 text-[10px] text-muted-foreground hover:text-foreground px-2"
							onClick={(e) => {
								e.stopPropagation();
							}}
						>
							تصدير السجل
						</Button>
						<Separator orientation="vertical" className="h-4" />
						<Button
							variant="ghost"
							size="icon"
							className="h-5 w-5 text-muted-foreground hover:text-foreground"
						>
							{isErrorLogExpanded ? (
								<ChevronDown className="h-3 w-3" />
							) : (
								<ChevronUp className="h-3 w-3" />
							)}
						</Button>
					</div>
				</div>

				{/* Expanded Content */}
				<div
					className={`flex-1 overflow-hidden transition-opacity duration-200 ${isErrorLogExpanded ? "opacity-100" : "opacity-0 pointer-events-none"}`}
				>
					<ScrollArea className="h-full w-full font-mono text-xs">
						<div className="flex flex-col">
							<LogEntry
								level="ERROR"
								time="14:47:03"
								source="NEC Compliance"
								message="لوحة LP-3A: تباعد شريط المحايد يخالف NEC §408.36 — المسافة 38مم < 50مم مطلوب"
							/>
							<LogEntry
								level="ERROR"
								time="14:46:51"
								source="Load Calculator"
								message="MDB-B محملة زائداً: الطلب 978A يتجاوز تقييم الحافلة 800A (122.3%)"
							/>
							<LogEntry
								level="ERROR"
								time="14:45:22"
								source="Arc Flash"
								message="لوحة LP-3A: ملصق وميض القوس مفقود. طاقة الحادثة 52.4 cal/cm² — مطلوب PPE الفئة 4"
							/>
							<LogEntry
								level="WARN"
								time="14:44:10"
								source="BIM Sync"
								message="IFC export: 3 elements skipped — unsupported geometry type (IFCBSPLINECURVE)"
							/>
							<LogEntry
								level="WARN"
								time="14:43:38"
								source="Clash Detection"
								message="5 new soft clashes detected in MEP zone — Level 2, Grid C–E / 3–6"
							/>
							<LogEntry
								level="WARN"
								time="14:42:15"
								source="Cable Sizing"
								message="Cable run EL-C-047: voltage drop 4.8% approaching 5% limit"
							/>
							<LogEntry
								level="WARN"
								time="14:41:02"
								source="File System"
								message="Auto-save delayed 12s — large file lock on BIM-Model.rvt"
							/>
							<LogEntry
								level="WARN"
								time="14:40:30"
								source="Collaboration"
								message="User Marcus Williams connection timeout — changes may not be synced"
							/>
							<LogEntry
								level="INFO"
								time="14:38:44"
								source="System"
								message="BIM model synchronized with Revit v14 — 2,847 elements updated"
							/>
							<LogEntry
								level="INFO"
								time="14:37:21"
								source="Analysis"
								message="Load flow converged — Newton-Raphson, 7 iterations, tolerance 0.0001 pu"
							/>
							<LogEntry
								level="INFO"
								time="14:36:05"
								source="Compliance"
								message="NFPA 72 check complete — 127 items passed, 2 warnings"
							/>
							<LogEntry
								level="INFO"
								time="14:35:00"
								source="System"
								message="Auto-save complete — 5 files, 47MB"
							/>
						</div>
					</ScrollArea>
				</div>
			</div>

			{/* Status Bar */}
			<div className="h-6 flex items-center justify-between px-4 bg-primary/10 border-t border-primary/20 text-[10px] font-mono text-primary/80 shrink-0">
				<div className="flex items-center gap-4">
					<span dir="ltr">X: 2847.32 Y: 1203.48</span>
					<Separator orientation="vertical" className="h-3 bg-primary/20" />
					<span>الالتقاط: تشغيل</span>
					<Separator orientation="vertical" className="h-3 bg-primary/20" />
					<span dir="ltr">الشبكة: 5mm</span>
					<Separator orientation="vertical" className="h-3 bg-primary/20" />
					<span>الطبقة: الكهربائي</span>
				</div>
				<div className="flex items-center gap-4">
					<span>المشروع: برج-ب</span>
					<Separator orientation="vertical" className="h-3 bg-primary/20" />
					<span>المراجعة: 14</span>
					<Separator orientation="vertical" className="h-3 bg-primary/20" />
					<span>آخر حفظ: قبل دقيقتين</span>
					<Separator orientation="vertical" className="h-3 bg-primary/20" />
					<div className="flex items-center gap-1">
						<User className="h-3 w-3" />
						<span>3 متصلون</span>
					</div>
				</div>
			</div>
		</div>
	);
}

function LogEntry({
	level,
	time,
	source,
	message,
}: {
	level: "ERROR" | "WARN" | "INFO";
	time: string;
	source: string;
	message: string;
}) {
	const isError = level === "ERROR";
	const isWarn = level === "WARN";

	return (
		<div
			className={`flex items-center px-4 py-1.5 border-b border-border/30 hover:bg-muted/30 group ${isError ? "bg-red-950/20 border-r-2 border-r-red-500" : isWarn ? "bg-orange-950/20 border-r-2 border-r-orange-500" : "border-r-2 border-r-transparent"}`}
		>
			<div className="w-[80px] shrink-0 text-muted-foreground" dir="ltr">
				{time}
			</div>
			<div className="w-[60px] shrink-0" dir="ltr">
				<span
					className={`${isError ? "text-red-400" : isWarn ? "text-orange-400" : "text-slate-400"}`}
				>
					{level}
				</span>
			</div>
			<div
				className="w-[130px] shrink-0 text-slate-500 truncate pl-4"
				dir="ltr"
			>
				{source}
			</div>
			<div className="flex-1 text-slate-300 truncate pl-4">{message}</div>
			<div className="shrink-0 flex items-center gap-4 opacity-0 group-hover:opacity-100 transition-opacity">
				{level !== "INFO" && (
					<span className="text-blue-400 hover:underline cursor-pointer">
						انتقال
					</span>
				)}
				<X className="h-3 w-3 text-muted-foreground hover:text-foreground cursor-pointer" />
			</div>
		</div>
	);
}

function RibbonBtn({ icon, label }: { icon: React.ReactNode; label: string }) {
	return (
		<div className="flex flex-col items-center justify-center w-16 h-12 rounded hover:bg-muted cursor-pointer transition-colors group">
			<div className="text-muted-foreground group-hover:text-primary mb-1 [&>svg]:w-4 [&>svg]:h-4">
				{icon}
			</div>
			<span className="text-[9px] text-center leading-tight whitespace-nowrap px-1 overflow-hidden text-ellipsis w-full text-muted-foreground group-hover:text-foreground">
				{label}
			</span>
		</div>
	);
}

function TreeNode({
	title,
	children,
	defaultOpen = false,
}: {
	title: string;
	children?: React.ReactNode;
	defaultOpen?: boolean;
}) {
	const [open, setOpen] = useState(defaultOpen);
	return (
		<div className="select-none">
			<div
				className="flex items-center gap-1 py-1 hover:bg-muted/50 cursor-pointer rounded px-1"
				onClick={() => setOpen(!open)}
			>
				<Triangle
					className={`h-3 w-3 text-muted-foreground transition-transform ${open ? "rotate-180" : "-rotate-90"}`}
				/>
				<FolderOpen className="h-3.5 w-3.5 text-blue-400/80" />
				<span className="text-xs truncate">{title}</span>
			</div>
			{open && children && (
				<div className="mr-3 pr-2 border-r border-border/50 flex flex-col gap-0.5 mt-0.5">
					{children}
				</div>
			)}
		</div>
	);
}

function FileNode({
	title,
	type,
	active = false,
}: {
	title: string;
	type: string;
	active?: boolean;
}) {
	let color = "text-muted-foreground";
	if (type === "dwg") color = "text-blue-400";
	if (type === "rvt") color = "text-orange-400";
	if (type === "xlsx") color = "text-emerald-400";

	return (
		<div
			className={`flex items-center gap-2 py-1 px-2 rounded cursor-pointer ${active ? "bg-primary/10 text-primary" : "hover:bg-muted/50 text-muted-foreground"}`}
			dir="ltr"
		>
			<span
				className={`text-xs truncate text-right w-full ${active ? "font-medium" : ""}`}
			>
				{title}
			</span>
			<FileText className={`h-3.5 w-3.5 shrink-0 ${color}`} />
		</div>
	);
}

function LayerRow({
	name,
	color,
	active = false,
	hidden = false,
	locked = false,
}: {
	name: string;
	color: string;
	active?: boolean;
	hidden?: boolean;
	locked?: boolean;
}) {
	return (
		<div
			className={`flex items-center justify-between py-1.5 px-2 rounded hover:bg-muted/50 group ${active ? "bg-muted/30" : ""}`}
		>
			<div className="flex items-center gap-2">
				<div className={`w-2.5 h-2.5 rounded-full ${color}`}></div>
				<span
					className={`text-xs ${active ? "text-foreground font-medium" : "text-muted-foreground"}`}
				>
					{name}
				</span>
			</div>
			<div className="flex items-center gap-1.5 opacity-60 group-hover:opacity-100">
				{hidden ? (
					<EyeOff className="h-3 w-3 text-muted-foreground" />
				) : (
					<Eye className="h-3 w-3 text-foreground" />
				)}
				{locked ? (
					<Lock className="h-3 w-3 text-amber-500/70" />
				) : (
					<div className="w-3 h-3"></div>
				)}
			</div>
		</div>
	);
}

function ToolBtn({
	icon,
	active = false,
}: {
	icon: React.ReactNode;
	active?: boolean;
}) {
	return (
		<div
			className={`w-8 h-8 rounded flex items-center justify-center cursor-pointer [&>svg]:w-4 [&>svg]:h-4 ${active ? "bg-primary/20 text-primary border border-primary/30" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
		>
			{icon}
		</div>
	);
}

function PropRow({ label, value }: { label: string; value: string }) {
	return (
		<div className="flex justify-between items-center text-xs">
			<span className="text-muted-foreground">{label}</span>
			<span className="font-mono text-foreground" dir="ltr">
				{value}
			</span>
		</div>
	);
}
