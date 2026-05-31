import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useParams, Link, useNavigate } from 'react-router-dom';
import type { ElementUpdate } from '@/types';
import { useState } from 'react';

function ElementDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editMaterial, setEditMaterial] = useState('');
  const [editFireRating, setEditFireRating] = useState('');
  const [editDescription, setEditDescription] = useState('');

  const { data: element, isLoading, error } = useQuery({
    queryKey: ['element', id],
    queryFn: () => api.getElement(id!),
    enabled: !!id,
  });

  const { data: connectionsData } = useQuery({
    queryKey: ['element-connections', id],
    queryFn: () => api.getConnections({ element_id: id! }),
    enabled: !!id,
  });

  const connections = connectionsData?.items ?? [];

  const updateMutation = useMutation({
    mutationFn: (data: ElementUpdate) => api.updateElement(id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['element', id] });
      queryClient.invalidateQueries({ queryKey: ['elements'] });
      setIsEditing(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteElement(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['elements'] });
      navigate('/elements');
    },
  });

  const startEditing = () => {
    if (element?.properties) {
      setEditName(element.properties.name ?? '');
      setEditMaterial(element.properties.material ?? '');
      setEditFireRating(element.properties.fire_rating ?? '');
      setEditDescription(element.properties.description ?? '');
    }
    setIsEditing(true);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-8 h-8 border-2 border-slate-600 border-t-orange-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !element) {
    return (
      <div className="space-y-4">
        <Link
          to="/elements"
          className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          Back to Elements
        </Link>
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <p className="text-red-400 text-sm">
            {error instanceof Error ? error.message : 'Element not found'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link to="/elements" className="text-slate-400 hover:text-white transition-colors">
          Elements
        </Link>
        <span className="text-slate-600">/</span>
        <span className="text-white">{element.properties?.name ?? element.element_id}</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">
            {element.properties?.name ?? 'Unnamed Element'}
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            ID: {element.element_id} · Version {element.version}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={startEditing}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Edit
          </button>
          <button
            onClick={() => {
              if (confirm('Are you sure you want to delete this element?')) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="px-4 py-2 bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>

      {/* Properties */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Properties</h2>

        {isEditing ? (
          <div className="space-y-4">
            {updateMutation.isError && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                <p className="text-red-400 text-sm">
                  {updateMutation.error instanceof Error ? updateMutation.error.message : 'Failed to update'}
                </p>
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Name</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Material</label>
                <input
                  type="text"
                  value={editMaterial}
                  onChange={(e) => setEditMaterial(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Fire Rating</label>
                <input
                  type="text"
                  value={editFireRating}
                  onChange={(e) => setEditFireRating(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Description</label>
                <input
                  type="text"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:border-orange-500 focus:outline-none"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setIsEditing(false)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  updateMutation.mutate({
                    properties: {
                      name: editName,
                      material: editMaterial,
                      fire_rating: editFireRating,
                      description: editDescription,
                    },
                  });
                }}
                disabled={updateMutation.isPending}
                className="px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <PropertyRow label="Type" value={element.properties?.element_type} />
            <PropertyRow label="Name" value={element.properties?.name} />
            <PropertyRow label="Description" value={element.properties?.description} />
            <PropertyRow label="Material" value={element.properties?.material} />
            <PropertyRow label="Fire Rating" value={element.properties?.fire_rating} />
            <PropertyRow
              label="Height"
              value={element.properties?.height != null ? `${element.properties.height} m` : undefined}
            />
            <PropertyRow
              label="Width"
              value={element.properties?.width != null ? `${element.properties.width} m` : undefined}
            />
            <PropertyRow
              label="Load Bearing"
              value={element.properties?.load_bearing != null ? (element.properties.load_bearing ? 'Yes' : 'No') : undefined}
            />
            <PropertyRow label="Layer" value={element.properties?.layer} />
            <PropertyRow label="Revit Category" value={element.properties?.revit_category} />
            <PropertyRow label="Source File" value={element.source_file} />
            <PropertyRow label="AutoCAD Handle" value={element.autocad_handle} />
            <PropertyRow
              label="Revit Element ID"
              value={element.revit_element_id != null ? String(element.revit_element_id) : undefined}
            />
          </div>
        )}
      </div>

      {/* Geometry */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Geometry</h2>
        {element.geometry ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <PropertyRow label="Area" value={`${element.geometry.area.toFixed(2)} m²`} />
            <PropertyRow label="Perimeter" value={`${element.geometry.perimeter.toFixed(2)} m`} />
            <PropertyRow label="Closed Polyline" value={element.geometry.polyline_closed ? 'Yes' : 'No'} />
            <div className="sm:col-span-3">
              <PropertyRow
                label="Points"
                value={`${element.geometry.points.length} points`}
              />
              {element.geometry.points.length > 0 && (
                <div className="mt-2 max-h-48 overflow-y-auto custom-scrollbar bg-slate-900 rounded-lg p-3">
                  <pre className="text-xs text-slate-400">
                    {JSON.stringify(element.geometry.points, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        ) : (
          <p className="text-slate-500 text-sm">No geometry data available</p>
        )}
      </div>

      {/* Timestamps */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Timestamps</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <PropertyRow
            label="Created"
            value={element.created_timestamp ? new Date(element.created_timestamp).toLocaleString() : '—'}
          />
          <PropertyRow
            label="Last Modified"
            value={element.last_modified_timestamp ? new Date(element.last_modified_timestamp).toLocaleString() : '—'}
          />
          <PropertyRow label="Modified By" value={element.last_modified_by} />
        </div>
      </div>

      {/* Connections */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">
          Connections ({connections.length})
        </h2>
        {connections.length > 0 ? (
          <div className="space-y-2">
            {connections.map((conn) => (
              <div
                key={conn.connection_id}
                className="flex items-center gap-3 bg-slate-900/50 border border-slate-700/50 rounded-lg p-3"
              >
                <span className="text-orange-400 text-xs font-mono">
                  {conn.from_element_id === id ? '→' : '←'}
                </span>
                <Link
                  to={`/elements/${conn.from_element_id === id ? conn.to_element_id : conn.from_element_id}`}
                  className="text-sm text-white hover:text-orange-400 transition-colors"
                >
                  {conn.from_element_id === id ? conn.to_element_id : conn.from_element_id}
                </Link>
                <span className="text-xs text-slate-500 bg-slate-700 px-2 py-0.5 rounded">
                  {conn.relationship_type}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-slate-500 text-sm">No connections found</p>
        )}
      </div>
    </div>
  );
}

function PropertyRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <p className="text-xs text-slate-500 mb-0.5">{label}</p>
      <p className="text-sm text-white">{value ?? '—'}</p>
    </div>
  );
}

export default ElementDetail;
