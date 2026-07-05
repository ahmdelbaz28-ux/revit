/**
 * useApi.ts - React hooks wrapping the digitalTwinApi client
 * Uses useState/useEffect for data fetching with loading/error states
 */
import { useCallback, useEffect, useState } from "react";
import type {
	ApiResponse,
	Connection,
	CreateDeviceInput,
	CreateProjectInput,
	Device,
	HealthStatus,
	PaginatedResponse,
	Project,
	Report,
} from "@/services/digitalTwinApi";
import { api } from "@/services/digitalTwinApi";

// ============================================================================
// Generic hook result type
// ============================================================================

interface UseApiResult<T> {
	data: T | null;
	loading: boolean;
	error: string | null;
	refetch: () => void;
}

// ============================================================================
// useHealth - Fetch backend health status
// ============================================================================

export function useHealth(): UseApiResult<HealthStatus> & {
	connected: boolean;
} {
	const [data, setData] = useState<HealthStatus | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [refreshKey, setRefreshKey] = useState(0);

	const refetch = useCallback(() => setRefreshKey((k) => k + 1), []);

	useEffect(() => {
		let cancelled = false;
		setLoading(true);
		setError(null);

		api
			.healthCheck()
			.then((res: ApiResponse<HealthStatus>) => {
				if (cancelled) return;
				setLoading(false);
				if (res.success && res.data) {
					setData(res.data);
					setError(null);
				} else {
					setData(null);
					setError(res.error || "Health check failed");
				}
			})
			.catch((err: unknown) => {
				if (cancelled) return;
				setLoading(false);
				setData(null);
				setError(err instanceof Error ? err.message : "Network error");
			});

		return () => {
			cancelled = true;
		};
	}, [refreshKey]);

	return { data, loading, error, refetch, connected: data?.status === "ok" };
}

// ============================================================================
// useProjects - Fetch all projects
// ============================================================================

export function useProjects(): UseApiResult<Project[]> {
	const [data, setData] = useState<Project[] | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [refreshKey, setRefreshKey] = useState(0);

	const refetch = useCallback(() => setRefreshKey((k) => k + 1), []);

	useEffect(() => {
		let cancelled = false;
		setLoading(true);
		setError(null);

		api
			.getProjects()
			.then((res: ApiResponse<PaginatedResponse<Project>>) => {
				if (cancelled) return;
				setLoading(false);
				if (res.success && res.data) {
					setData(res.data.data);
					setError(null);
				} else {
					setData(null);
					setError(res.error || "Failed to fetch projects");
				}
			})
			.catch((err: unknown) => {
				if (cancelled) return;
				setLoading(false);
				setData(null);
				setError(err instanceof Error ? err.message : "Network error");
			});

		return () => {
			cancelled = true;
		};
	}, [refreshKey]);

	return { data, loading, error, refetch };
}

// ============================================================================
// useProject - Fetch a single project
// ============================================================================

export function useProject(id: string | null): UseApiResult<Project> {
	const [data, setData] = useState<Project | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [refreshKey, setRefreshKey] = useState(0);

	const refetch = useCallback(() => setRefreshKey((k) => k + 1), []);

	useEffect(() => {
		if (!id) {
			setData(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		api
			.getProject(id)
			.then((res: ApiResponse<Project>) => {
				if (cancelled) return;
				setLoading(false);
				if (res.success && res.data) {
					setData(res.data);
					setError(null);
				} else {
					setData(null);
					setError(res.error || "Failed to fetch project");
				}
			})
			.catch((err: unknown) => {
				if (cancelled) return;
				setLoading(false);
				setData(null);
				setError(err instanceof Error ? err.message : "Network error");
			});

		return () => {
			cancelled = true;
		};
	}, [id, refreshKey]);

	return { data, loading, error, refetch };
}

// ============================================================================
// useDevices - Fetch devices for a project
// ============================================================================

export function useDevices(projectId: string | null): UseApiResult<Device[]> {
	const [data, setData] = useState<Device[] | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [refreshKey, setRefreshKey] = useState(0);

	const refetch = useCallback(() => setRefreshKey((k) => k + 1), []);

	useEffect(() => {
		if (!projectId) {
			setData(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		api
			.getDevices(projectId)
			.then((res: ApiResponse<PaginatedResponse<Device>>) => {
				if (cancelled) return;
				setLoading(false);
				if (res.success && res.data) {
					setData(res.data.data);
					setError(null);
				} else {
					setData(null);
					setError(res.error || "Failed to fetch devices");
				}
			})
			.catch((err: unknown) => {
				if (cancelled) return;
				setLoading(false);
				setData(null);
				setError(err instanceof Error ? err.message : "Network error");
			});

		return () => {
			cancelled = true;
		};
	}, [projectId, refreshKey]);

	return { data, loading, error, refetch };
}

// ============================================================================
// useConnections - Fetch connections for a project
// ============================================================================

export function useConnections(
	projectId: string | null,
): UseApiResult<Connection[]> {
	const [data, setData] = useState<Connection[] | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [refreshKey, setRefreshKey] = useState(0);

	const refetch = useCallback(() => setRefreshKey((k) => k + 1), []);

	useEffect(() => {
		if (!projectId) {
			setData(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		api
			.getConnections(projectId)
			.then((res: ApiResponse<PaginatedResponse<Connection>>) => {
				if (cancelled) return;
				setLoading(false);
				if (res.success && res.data) {
					setData(res.data.data);
					setError(null);
				} else {
					setData(null);
					setError(res.error || "Failed to fetch connections");
				}
			})
			.catch((err: unknown) => {
				if (cancelled) return;
				setLoading(false);
				setData(null);
				setError(err instanceof Error ? err.message : "Network error");
			});

		return () => {
			cancelled = true;
		};
	}, [projectId, refreshKey]);

	return { data, loading, error, refetch };
}

// ============================================================================
// useReports - Fetch reports for a project
// ============================================================================

export function useReports(projectId: string | null): UseApiResult<Report[]> {
	const [data, setData] = useState<Report[] | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [refreshKey, setRefreshKey] = useState(0);

	const refetch = useCallback(() => setRefreshKey((k) => k + 1), []);

	useEffect(() => {
		if (!projectId) {
			setData(null);
			setLoading(false);
			return;
		}

		let cancelled = false;
		setLoading(true);
		setError(null);

		api
			.getReports(projectId)
			.then((res: ApiResponse<PaginatedResponse<Report>>) => {
				if (cancelled) return;
				setLoading(false);
				if (res.success && res.data) {
					setData(res.data.data);
					setError(null);
				} else {
					setData(null);
					setError(res.error || "Failed to fetch reports");
				}
			})
			.catch((err: unknown) => {
				if (cancelled) return;
				setLoading(false);
				setData(null);
				setError(err instanceof Error ? err.message : "Network error");
			});

		return () => {
			cancelled = true;
		};
	}, [projectId, refreshKey]);

	return { data, loading, error, refetch };
}

// ============================================================================
// Mutation hooks
// ============================================================================

interface UseMutationResult<TArgs, TResult> {
	mutate: (args: TArgs) => Promise<TResult | null>;
	loading: boolean;
	error: string | null;
	data: TResult | null;
	reset: () => void;
}

// useCreateProject - Mutation hook for creating a project
export function useCreateProject(): UseMutationResult<
	CreateProjectInput,
	Project
> & { refetch: () => void } {
	const [data, setData] = useState<Project | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const mutate = useCallback(
		async (input: CreateProjectInput): Promise<Project | null> => {
			setLoading(true);
			setError(null);
			try {
				const res = await api.createProject(input);
				setLoading(false);
				if (res.success && res.data) {
					setData(res.data);
					return res.data;
				} else {
					setError(res.error || "Failed to create project");
					return null;
				}
			} catch (err: unknown) {
				setLoading(false);
				const msg = err instanceof Error ? err.message : "Network error";
				setError(msg);
				return null;
			}
		},
		[],
	);

	const reset = useCallback(() => {
		setData(null);
		setLoading(false);
		setError(null);
	}, []);

	// Alias refetch as reset for consistency
	return { mutate, loading, error, data, reset, refetch: reset };
}

// useCreateDevice - Mutation hook for creating a device
export function useCreateDevice(): UseMutationResult<
	{ projectId: string; data: CreateDeviceInput },
	Device
> {
	const [data, setData] = useState<Device | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const mutate = useCallback(
		async (args: {
			projectId: string;
			data: CreateDeviceInput;
		}): Promise<Device | null> => {
			setLoading(true);
			setError(null);
			try {
				const res = await api.createDevice(args.projectId, args.data);
				setLoading(false);
				if (res.success && res.data) {
					setData(res.data);
					return res.data;
				} else {
					setError(res.error || "Failed to create device");
					return null;
				}
			} catch (err: unknown) {
				setLoading(false);
				const msg = err instanceof Error ? err.message : "Network error";
				setError(msg);
				return null;
			}
		},
		[],
	);

	const reset = useCallback(() => {
		setData(null);
		setLoading(false);
		setError(null);
	}, []);

	return { mutate, loading, error, data, reset };
}

// useDeleteProject - Mutation hook for deleting a project
export function useDeleteProject(): UseMutationResult<string, void> & {
	refetch: () => void;
} {
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const mutate = useCallback(async (id: string): Promise<void | null> => {
		setLoading(true);
		setError(null);
		try {
			const res = await api.deleteProject(id);
			setLoading(false);
			if (res.success) {
				return undefined;
			} else {
				setError(res.error || "Failed to delete project");
				return null;
			}
		} catch (err: unknown) {
			setLoading(false);
			const msg = err instanceof Error ? err.message : "Network error";
			setError(msg);
			return null;
		}
	}, []);

	const reset = useCallback(() => {
		setLoading(false);
		setError(null);
	}, []);

	return { mutate, loading, error, data: null, reset, refetch: reset };
}

// useSyncProject - Mutation hook for syncing a project
export function useSyncProject(): UseMutationResult<string, unknown> {
	const [data, setData] = useState<unknown>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const mutate = useCallback(
		async (projectId: string): Promise<unknown | null> => {
			setLoading(true);
			setError(null);
			try {
				const res = await api.syncProject(projectId);
				setLoading(false);
				if (res.success) {
					setData(res.data);
					return res.data;
				} else {
					setError(res.error || "Failed to sync project");
					return null;
				}
			} catch (err: unknown) {
				setLoading(false);
				const msg = err instanceof Error ? err.message : "Network error";
				setError(msg);
				return null;
			}
		},
		[],
	);

	const reset = useCallback(() => {
		setData(null);
		setLoading(false);
		setError(null);
	}, []);

	return { mutate, loading, error, data, reset };
}

// useGenerateReport - Mutation hook for generating a report
export function useGenerateReport(): UseMutationResult<
	{
		projectId: string;
		data: { type: string; execution_params: Record<string, unknown> };
	},
	Report
> {
	const [data, setData] = useState<Report | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const mutate = useCallback(
		async (args: {
			projectId: string;
			data: { type: string; execution_params: Record<string, unknown> };
		}): Promise<Report | null> => {
			setLoading(true);
			setError(null);
			try {
				const res = await api.generateReport(args.projectId, args.data);
				setLoading(false);
				if (res.success && res.data) {
					setData(res.data);
					return res.data;
				} else {
					setError(res.error || "Failed to generate report");
					return null;
				}
			} catch (err: unknown) {
				setLoading(false);
				const msg = err instanceof Error ? err.message : "Network error";
				setError(msg);
				return null;
			}
		},
		[],
	);

	const reset = useCallback(() => {
		setData(null);
		setLoading(false);
		setError(null);
	}, []);

	return { mutate, loading, error, data, reset };
}
