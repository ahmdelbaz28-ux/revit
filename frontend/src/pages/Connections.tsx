import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { Link } from 'react-router-dom';
import type { ConnectionCreate } from '@/types';

function Connections() {
  const queryClient = useQueryClient();
  const [elementFilter, setElementFilter] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data: connectionsData, isLoading, error } = useQuery({
    queryKey: ['connections', elementFilter],
    queryFn: () => api.getConnections({ element_id: elementFilter || undefined }),
  });

  const connections = connectionsData?.items ?? [];

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteConnection(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connections'] });
      setDeleteTarget(null);
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Connections</h1>
          <p className="text-slate-400 text-sm mt-1">
            {connectionsData ? `${connectionsData.total} connections` : 'Loading...'}
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Create Connection
        </button>
      </div>

      {/* Filter */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={elementFilter}
          onChange={(e) => setElementFilter(e.target.value)}
          placeholder="Filter by element ID..."
          className="bg-slate-800 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none w-full sm:w-72"
        />
        {elementFilter && (
          <button
            onClick={() => setElementFilter('')}
            className="text-sm text-slate-400 hover:text-white"
          >
            ✕ Clear
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <p className="text-red-400 text-sm">Failed to load connections.</p>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-slate-600 border-t-orange-500 rounded-full animate-spin" />
        </div>
      )}

      {/* Table */}
      {connectionsData && !isLoading && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-800/50">
                  <th className="text-left text-slate-400 font-medium px-4 py-3">From</th>
                  <th className="text-left text-slate-400 font-medium px-4 py-3">To</th>
                  <th className="text-left text-slate-400 font-medium px-4 py-3">Type</th>
                  <th className="text-left text-slate-400 font-medium px-4 py-3">Parametric</th>
                  <th className="text-right text-slate-400 font-medium px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {connections.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-slate-500">
                      No connections found
                    </td>
                  </tr>
                ) : (
                  connections.map((conn) => (
                    <tr
                      key={conn.connection_id}
                      className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <Link
                          to={`/elements/${conn.from_element_id}`}
                          className="text-orange-400 hover:text-orange-300 text-xs font-mono"
                        >
                          {conn.from_element_id.slice(0, 12)}…
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          to={`/elements/${conn.to_element_id}`}
                          className="text-orange-400 hover:text-orange-300 text-xs font-mono"
                        >
                          {conn.to_element_id.slice(0, 12)}…
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-700 text-slate-300">
                          {conn.relationship_type}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {conn.is_parametric ? (
                          <span className="text-emerald-400 text-xs">Yes</span>
                        ) : (
                          <span className="text-slate-500 text-xs">No</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => setDeleteTarget(conn.connection_id)}
                          className="text-slate-400 hover:text-red-400 transition-colors"
                          title="Delete"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="3 6 5 6 21 6" />
                            <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <CreateConnectionModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false);
            queryClient.invalidateQueries({ queryKey: ['connections'] });
          }}
        />
      )}

      {/* Delete Confirmation */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-white mb-2">Delete Connection</h3>
            <p className="text-slate-400 text-sm mb-4">
              Are you sure you want to delete this connection?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteTarget)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ===== Create Connection Modal =====

function CreateConnectionModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [fromId, setFromId] = useState('');
  const [toId, setToId] = useState('');
  const [relationshipType, setRelationshipType] = useState('');
  const [isParametric, setIsParametric] = useState(false);

  const createMutation = useMutation({
    mutationFn: () => {
      const data: ConnectionCreate = {
        from_element_id: fromId,
        to_element_id: toId,
        relationship_type: relationshipType,
        is_parametric: isParametric,
      };
      return api.createConnection(data);
    },
    onSuccess,
  });

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-md w-full p-6">
        <h3 className="text-lg font-semibold text-white mb-4">Create Connection</h3>

        {createMutation.isError && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-4">
            <p className="text-red-400 text-sm">
              {createMutation.error instanceof Error
                ? createMutation.error.message
                : 'Failed to create connection'}
            </p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">From Element ID *</label>
            <input
              type="text"
              value={fromId}
              onChange={(e) => setFromId(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
              placeholder="Element UUID"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">To Element ID *</label>
            <input
              type="text"
              value={toId}
              onChange={(e) => setToId(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
              placeholder="Element UUID"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Relationship Type *</label>
            <input
              type="text"
              value={relationshipType}
              onChange={(e) => setRelationshipType(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
              placeholder="e.g., adjacent, connected, contains"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={isParametric}
              onChange={(e) => setIsParametric(e.target.checked)}
              className="rounded bg-slate-900 border-slate-600 text-orange-500 focus:ring-orange-500"
            />
            <span className="text-sm text-slate-300">Parametric</span>
          </label>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => createMutation.mutate()}
            disabled={!fromId || !toId || !relationshipType || createMutation.isPending}
            className="px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {createMutation.isPending ? 'Creating...' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default Connections;
