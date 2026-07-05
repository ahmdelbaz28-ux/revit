export function Header() {
	return (
		<header className="h-14 flex items-center justify-between px-4 bg-slate-800 text-slate-200">
			<div className="flex items-center gap-3">
				<h1 className="text-xl font-bold">BAZSPARK Revit Digital Twin</h1>
			</div>
			<div className="flex items-center gap-4">
				<span className="text-sm">User</span>
			</div>
		</header>
	);
}
