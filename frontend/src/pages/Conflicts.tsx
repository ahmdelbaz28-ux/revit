import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { api } from "@/services/api";

function Conflicts() {
	const { t } = useTranslation();
	const queryClient = useQueryClient();
	const [resolveTarget, setResolveTarget] = useState<string | null>(null);
	const [resolveStrategy, setResolveStrategy] = useState("LAST_WRITE_WINS");

	const {
		data: conflictsData,
		isLoading,
		error,
	} = useQuery({
		queryKey: ["conflicts"],
		queryFn: () => api.getConflicts(),
	});

	const conflicts = conflictsData?.items ?? [];

	const detectMutation = useMutation({
		mutationFn: () => api.detectConflicts(),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["conflicts"] });
		},
	});

	const resolveMutation = useMutation({
		mutationFn: ({ id, strategy }: { id: string; strategy: string }) =>
			api.resolveConflict(id, strategy),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ["conflicts"] });
			setResolveTarget(null);
		},
	});

	const resolvedCount = conflicts?.filter((c) => c.resolved).length ?? 0;
	const unresolvedCount = conflicts ? conflicts.length - resolvedCount : 0;

	return (
		<div className="space-y-6" aria-label={t("conflicts.title")}>
			{/* Header */}
			<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
				<div>
					<h1 className="text-2xl font-bold text-white">
						{t("conflicts.title")}
					</h1>
					<p className="text-slate-400 text-sm mt-1">
						{conflicts
							? `${unresolvedCount} ${t("conflicts.unresolved")} / ${resolvedCount} ${t("conflicts.resolved")}`
							: t("common.loading")}
					</p>
				</div>
				<Button
					onClick={() => detectMutation.mutate()}
					disabled={detectMutation.isPending}
					className="bg-red-600 hover:bg-red-700 text-white border-none"
				>
					{detectMutation.isPending ? (
						<>
							<div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2" />
							{t("conflicts.detecting")}
						</>
					) : (
						<>
							<svg
								width="16"
								height="16"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								strokeWidth="2"
								strokeLinecap="round"
								strokeLinejoin="round"
								className="mr-2"
							>
								<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
								<line x1="12" y1="9" x2="12" y2="13" />
								<line x1="12" y1="17" x2="12.01" y2="17" />
							</svg>
							{t("conflicts.detectConflicts")}
						</>
					)}
				</Button>
			</div>

			{/* Detect result */}
			{detectMutation.isSuccess && detectMutation.data && (
				<div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-4">
					<p className="text-emerald-400 text-sm">
						{t("conflicts.detectedConflicts", {
							count: detectMutation.data.length,
						})}
					</p>
				</div>
			)}

			{detectMutation.isError && (
				<div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
					<p className="text-red-400 text-sm">
						{detectMutation.error instanceof Error
							? detectMutation.error.message
							: t("conflicts.failedToDetect")}
					</p>
				</div>
			)}

			{/* Error */}
			{error && (
				<div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
					<p className="text-red-400 text-sm">{t("conflicts.failedToLoad")}</p>
				</div>
			)}

			{/* Loading */}
			{isLoading && (
				<div className="flex items-center justify-center py-12">
					<div className="w-8 h-8 border-2 border-slate-600 border-t-orange-500 rounded-full animate-spin" />
				</div>
			)}

			{/* Summary cards */}
			{conflictsData && !isLoading && (
				<div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
					<div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
						<p className="text-2xl font-bold text-white">
							{conflictsData.total}
						</p>
						<p className="text-slate-400 text-sm">
							{t("conflicts.totalConflicts")}
						</p>
					</div>
					<div className="bg-slate-800 border border-amber-500/20 rounded-xl p-4">
						<p className="text-2xl font-bold text-amber-400">
							{unresolvedCount}
						</p>
						<p className="text-slate-400 text-sm">
							{t("conflicts.unresolved")}
						</p>
					</div>
					<div className="bg-slate-800 border border-emerald-500/20 rounded-xl p-4">
						<p className="text-2xl font-bold text-emerald-400">
							{resolvedCount}
						</p>
						<p className="text-slate-400 text-sm">{t("conflicts.resolved")}</p>
					</div>
				</div>
			)}

			{/* Table */}
			{conflictsData && !isLoading && (
				<div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
					<div className="overflow-x-auto">
						<table className="w-full text-sm" aria-label={t("conflicts.title")}>
							<thead>
								<tr className="border-b border-slate-700 bg-slate-800/50">
									<th
										scope="col"
										className="text-left text-slate-400 font-medium px-4 py-3"
									>
										{t("conflicts.element")}
									</th>
									<th
										scope="col"
										className="text-left text-slate-400 font-medium px-4 py-3"
									>
										{t("elements.type")}
									</th>
									<th
										scope="col"
										className="text-left text-slate-400 font-medium px-4 py-3"
									>
										{t("conflicts.sources")}
									</th>
									<th
										scope="col"
										className="text-left text-slate-400 font-medium px-4 py-3"
									>
										{t("conflicts.status")}
									</th>
									<th
										scope="col"
										className="text-left text-slate-400 font-medium px-4 py-3"
									>
										{t("conflicts.timestamp")}
									</th>
									<th
										scope="col"
										className="text-right text-slate-400 font-medium px-4 py-3"
									>
										{t("elements.actions")}
									</th>
								</tr>
							</thead>
							<tbody>
								{conflicts.length === 0 ? (
									<tr>
										<td colSpan={6} className="py-8">
											<EmptyState
												icon={
													<svg
														width="48"
														height="48"
														viewBox="0 0 24 24"
														fill="none"
														stroke="currentColor"
														strokeWidth="1.5"
														className="h-12 w-12 text-slate-600"
													>
														<line x1="12" y1="22" x2="12" y2="2" />
														<path d="M10 22a2 2 0 002-2V4a2 2 0 00-2-2h0a2 2 0 00-2 2v16a2 2 0 002 2h0z" />
													</svg>
												}
												title={t("conflicts.noConflictsDetected")}
												description=""
												action={{
													label: t("conflicts.detectConflicts"),
													onClick: () => detectMutation.mutate(),
												}}
											/>
										</td>
									</tr>
								) : (
									conflicts.map((conflict) => (
										<tr
											key={conflict.conflict_id}
											className={`border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors ${
												conflict.resolved ? "opacity-60" : ""
											}`}
										>
											<td className="px-4 py-3">
												<span className="text-xs font-mono text-orange-400">
													{conflict.element_id
														? `${conflict.element_id.slice(0, 12)}…`
														: "—"}
												</span>
											</td>
											<td className="px-4 py-3">
												<span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
													{conflict.conflict_type}
												</span>
											</td>
											<td className="px-4 py-3">
												<div className="text-xs text-slate-400">
													<span className="text-blue-400">
														{conflict.source_a}
													</span>
													{" vs "}
													<span className="text-emerald-400">
														{conflict.source_b}
													</span>
												</div>
											</td>
											<td className="px-4 py-3">
												{conflict.resolved ? (
													<span className="inline-flex items-center gap-1 text-xs text-emerald-400">
														<svg
															width="12"
															height="12"
															viewBox="0 0 24 24"
															fill="none"
															stroke="currentColor"
															strokeWidth="3"
															strokeLinecap="round"
															strokeLinejoin="round"
														>
															<polyline points="20 6 9 17 4 12" />
														</svg>
														{t("conflicts.resolved")}
													</span>
												) : (
													<span className="inline-flex items-center gap-1 text-xs text-amber-400">
														<span className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-pulse" />
														{t("conflicts.unresolved")}
													</span>
												)}
											</td>
											<td className="px-4 py-3 text-slate-400 text-xs">
												{conflict.timestamp
													? new Date(conflict.timestamp).toLocaleDateString()
													: "—"}
											</td>
											<td className="px-4 py-3 text-right">
												{!conflict.resolved && (
													<Button
														onClick={() =>
															setResolveTarget(conflict.conflict_id)
														}
														className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs rounded-lg transition-colors"
													>
														{t("conflicts.resolve")}
													</Button>
												)}
											</td>
										</tr>
									))
								)}
							</tbody>
						</table>
					</div>
				</div>
			)}

			{/* Resolve Modal */}
			{resolveTarget && (
				<div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
					<div className="bg-slate-800 border border-slate-700 rounded-xl max-w-md w-full p-6">
						<h3 className="text-lg font-semibold text-white mb-2">
							{t("conflicts.resolveConflict")}
						</h3>
						<p className="text-slate-400 text-sm mb-4">
							{t("conflicts.selectResolutionStrategy")}
						</p>

						{resolveMutation.isError && (
							<div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-4">
								<p className="text-red-400 text-sm">
									{resolveMutation.error instanceof Error
										? resolveMutation.error.message
										: t("conflicts.resolutionFailed")}
								</p>
							</div>
						)}

						<div className="space-y-3 mb-6">
							<RadioGroup
								value={resolveStrategy}
								onValueChange={setResolveStrategy}
								className="space-y-3"
							>
								<div className="flex items-start space-x-3 p-3 bg-slate-900/50 rounded-lg border border-slate-700 hover:border-red-500/30 transition-colors">
									<RadioGroupItem
										value="LAST_WRITE_WINS"
										id="last-write"
										className="mt-0.5 data-[state=checked]:border-red-500 data-[state=checked]:bg-red-500"
									/>
									<div className="space-y-1">
										<label
											htmlFor="last-write"
											className="text-sm text-white font-medium cursor-pointer"
										>
											{t("conflicts.lastWriteWins")}
										</label>
										<p className="text-xs text-slate-400">
											{t("conflicts.acceptMostRecent")}
										</p>
									</div>
								</div>
								<div className="flex items-start space-x-3 p-3 bg-slate-900/50 rounded-lg border border-slate-700 hover:border-red-500/30 transition-colors">
									<RadioGroupItem
										value="SEMANTIC_MERGE"
										id="semantic-merge"
										className="mt-0.5 data-[state=checked]:border-red-500 data-[state=checked]:bg-red-500"
									/>
									<div className="space-y-1">
										<label
											htmlFor="semantic-merge"
											className="text-sm text-white font-medium cursor-pointer"
										>
											{t("conflicts.semanticMerge")}
										</label>
										<p className="text-xs text-slate-400">
											{t("conflicts.intelligentMerge")}
										</p>
									</div>
								</div>
							</RadioGroup>
						</div>

						<div className="flex justify-end gap-3">
							<Button
								variant="outline"
								className="border-slate-600 text-slate-300"
								onClick={() => setResolveTarget(null)}
							>
								{t("common.cancel")}
							</Button>
							<Button
								onClick={() =>
									resolveMutation.mutate({
										id: resolveTarget,
										strategy: resolveStrategy,
									})
								}
								disabled={resolveMutation.isPending}
								className="bg-emerald-600 hover:bg-emerald-700 text-white border-none"
							>
								{resolveMutation.isPending
									? t("conflicts.resolving")
									: t("conflicts.resolve")}
							</Button>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}

export default Conflicts;
