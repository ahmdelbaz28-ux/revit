
/**
 * useApi.ts - React hooks wrapping the digitalTwinApi client
 * Uses useState/useEffect for data fetching with loading/error states
 *
 * V222: Refactored to eliminate duplicated fetch/mutation patterns.
 * All hooks now delegate to useAsyncResource / useAsyncMutation.
 *
 * V244 DEPRECATED: This module uses a custom useState/useEffect pattern for
 * data fetching. The project has adopted React Query (@tanstack/react-query)
 * as the canonical data-fetching layer (used by Connections, Projects,
 * Elements, Conflicts pages). New code should use React Query's `useQuery`
 * and `useMutation` hooks instead of this module.
 *
 * Migration guide:
 *   - useProjects() → useQuery({ queryKey: ['projects'], queryFn: api.getProjects })
 *   - useCreateProject() → useMutation({ mutationFn: api.createProject })
 *   - useHealth() → useQuery({ queryKey: ['health'], queryFn: api.getHealth, refetchInterval: 30000 })
 *
 * This module will be removed in v2.0 after all pages migrate to React Query.
 *
 * @deprecated Use @tanstack/react-query instead. See migration guide above.
 */
import { useCallback, useEffect, useRef, useState } from "react";
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
// Generic result types
// ============================================================================

interface UseApiResult<T> {
        data: T | null;
        loading: boolean;
        error: string | null;
        refetch: () => void;
}

interface UseMutationResult<TArgs, TResult> {
        mutate: (args: TArgs) => Promise<TResult | null>;
        loading: boolean;
        error: string | null;
        data: TResult | null;
        reset: () => void;
}

// ============================================================================
// Generic async resource hook — eliminates fetch-pattern duplication
// ============================================================================

function useAsyncResource<T, TDep = string | null>(
        fetcher: () => Promise<ApiResponse<T>>,
        dependencies: TDep[],
        errorMessage: string,
        initialLoading: boolean = false,
        enabled: boolean = true,
): UseApiResult<T> {
        const [data, setData] = useState<T | null>(null);
        const [loading, setLoading] = useState(initialLoading);
        const [error, setError] = useState<string | null>(null);
        const [_refreshKey, setRefreshKey] = useState(0);

        // V256: requestIdRef prevents stale data from overwriting current data.
        // Each effect run increments the ID; the closure captures it.
        // When the response arrives, we check if it's still current.
        const requestIdRef = useRef(0);

        const refetch = useCallback(() => setRefreshKey((k) => k + 1), []);

        useEffect(() => {
                const currentRequestId = ++requestIdRef.current;

                if (!enabled) {
                        setData(null);
                        setLoading(false);
                        return;
                }

                setLoading(true);
                setError(null);

                fetcher()
                        .then((res) => {
                                if (requestIdRef.current !== currentRequestId) return;
                                setLoading(false);
                                if (res.success && res.data) {
                                        setData(res.data);
                                        setError(null);
                                } else {
                                        setData(null);
                                        setError(res.error || errorMessage);
                                }
                        })
                        .catch((err: unknown) => {
                                if (requestIdRef.current !== currentRequestId) return;
                                setLoading(false);
                                setData(null);
                                setError(err instanceof Error ? err.message : "Network error");
                        });

                return () => {
                        requestIdRef.current++;
                };
                // eslint-disable-next-line react-hooks/exhaustive-deps
        }, [...dependencies, _refreshKey]);

        return { data, loading, error, refetch };
}

// ============================================================================
// Generic async mutation hook — eliminates mutation-pattern duplication
// ============================================================================

function useAsyncMutation<TArgs, TResult>(
        mutator: (args: TArgs) => Promise<ApiResponse<TResult>>,
        errorMessage: string,
): UseMutationResult<TArgs, TResult> {
        const [data, setData] = useState<TResult | null>(null);
        const [loading, setLoading] = useState(false);
        const [error, setError] = useState<string | null>(null);

        const mutate = useCallback(
                async (args: TArgs): Promise<TResult | null> => {
                        setLoading(true);
                        setError(null);
                        try {
                                const res = await mutator(args);
                                setLoading(false);
                                if (res.success && res.data !== undefined && res.data !== null) {
                                        setData(res.data);
                                        return res.data;
                                }
                                if (res.success) {
                                        // Success but no data (e.g. delete operation)
                                        return null;
                                }
                                setError(res.error || errorMessage);
                                return null;
                        } catch (err: unknown) {
                                setLoading(false);
                                setError(err instanceof Error ? err.message : "Network error");  // NOSONAR: typescript:S6754
                                return null;
                        }
                },
                // eslint-disable-next-line react-hooks/exhaustive-deps
                [],
        );

        const reset = useCallback(() => {
                setData(null);
                setLoading(false);
                setError(null);
        }, []);

        return { mutate, loading, error, data, reset };
}

// ============================================================================
// Query hooks
// ============================================================================

export function useHealth(): UseApiResult<HealthStatus> & {
        connected: boolean;
} {
        const result = useAsyncResource<HealthStatus>(
                () => api.healthCheck(),
                [],
                "Health check failed",
                true,
        );
        return { ...result, connected: result.data?.status === "ok" };
}

export function useProjects(): UseApiResult<Project[]> {
        // Unwrap paginated response
        const [data, setData] = useState<Project[] | null>(null);
        const resource = useAsyncResource<PaginatedResponse<Project>>(
                () => api.getProjects(),
                [],
                "Failed to fetch projects",
                true,
        );
        useEffect(() => {
                setData(resource.data?.data ?? null);
        }, [resource.data]);
        return { ...resource, data };
}

export function useProject(id: string | null): UseApiResult<Project> {
        return useAsyncResource<Project>(
                () => api.getProject(id!),
                [id],  // NOSONAR: typescript:S6754
                "Failed to fetch project",
                false,
                id !== null,
        );
}

export function useDevices(projectId: string | null): UseApiResult<Device[]> {
        const [data, setData] = useState<Device[] | null>(null);
        const resource = useAsyncResource<PaginatedResponse<Device>>(
                () => api.getDevices(projectId!),
                [projectId],
                "Failed to fetch devices",
                false,
                projectId !== null,
        );
        useEffect(() => {
                setData(resource.data?.data ?? null);
        }, [resource.data]);
        return { ...resource, data };
}

export function useConnections(
        projectId: string | null,
): UseApiResult<Connection[]> {
        const [data, setData] = useState<Connection[] | null>(null);
        const resource = useAsyncResource<PaginatedResponse<Connection>>(
                () => api.getConnections(projectId!),
                [projectId],
                "Failed to fetch connections",
                false,
                projectId !== null,
        );
        useEffect(() => {
                setData(resource.data?.data ?? null);
        }, [resource.data]);
        return { ...resource, data };
}

export function useReports(projectId: string | null): UseApiResult<Report[]> {
        const [data, setData] = useState<Report[] | null>(null);
        const resource = useAsyncResource<PaginatedResponse<Report>>(
                () => api.getReports(projectId!),
                [projectId],
                "Failed to fetch reports",
                false,
                projectId !== null,
        );
        useEffect(() => {
                setData(resource.data?.data ?? null);
        }, [resource.data]);
        return { ...resource, data };
}

// ============================================================================
// Mutation hooks
// ============================================================================

export function useCreateProject(): UseMutationResult<
        CreateProjectInput,
        Project
> & { refetch: () => void } {
        const mutation = useAsyncMutation<CreateProjectInput, Project>(
                (input) => api.createProject(input),
                "Failed to create project",
        );
        return { ...mutation, refetch: mutation.reset };
}

export function useCreateDevice(): UseMutationResult<
        { projectId: string; data: CreateDeviceInput },
        Device
> {
        return useAsyncMutation<{ projectId: string; data: CreateDeviceInput }, Device>(
                (args) => api.createDevice(args.projectId, args.data),
                "Failed to create device",
        );
}

export function useDeleteProject(): UseMutationResult<string, void> & {
        refetch: () => void;
} {
        const mutation = useAsyncMutation<string, void>(
                (id) => api.deleteProject(id),
                "Failed to delete project",
        );
        return { ...mutation, data: null, refetch: mutation.reset };
}

export function useSyncProject(): UseMutationResult<string, unknown> {
        return useAsyncMutation<string, unknown>(
                (projectId) => api.syncProject(projectId),
                "Failed to sync project",
        );
}

export function useGenerateReport(): UseMutationResult<
        {
                projectId: string;
                data: { type: string; execution_params: Record<string, unknown> };
        },
        Report
> {
        return useAsyncMutation<
                {
                        projectId: string;
                        data: { type: string; execution_params: Record<string, unknown> };
                },
                Report
        >((args) => api.generateReport(args.projectId, args.data), "Failed to generate report");
}
