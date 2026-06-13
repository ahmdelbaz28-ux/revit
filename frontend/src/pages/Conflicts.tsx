import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

function Conflicts() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [resolveTarget, setResolveTarget] = useState<string | null>(null);
  const [resolveStrategy, setResolveStrategy] = useState('LAST_WRITE_WINS');

  const { data: conflictsData, isLoading, error } = useQuery({
    queryKey: ['conflicts'],
    queryFn: () => api.getConflicts(),
  });

  const conflicts = conflictsData?.items ?? [];

  const detectMutation = useMutation({
    mutationFn: () => api.detectConflicts(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conflicts'] });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: ({ id, strategy }: { id: string; strategy: string }) =>
      api.resolveConflict(id, strategy),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conflicts'] });
      setResolveTarget(null);
    },
  });

  const resolvedCount = conflicts?.filter((c) => c.resolved).length ?? 0;
  const unresolvedCount = conflicts ? conflicts.length - resolvedCount : 0;

  return (
    <div className="space-y-6" aria-label={t('conflicts.title')}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">{t('conflicts.title')}</h1>
          <p className="text-slate-400 text-sm mt-1">
            {conflicts
              ? `${unresolvedCount} unresolved / ${resolvedCount} resolved`
              : 'Loading...'}
          </p>
        </div>
        <button
          onClick={() => detectMutation.mutate()}
          disabled={detectMutation.isPending}
          className="inline-flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
        >
          {detectMutation.isPending ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Detecting...
            </>
          ) : (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              Detect Conflicts
            </>
          )}
        </button>
      </div>

      {/* Detect result */}
      {detectMutation.isSuccess && detectMutation.data && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-4">
          <p className="text-emerald-400 text-sm">
            Detected {detectMutation.data.length} conflicts
          </p>
        </div>
      )}

      {detectMutation.isError && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <p className="text-red-400 text-sm">
            {detectMutation.error instanceof Error ? detectMutation.error.message : 'Failed to detect conflicts'}
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <p className="text-red-400 text-sm">Failed to load conflicts.</p>
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
            <p className="text-2xl font-bold text-white">{conflictsData.total}</p>
            <p className="text-slate-400 text-sm">Total Conflicts</p>
          </div>
          <div className="bg-slate-800 border border-amber-500/20 rounded-xl p-4">
            <p className="text-2xl font-bold text-amber-400">{unresolvedCount}</p>
            <p className="text-slate-400 text-sm">Unresolved</p>
          </div>
          <div className="bg-slate-800 border border-emerald-500/20 rounded-xl p-4">
            <p className="text-2xl font-bold text-emerald-400">{resolvedCount}</p>
            <p className="text-slate-400 text-sm">Resolved</p>
          </div>
        </div>
      )}

      {/* Table */}
      {conflictsData && !isLoading && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" aria-label={t('conflicts.title')}>
              <thead>
                <tr className="border-b border-slate-700 bg-slate-800/50">
                  <th scope="col" className="text-left text-slate-400 font-medium px-4 py-3">Element</th>
                  <th scope="col" className="text-left text-slate-400 font-medium px-4 py-3">Type</th>
                  <th scope="col" className="text-left text-slate-400 font-medium px-4 py-3">Sources</th>
                  <th scope="col" className="text-left text-slate-400 font-medium px-4 py-3">Status</th>
                  <th scope="col" className="text-left text-slate-400 font-medium px-4 py-3">Timestamp</th>
                  <th scope="col" className="text-right text-slate-400 font-medium px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {conflicts.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-slate-500">
                      No conflicts detected
                    </td>
                  </tr>
                ) : (
                  conflicts.map((conflict) => (
                    <tr
                      key={conflict.conflict_id}
                      className={`border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors ${
                        conflict.resolved ? 'opacity-60' : ''
                      }`}
                    >
                      <td className="px-4 py-3">
                        <span className="text-xs font-mono text-orange-400">
                          {conflict.element_id ? `${conflict.element_id.slice(0, 12)}…` : '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                          {conflict.conflict_type}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-xs text-slate-400">
                          <span className="text-blue-400">{conflict.source_a}</span>
                          {' vs '}
                          <span className="text-emerald-400">{conflict.source_b}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {conflict.resolved ? (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-400">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                            Resolved
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-400">
                            <span className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-pulse" />
                            Unresolved
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-xs">
                        {conflict.timestamp ? new Date(conflict.timestamp).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {!conflict.resolved && (
                          <button
                            onClick={() => setResolveTarget(conflict.conflict_id)}
                            className="px-3 py-1 bg-emerald-600/20 hover:bg-emerald-600 text-emerald-400 hover:text-white text-xs font-medium rounded-lg transition-colors"
                          >
                            Resolve
                          </button>
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
            <h3 className="text-lg font-semibold text-white mb-2">Resolve Conflict</h3>
            <p className="text-slate-400 text-sm mb-4">
              Select a resolution strategy for this conflict.
            </p>

            {resolveMutation.isError && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-4">
                <p className="text-red-400 text-sm">
                  {resolveMutation.error instanceof Error ? resolveMutation.error.message : 'Failed to resolve'}
                </p>
              </div>
            )}

            <div className="space-y-3 mb-6">
              <label className="flex items-center gap-3 cursor-pointer p-3 bg-slate-900/50 rounded-lg border border-slate-700 hover:border-orange-500/30 transition-colors">
                <input
                  type="radio"
                  name="strategy"
                  value="LAST_WRITE_WINS"
                  checked={resolveStrategy === 'LAST_WRITE_WINS'}
                  onChange={() => setResolveStrategy('LAST_WRITE_WINS')}
                  className="text-orange-500 focus:ring-orange-500"
                />
                <div>
                  <p className="text-sm text-white font-medium">Last Write Wins</p>
                  <p className="text-xs text-slate-400">Accept the most recent change</p>
                </div>
              </label>
              <label className="flex items-center gap-3 cursor-pointer p-3 bg-slate-900/50 rounded-lg border border-slate-700 hover:border-orange-500/30 transition-colors">
                <input
                  type="radio"
                  name="strategy"
                  value="SEMANTIC_MERGE"
                  checked={resolveStrategy === 'SEMANTIC_MERGE'}
                  onChange={() => setResolveStrategy('SEMANTIC_MERGE')}
                  className="text-orange-500 focus:ring-orange-500"
                />
                <div>
                  <p className="text-sm text-white font-medium">Semantic Merge</p>
                  <p className="text-xs text-slate-400">Intelligently merge both changes</p>
                </div>
              </label>
            </div>

            <div className="flex justify-end gap-3">
              <button
                onClick={() => setResolveTarget(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  resolveMutation.mutate({ id: resolveTarget, strategy: resolveStrategy })
                }
                disabled={resolveMutation.isPending}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {resolveMutation.isPending ? 'Resolving...' : 'Resolve'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Conflicts;
