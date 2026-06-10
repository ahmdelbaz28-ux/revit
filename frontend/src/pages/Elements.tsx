import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { Link } from 'react-router-dom';
import type { ElementPropertiesCreate, ElementGeometryCreate, Element } from '@/types';

const ELEMENT_TYPES = [
  'wall',
  'door',
  'window',
  'room',
  'equipment',
  'mechanical',
  'electrical',
  'unknown',
] as const;

const PAGE_SIZE = 20;

function Elements() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Element | null>(null);

  // Fetch elements
  const { data, isLoading, error } = useQuery({
    queryKey: ['elements', page, typeFilter],
    queryFn: () =>
      api.getElements({
        page,
        page_size: PAGE_SIZE,
        element_type: typeFilter || undefined,
      }),
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteElement(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['elements'] });
      setDeleteTarget(null);
    },
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Elements</h1>
          <p className="text-slate-400 text-sm mt-1">
            {data ? `${data.total} total elements` : 'Loading...'}
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
          Create Element
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value);
            setPage(1);
          }}
          className="bg-slate-800 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
        >
          <option value="">All Types</option>
          {ELEMENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </option>
          ))}
        </select>
        {typeFilter && (
          <button
            onClick={() => {
              setTypeFilter('');
              setPage(1);
            }}
            className="text-sm text-slate-400 hover:text-white"
          >
            ✕ Clear filter
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <p className="text-red-400 text-sm">
            Failed to load elements. Make sure the backend is running.
          </p>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-slate-600 border-t-orange-500 rounded-full animate-spin" />
        </div>
      )}

      {/* Table */}
      {data && !isLoading && (
        <>
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-800/50">
                    <th className="text-left text-slate-400 font-medium px-4 py-3">Name</th>
                    <th className="text-left text-slate-400 font-medium px-4 py-3">Type</th>
                    <th className="text-left text-slate-400 font-medium px-4 py-3">Area</th>
                    <th className="text-left text-slate-400 font-medium px-4 py-3">Version</th>
                    <th className="text-left text-slate-400 font-medium px-4 py-3">Modified</th>
                    <th className="text-right text-slate-400 font-medium px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-center py-8 text-slate-500">
                        No elements found
                      </td>
                    </tr>
                  ) : (
                    data.items.map((element) => (
                      <tr
                        key={element.element_id}
                        className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <Link
                            to={`/elements/${element.element_id}`}
                            className="text-white hover:text-orange-400 font-medium transition-colors"
                          >
                            {element.properties?.name ?? 'Unnamed'}
                          </Link>
                        </td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-700 text-slate-300">
                            {element.properties?.element_type ?? 'unknown'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-300">
                          {element.geometry?.area != null
                            ? `${element.geometry.area.toFixed(2)} m²`
                            : '—'}
                        </td>
                        <td className="px-4 py-3 text-slate-300">
                          v{element.version}
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-xs">
                          {element.last_modified_timestamp ? new Date(element.last_modified_timestamp).toLocaleDateString() : '—'}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Link
                              to={`/elements/${element.element_id}`}
                              className="text-slate-400 hover:text-white transition-colors px-2 py-1"
                              title="View"
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                                <circle cx="12" cy="12" r="3" />
                              </svg>
                            </Link>
                            <button
                              onClick={() => setDeleteTarget(element)}
                              className="text-slate-400 hover:text-red-400 transition-colors px-2 py-1"
                              title="Delete"
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="3 6 5 6 21 6" />
                                <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                              </svg>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-400">
                Page {page} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1.5 bg-slate-700 text-white text-sm rounded-lg disabled:opacity-40 hover:bg-slate-600 transition-colors"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-3 py-1.5 bg-slate-700 text-white text-sm rounded-lg disabled:opacity-40 hover:bg-slate-600 transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <CreateElementModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false);
            queryClient.invalidateQueries({ queryKey: ['elements'] });
          }}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold text-white mb-2">Delete Element</h3>
            <p className="text-slate-400 text-sm mb-4">
              Are you sure you want to delete &quot;{deleteTarget.properties?.name ?? deleteTarget.element_id}&quot;? This action cannot be undone.
            </p>
            {deleteMutation.isError && (
              <p className="text-red-400 text-sm mb-3">
                Failed to delete: {deleteMutation.error instanceof Error ? deleteMutation.error.message : 'Unknown error'}
              </p>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteTarget.element_id)}
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

// ===== Create Element Modal =====

function CreateElementModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState('');
  const [elementType, setElementType] = useState<string>('wall');
  const [material, setMaterial] = useState('');
  const [fireRating, setFireRating] = useState('');
  const [height, setHeight] = useState('');
  const [width, setWidth] = useState('');
  const [loadBearing, setLoadBearing] = useState(false);
  const [description, setDescription] = useState('');

  const createMutation = useMutation({
    mutationFn: () => {
      const properties: ElementPropertiesCreate = {
        element_type: elementType,
        name,
        description: description || undefined,
        material: material || undefined,
        fire_rating: fireRating || undefined,
        height: height ? parseFloat(height) : undefined,
        width: width ? parseFloat(width) : undefined,
        load_bearing: loadBearing,
      };

      // Default geometry with empty points
      const geometry: ElementGeometryCreate = {
        points: [],
        polyline_closed: false,
      };

      return api.createElement({ properties, geometry });
    },
    onSuccess,
  });

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto custom-scrollbar">
        <h3 className="text-lg font-semibold text-white mb-4">Create Element</h3>

        {createMutation.isError && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-4">
            <p className="text-red-400 text-sm">
              {createMutation.error instanceof Error
                ? createMutation.error.message
                : 'Failed to create element'}
            </p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
              placeholder="Element name"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Type *</label>
            <select
              value={elementType}
              onChange={(e) => setElementType(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
            >
              {ELEMENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type.charAt(0).toUpperCase() + type.slice(1)}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Height</label>
              <input
                type="number"
                value={height}
                onChange={(e) => setHeight(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
                placeholder="m"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Width</label>
              <input
                type="number"
                value={width}
                onChange={(e) => setWidth(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
                placeholder="m"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Material</label>
              <input
                type="text"
                value={material}
                onChange={(e) => setMaterial(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
                placeholder="e.g., Concrete"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Fire Rating</label>
              <input
                type="text"
                value={fireRating}
                onChange={(e) => setFireRating(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
                placeholder="e.g., 2HR"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none resize-none"
              placeholder="Optional description"
            />
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={loadBearing}
              onChange={(e) => setLoadBearing(e.target.checked)}
              className="rounded bg-slate-900 border-slate-600 text-orange-500 focus:ring-orange-500"
            />
            <span className="text-sm text-slate-300">Load Bearing</span>
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
            disabled={!name || createMutation.isPending}
            className="px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {createMutation.isPending ? 'Creating...' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default Elements;
