import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api";
import type {
  JobRecord,
  JobsListResponse,
  ServerStatus,
  TaskRecord,
} from "./types";

// Centralized query keys make it easy to invalidate the right caches
// when a mutation lands. (`["jobs"]` covers list + detail; React Query
// invalidates anything starting with the prefix.)
export const queryKeys = {
  status: ["status"] as const,
  jobs: ["jobs"] as const,
  job: (id: string) => ["jobs", id] as const,
  searches: ["searches"] as const,
  task: (id: string) => ["task", id] as const,
};

export function useStatus(opts?: Partial<UseQueryOptions<ServerStatus>>) {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: api.status,
    ...opts,
  });
}

export function useJobs(opts?: Partial<UseQueryOptions<JobsListResponse>>) {
  return useQuery({
    queryKey: queryKeys.jobs,
    queryFn: api.jobs,
    ...opts,
  });
}

export function useJob(
  jobId: string | undefined,
  opts?: Partial<UseQueryOptions<JobRecord>>,
) {
  return useQuery({
    queryKey: jobId ? queryKeys.job(jobId) : ["jobs", "missing"],
    enabled: Boolean(jobId),
    queryFn: () => api.job(jobId!),
    ...opts,
  });
}

export function useSearches() {
  return useQuery({ queryKey: queryKeys.searches, queryFn: api.searches });
}

/** Polls /api/tasks/<id> until the task settles. Returns the latest
 *  snapshot plus a `done` flag the caller can use to invalidate
 *  dependent queries exactly once. */
export function useTaskPoll(taskId: string | null) {
  const [task, setTask] = useState<TaskRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) {
      setTask(null);
      setError(null);
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const t = await api.task(taskId);
        if (cancelled) return;
        setTask(t);
        if (
          t.status === "succeeded" ||
          t.status === "failed" ||
          t.status === "cancelled"
        ) {
          return; // stop polling
        }
        timer = window.setTimeout(tick, 1200);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    let timer = window.setTimeout(tick, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [taskId]);

  const isTerminal =
    !!task &&
    (task.status === "succeeded" ||
      task.status === "failed" ||
      task.status === "cancelled");

  return { task, error, isTerminal };
}

export function useStartSearch() {
  return useMutation({ mutationFn: api.search });
}

export function useStartRun() {
  return useMutation({ mutationFn: api.run });
}

export function useStartTailor(jobId: string) {
  return useMutation({
    mutationFn: (
      vars: { provider?: string; model?: string; no_pdf?: boolean } = {},
    ) => api.tailor(jobId, vars),
  });
}

export function useStartFreeform() {
  return useMutation({ mutationFn: api.freeform });
}

export function useStartEmail(jobId: string) {
  return useMutation({
    mutationFn: (vars: {
      recipient: string;
      additional_info?: string;
      provider?: string;
      model?: string;
    }) => api.email(jobId, vars),
  });
}

export function useDeleteJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.deleteJob(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.jobs });
      qc.invalidateQueries({ queryKey: queryKeys.status });
    },
  });
}

export function useEmailHint(jobId: string | undefined) {
  return useQuery({
    queryKey: ["email-hint", jobId],
    enabled: Boolean(jobId),
    queryFn: () => api.emailHint(jobId!),
  });
}
