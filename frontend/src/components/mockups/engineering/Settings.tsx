
import {
	Cloud,
	Cpu,
	HardDrive,
	Key,
	Keyboard,
	Layout,
	Lock,
	Mic,
	Monitor,
	Settings2,
	ShieldCheck,
	Users,
	Zap,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";

export function Settings() {
	const [activeTab, setActiveTab] = useState("Display & Graphics");

	return (
		<div className="w-screen h-screen bg-[#0a0a0c] font-sans dark text-foreground flex flex-col overflow-hidden">
			{/* Header */}
			<div className="h-16 border-b border-white/5 flex items-center justify-between px-8 bg-[#0f1115]">
				<div className="flex items-center gap-3 text-white">
					<Settings2 className="w-6 h-6 text-primary" />
					<h1 className="text-xl font-bold tracking-wide">
						Settings Architecture
					</h1>
				</div>
				<div className="text-xs text-muted-foreground font-mono bg-white/5 px-3 py-1 rounded">
					NexusCAD Pro Enterprise Edition
				</div>
			</div>

			<div className="flex flex-1 overflow-hidden">
				{/* Left Nav */}
				<div className="w-72 border-r border-white/5 bg-[#0f1115] flex flex-col">
					<ScrollArea className="flex-1 py-4">
						<div className="space-y-1 px-3">
							<NavItem
								icon={<Settings2 />}
								title="General"
								active={activeTab === "General"}
								onClick={() => setActiveTab("General")}
							/>
							<NavItem
								icon={<Monitor />}
								title="Display & Graphics"
								active={activeTab === "Display & Graphics"}
								onClick={() => setActiveTab("Display & Graphics")}
							/>
							<NavItem
								icon={<Cpu />}
								title="GPU & Performance"
								active={activeTab === "GPU & Performance"}
								onClick={() => setActiveTab("GPU & Performance")}
							/>
							<NavItem
								icon={<Layout />}
								title="Workspace"
								active={activeTab === "Workspace"}
								onClick={() => setActiveTab("Workspace")}
							/>
							<NavItem
								icon={<Mic />}
								title="AI & Voice"
								active={activeTab === "AI & Voice"}
								onClick={() => setActiveTab("AI & Voice")}
							/>

							<div className="my-4" />
							<div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
								System
							</div>

							<NavItem
								icon={<HardDrive />}
								title="File Handling"
								active={activeTab === "File Handling"}
								onClick={() => setActiveTab("File Handling")}
							/>
							<NavItem
								icon={<Users />}
								title="Collaboration"
								active={activeTab === "Collaboration"}
								onClick={() => setActiveTab("Collaboration")}
							/>
							<NavItem
								icon={<ShieldCheck />}
								title="Standards & Compliance"
								active={activeTab === "Standards & Compliance"}
								onClick={() => setActiveTab("Standards & Compliance")}
							/>
							<NavItem
								icon={<Zap />}
								title="Plugin Manager"
								active={activeTab === "Plugin Manager"}
								onClick={() => setActiveTab("Plugin Manager")}
							/>
							<NavItem
								icon={<Keyboard />}
								title="Keyboard Shortcuts"
								active={activeTab === "Keyboard Shortcuts"}
								onClick={() => setActiveTab("Keyboard Shortcuts")}
							/>

							<div className="my-4" />
							<div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
								Account
							</div>

							<NavItem
								icon={<Cloud />}
								title="Cloud & Backup"
								active={activeTab === "Cloud & Backup"}
								onClick={() => setActiveTab("Cloud & Backup")}
							/>
							<NavItem
								icon={<Lock />}
								title="Security"
								active={activeTab === "Security"}
								onClick={() => setActiveTab("Security")}
							/>
							<NavItem
								icon={<Key />}
								title="Licensing"
								active={activeTab === "Licensing"}
								onClick={() => setActiveTab("Licensing")}
							/>
						</div>
					</ScrollArea>
				</div>

				{/* Main Content */}
				<div className="flex-1 flex flex-col bg-[#0a0a0c] relative">
					<div className="absolute top-0 right-0 w-[800px] h-[800px] bg-primary/5 rounded-full blur-[120px] pointer-events-none -translate-y-1/2 translate-x-1/3"></div>

					<div className="px-10 pt-8 pb-4 border-b border-white/5 relative z-10">
						<h2 className="text-2xl font-bold text-white mb-1">{activeTab}</h2>
						<p className="text-sm text-muted-foreground">
							Configure visual output, hardware acceleration, and interface
							appearance.
						</p>
					</div>

					<ScrollArea className="flex-1 relative z-10">
						<div className="p-10 max-w-4xl space-y-12">
							{/* Section: Rendering */}
							<section>
								<SectionHeader title="Rendering Engine" />
								<div className="grid grid-cols-2 gap-x-12 gap-y-6">
									<SettingRow
										title="Hardware Acceleration"
										desc="Uses GPU for 2D/3D rendering"
									>
										<Switch defaultChecked />
									</SettingRow>

									<SettingRow
										title="Render Quality"
										desc="Overall visual fidelity"
									>
										<Slider
											defaultValue={[75]}
											max={100}
											step={25}
											className="w-32"
										/>
										<span className="text-xs font-mono ml-3 text-primary">
											High
										</span>
									</SettingRow>

									<SettingRow title="Anti-Aliasing" desc="Smooths jagged edges">
										<Select defaultValue="8x">
											<SelectTrigger className="w-[140px] h-8 bg-[#15181e] border-white/10 text-xs">
												<SelectValue placeholder="Select" />
											</SelectTrigger>
											<SelectContent className="bg-[#15181e] border-white/10 text-white">
												<SelectItem value="off">Off</SelectItem>
												<SelectItem value="2x">2x MSAA</SelectItem>
												<SelectItem value="4x">4x MSAA</SelectItem>
												<SelectItem value="8x">8x MSAA</SelectItem>
												<SelectItem value="taa">TAA (Temporal)</SelectItem>
											</SelectContent>
										</Select>
									</SettingRow>

									<SettingRow
										title="LOD Distance"
										desc="Level of detail dropoff"
									>
										<Slider
											defaultValue={[80]}
											max={100}
											step={1}
											className="w-32"
										/>
									</SettingRow>

									<SettingRow
										title="Shadow Quality"
										desc="Resolution of projected shadows"
									>
										<Select defaultValue="high">
											<SelectTrigger className="w-[140px] h-8 bg-[#15181e] border-white/10 text-xs">
												<SelectValue placeholder="Select" />
											</SelectTrigger>
											<SelectContent className="bg-[#15181e] border-white/10 text-white">
												<SelectItem value="low">Low (1024)</SelectItem>
												<SelectItem value="med">Medium (2048)</SelectItem>
												<SelectItem value="high">High (4096)</SelectItem>
												<SelectItem value="ultra">Ultra (RTX)</SelectItem>
											</SelectContent>
										</Select>
									</SettingRow>
								</div>
							</section>

							{/* Section: Interface */}
							<section>
								<SectionHeader title="Interface Options" />
								<div className="grid grid-cols-2 gap-x-12 gap-y-6">
									<SettingRow
										title="UI Scale"
										desc="Adjust overall element size"
									>
										<Slider
											defaultValue={[100]}
											min={75}
											max={150}
											step={5}
											className="w-32"
										/>
										<span className="text-xs font-mono ml-3 text-white">
											100%
										</span>
									</SettingRow>

									<SettingRow
										title="DPI Awareness"
										desc="Scale correctly on high-res displays"
									>
										<Switch defaultChecked />
									</SettingRow>

									<SettingRow
										title="Panel Opacity"
										desc="Transparency of floating windows"
									>
										<Slider
											defaultValue={[95]}
											max={100}
											step={1}
											className="w-32"
										/>
										<span className="text-xs font-mono ml-3 text-white">
											95%
										</span>
									</SettingRow>

									<SettingRow
										title="Animation Speed"
										desc="Duration of UI transitions"
									>
										<Slider
											defaultValue={[50]}
											max={100}
											step={1}
											className="w-32"
										/>
										<span className="text-xs font-mono ml-3 text-white">
											Normal
										</span>
									</SettingRow>
								</div>
							</section>

							{/* Section: Color Theme */}
							<section>
								<SectionHeader title="Color Theme" />
								<div className="space-y-6">
									<div className="flex gap-4">
										<ThemeCard mode="Dark" active />
										<ThemeCard mode="Light" />
										<ThemeCard mode="System" />
									</div>

									<div className="grid grid-cols-2 gap-x-12 gap-y-6 mt-6">
										<SettingRow
											title="Accent Color"
											desc="Primary highlight color"
										>
											<div className="flex gap-2">
												<ColorSwatch color="bg-blue-500" active />
												<ColorSwatch color="bg-cyan-500" />
												<ColorSwatch color="bg-emerald-500" />
												<ColorSwatch color="bg-amber-500" />
												<ColorSwatch color="bg-primary" />
												<ColorSwatch color="bg-violet-500" />
											</div>
										</SettingRow>

										<SettingRow
											title="Canvas Background"
											desc="Working area color"
										>
											<div className="flex items-center gap-2">
												<div className="w-6 h-6 rounded bg-[#0f1115] border border-white/20"></div>
												<span className="text-xs font-mono text-muted-foreground">
													#0f1115
												</span>
											</div>
										</SettingRow>
									</div>
								</div>
							</section>

							{/* Section: Advanced GPU */}
							<section>
								<SectionHeader title="Advanced GPU Configuration" />
								<div className="bg-[#15181e] border border-white/5 rounded-lg p-4 mb-6 flex items-center justify-between">
									<div className="flex items-center gap-3">
										<div className="w-10 h-10 rounded bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
											<Cpu className="w-5 h-5 text-success" />
										</div>
										<div>
											<div className="text-sm font-semibold text-white">
												NVIDIA RTX 4090 (24GB)
											</div>
											<div className="text-xs text-success font-mono mt-0.5">
												Active Compute Device • Driver 536.23
											</div>
										</div>
									</div>
									<Button
										variant="outline"
										size="sm"
										className="h-8 text-xs bg-transparent border-white/10 hover:bg-white/5 text-white"
									>
										Update Drivers
									</Button>
								</div>

								<div className="grid grid-cols-2 gap-x-12 gap-y-6">
									<SettingRow
										title="VRAM Limit"
										desc="Maximum memory allocation"
									>
										<Slider
											defaultValue={[8192]}
											max={24576}
											step={1024}
											className="w-32"
										/>
										<span className="text-xs font-mono ml-3 text-warning">
											8192 MB
										</span>
									</SettingRow>

									<SettingRow
										title="Deferred Rendering"
										desc="Optimizes dense complex scenes"
									>
										<Switch defaultChecked />
									</SettingRow>

									<SettingRow
										title="Hardware Tessellation"
										desc="Dynamic mesh subdivision"
									>
										<Switch />
									</SettingRow>
								</div>
							</section>
						</div>
					</ScrollArea>

					{/* Footer Actions */}
					<div className="h-20 border-t border-white/5 bg-[#0f1115] px-10 flex items-center justify-between z-10 relative">
						<Button
							variant="ghost"
							className="text-destructive hover:bg-destructive/10 hover:text-destructive text-sm font-medium"
						>
							Reset to Defaults
						</Button>
						<div className="flex gap-3">
							<Button
								variant="outline"
								className="bg-[#15181e] border-white/10 text-white hover:bg-white/5 text-sm font-medium"
							>
								Export Config
							</Button>
							<Button className="bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-semibold px-8 shadow-[0_0_15px_rgba(0,168,255,0.3)]">
								Save Settings
							</Button>
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}

function NavItem({
	icon,
	title,
	active,
	onClick,
}: {
	icon: React.ReactNode;
	title: string;
	active?: boolean;
	onClick?: () => void;
}) {
	return (
		<div
		role="button"
		tabIndex=0
			className={`flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors group ${active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-white/5 hover:text-white"}`}
			onClick={onClick}
		onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick } }}
		>
			<div
				className={`[&>svg]:w-4 [&>svg]:h-4 ${active ? "text-primary" : "text-muted-foreground group-hover:text-foreground/90"}`}
			>
				{icon}
			</div>
			<span className={`text-sm font-medium ${active ? "" : "font-normal"}`}>
				{title}
			</span>
		</div>
	);
}

function SectionHeader({ title }: { title: string }) {
	return (
		<div className="flex items-center gap-4 mb-6">
			<h3 className="text-sm font-bold tracking-wide uppercase text-white">
				{title}
			</h3>
			<Separator className="flex-1 bg-white/5" />
		</div>
	);
}

function SettingRow({
	title,
	desc,
	children,
}: {
	title: string;
	desc: string;
	children: React.ReactNode;
}) {
	return (
		<div className="flex items-center justify-between p-3 rounded-lg hover:bg-white/[0.02] transition-colors -mx-3">
			<div>
				<div className="text-sm font-medium text-white mb-0.5">{title}</div>
				<div className="text-xs text-muted-foreground">{desc}</div>
			</div>
			<div className="flex items-center">{children}</div>
		</div>
	);
}

function ThemeCard({ mode, active }: { mode: string; active?: boolean }) {
	return (
		<div
			className={`flex flex-col gap-2 p-3 rounded-md border cursor-pointer transition-all w-32 ${active ? "bg-primary/5 border-primary ring-1 ring-primary/30" : "bg-[#15181e] border-white/5 hover:border-white/20"}`}
		>
			<div
				className={`w-full h-16 rounded-md overflow-hidden flex flex-col border ${active ? "border-primary/50" : "border-white/10"}`}
			>
				{mode === "Dark" && (
					<div className="flex-1 bg-[#0a0a0c] flex">
						<div className="w-1/4 h-full bg-[#15181e] border-r border-white/5"></div>
						<div className="flex-1 p-1">
							<div className="w-full h-1/2 bg-primary/20 rounded-sm"></div>
						</div>
					</div>
				)}
				{mode === "Light" && (
					<div className="flex-1 bg-white flex">
						<div className="w-1/4 h-full bg-slate-100 border-r border-slate-200"></div>
						<div className="flex-1 p-1">
							<div className="w-full h-1/2 bg-blue-500/20 rounded-sm"></div>
						</div>
					</div>
				)}
				{mode === "System" && (
					<div className="flex-1 flex">
						<div className="w-1/2 h-full bg-white"></div>
						<div className="w-1/2 h-full bg-[#0a0a0c]"></div>
					</div>
				)}
			</div>
			<div className="text-sm text-center font-medium text-white mt-1">
				{mode}
			</div>
		</div>
	);
}

function ColorSwatch({ color, active }: { color: string; active?: boolean }) {
	return (
		<div
			className={`w-6 h-6 rounded-full cursor-pointer flex items-center justify-center ${color} ${active ? "ring-2 ring-white ring-offset-2 ring-offset-[#0a0a0c]" : "opacity-80 hover:opacity-100"}`}
		></div>
	);
}
