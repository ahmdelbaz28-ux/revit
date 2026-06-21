/**
 * useApi.ts - React hooks wrapping the digitalTwinApi client
 *
 * P1.2 FIX (2026-06-20): migrated from useState/useEffect pattern to
 * @tanstack/react-query. The previous implementation had 482 lines of
 * boilerplate — each hook repeated the same 30-line pattern (useState
 * × 3 + useCallback refetch + useEffect with cancelled flag + then/
 * catch with success/error branching). React Query handles all of
 * this in 3 lines per hook.
 *
 * Backward compatibility: the hook return shape ({ data, loading,
 * error, refetch }) is PRESERVED so existing callers (DashboardPage,
 * ProjectsPage, ReportsPage, ReportGeneratorPage, SettingsPage,
 * App.tsx) do not need to change.
 *
 * React Query v5 mapping:
 *   data    = query.data
 *   loading = query.isLoading (true only on first load, not refetch)
 *   error   = query.error?.message ?? null
 *   refetch = query.refetch
 *
 * For mutations, useMutation is used. The hook returns:
 *   mutate  = mutation.mutateAsync
 *   loading = mutation.isPending
 *   error   = mutation.error?.message ?? null
 *   data    = mutation.data
 *   reset   = mutation.reset
 *
 * React Query is already configured in main.tsx (QueryClientProvider
 * wraps the App). The QueryClient has staleTime: 60s and refetchOnWindowFocus
 * enabled, so API calls are automatically cached and refreshed.
 */
import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/services/digitalTwinApi';
import type {
  Project,
  Device,
  Connection,
  Report,
  HealthStatus,
  PaginatedResponse,
  CreateProjectInput,
  CreateDeviceInput,
  ApiResponse,
} from '@/services/digitalTwinApi';

// ============================================================================
// Generic hook result type (PRESERVED for backward compatibility)
// ============================================================================

interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

// Helper: extract error message from React Query error
function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  return fallback;
}

// Helper: unwrap ApiResponse<T> — returns data on success, throws on failure
// (React Query catches the throw and exposes it via .error)
async function unwrap<T>(promise: Promise<ApiResponse<T>>, fallbackMsg: string): Promise<T> {
  const res = await promise;
  if (res.success && res.data !== undefined) {
    return res.data;
  }
  throw new Error(res.error || fallbackMsg);
}

// Helper: unwrap ApiResponse<PaginatedResponse<T>> → T[]
async function unwrapPaginated<T>(
  promise: Promise<ApiResponse<PaginatedResponse<T>>>,
  fallbackMsg: string,
): Promise<T[]> {
  const res = await promise;
  if (res.success && res.data) {
    return res.data.data;
  }
  throw new Error(res.error || fallbackMsg);
}

// ============================================================================
// useHealth - Fetch backend health status
// ============================================================================

export function useHealth(): UseApiResult<HealthStatus> & { connected: boolean } {
  const query = useQuery({
    queryKey: ['health'],
    queryFn: () => unwrap(api.healthCheck(), 'Health check failed'),
    refetchInterval: 30000, // Poll every 30s for health
    staleTime: 10000, // Health is stale after 10s
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? errorMessage(query.error, 'Health check failed') : null,
    refetch: () => { void query.refetch(); },
    connected: query.data?.status === 'ok',
  };
}

// ============================================================================
// useProjects - Fetch all projects
// ============================================================================

export function useProjects(): UseApiResult<Project[]> {
  const query = useQuery({
    queryKey: ['projects'],
    queryFn: () => unwrapPaginated(api.getProjects(), 'Failed to fetch projects'),
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? errorMessage(query.error, 'Failed to fetch projects') : null,
    refetch: () => { void query.refetch(); },
  };
}

// ============================================================================
// useProject - Fetch a single project
// ============================================================================

export function useProject(id: string | null): UseApiResult<Project> {
  const query = useQuery({
    queryKey: ['project', id],
    queryFn: () => unwrap(api.getProject(id!), 'Failed to fetch project'),
    enabled: !!id, // Don't fetch if id is null
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? errorMessage(query.error, 'Failed to fetch project') : null,
    refetch: () => { void query.refetch(); },
  };
}

// ============================================================================
// useDevices - Fetch devices for a project
// ============================================================================

export function useDevices(projectId: string | null): UseApiResult<Device[]> {
  const query = useQuery({
    queryKey: ['devices', projectId],
    queryFn: () => unwrapPaginated(api.getDevices(projectId!), 'Failed to fetch devices'),
    enabled: !!projectId,
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? errorMessage(query.error, 'Failed to fetch devices') : null,
    refetch: () => { void query.refetch(); },
  };
}

// ============================================================================
// useConnections - Fetch connections for a project
// ============================================================================

export function useConnections(projectId: string | null): UseApiResult<Connection[]> {
  const query = useQuery({
    queryKey: ['connections', projectId],
    queryFn: () => unwrapPaginated(api.getConnections(projectId!), 'Failed to fetch connections'),
    enabled: !!projectId,
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? errorMessage(query.error, 'Failed to fetch connections') : null,
    refetch: () => { void query.refetch(); },
  };
}

// ============================================================================
// useReports - Fetch reports for a project
// ============================================================================

export function useReports(projectId: string | null): UseApiResult<Report[]> {
  const query = useQuery({
    queryKey: ['reports', projectId],
    queryFn: () => unwrapPaginated(api.getReports(projectId!), 'Failed to fetch reports'),
    enabled: !!projectId,
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.error ? errorMessage(query.error, 'Failed to fetch reports') : null,
    refetch: () => { void query.refetch(); },
  };
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
export function useCreateProject(): UseMutationResult<CreateProjectInput, Project> & { refetch: () => void } {
  const mutation = useMutation({
    mutationFn: (input: CreateProjectInput) => unwrap(api.createProject(input), 'Failed to create project'),
  });

  return {
    mutate: async (args: CreateProjectInput) => {
      try {
        const data = await mutation.mutateAsync(args);
        return data;
      } catch {
        return null;
      }
    },
    loading: mutation.isPending,
    error: mutation.error ? errorMessage(mutation.error, 'Failed to create project') : null,
    data: mutation.data ?? null,
    reset: mutation.reset,
    refetch: mutation.reset, // Alias for backward compat (old code called refetch to clear state)
  };
}

// useCreateDevice - Mutation hook for creating a device
export function useCreateDevice(): UseMutationResult<{ projectId: string; data: CreateDeviceInput }, Device> {
  const mutation = useMutation({
    mutationFn: (args: { projectId: string; data: CreateDeviceInput }) =>
      unwrap(api.createDevice(args.projectId, args.data), 'Failed to create device'),
  });

  return {
    mutate: async (args: { projectId: string; data: CreateDeviceInput }) => {
      try {
        const data = await mutation.mutateAsync(args);
        return data;
      } catch {
        return null;
      }
    },
    loading: mutation.isPending,
    error: mutation.error ? errorMessage(mutation.error, 'Failed to create device') : null,
    data: mutation.data ?? null,
    reset: mutation.reset,
  };
}

// useDeleteProject - Mutation hook for deleting a project
export function useDeleteProject(): UseMutationResult<string, void> & { refetch: () => void } {
  const mutation = useMutation({
    mutationFn: async (id: string) => {
      await unwrap(api.deleteProject(id), 'Failed to delete project');
    },
  });

  return {
    mutate: async (id: string) => {
      try {
        await mutation.mutateAsync(id);
        return undefined;
      } catch {
        return null;
      }
    },
    loading: mutation.isPending,
    error: mutation.error ? errorMessage(mutation.error, 'Failed to delete project') : null,
    data: null,
    reset: mutation.reset,
    refetch: mutation.reset,
  };
}

// useSyncProject - Mutation hook for syncing a project
export function useSyncProject(): UseMutationResult<string, unknown> {
  const mutation = useMutation({
    mutationFn: (projectId: string) => unwrap(api.syncProject(projectId), 'Failed to sync project'),
  });

  return {
    mutate: async (projectId: string) => {
      try {
        const data = await mutation.mutateAsync(projectId);
        return data;
      } catch {
        return null;
      }
    },
    loading: mutation.isPending,
    error: mutation.error ? errorMessage(mutation.error, 'Failed to sync project') : null,
    data: mutation.data ?? null,
    reset: mutation.reset,
  };
}

// useGenerateReport - Mutation hook for generating a report
export function useGenerateReport(): UseMutationResult<{ projectId: string; data: { type: string; execution_params: Record<string, unknown> } }, Report> {
  const mutation = useMutation({
    mutationFn: (args: { projectId: string; data: { type: string; execution_params: Record<string, unknown> } }) =>
      unwrap(api.generateReport(args.projectId, args.data), 'Failed to generate report'),
  });

  return {
    mutate: async (args: { projectId: string; data: { type: string; execution_params: Record<string, unknown> } }) => {
      try {
        const data = await mutation.mutateAsync(args);
        return data;
      } catch {
        return null;
      }
    },
    loading: mutation.isPending,
    error: mutation.error ? errorMessage(mutation.error, 'Failed to generate report') : null,
    data: mutation.data ?? null,
    reset: mutation.reset,
  };
}
