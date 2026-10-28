import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useTaskPoll } from "@/lib/hooks";
import { queryKeys } from "@/lib/hooks";
import { api } from "@/lib/api";

interface Props {
  taskId: string;
  onDone?: (status: "succeeded" | "failed" | "cancelled") => void;
  invalidateOnDone?: ReadonlyArray<readonly unknown[]>;
}

/** Card that polls a backend task and renders its progress live. */
export default function TaskProgress({
  taskId,
  onDone,
  invalidateOnDone,
}: Props) {
  const { task, error } = useTaskPoll(taskId);
  const qc = useQueryClient();

  useEffect(() => {
    if (!task) return;
    if (
      task.status === "succeeded" ||
      task.status === "failed" ||
      task.status === "cancelled"
    ) {
      const keys = invalidateOnDone ?? [queryKeys.jobs, queryKeys.status];
      for (const key of keys) qc.invalidateQueries({ queryKey: key });
      onDone?.(task.status);
    }
  }, [task?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!task) {
    return (
      <div className="card flex items-center gap-3 p-4">
        <Loader2 size={16} className="animate-spin text-neutral-400" />
        <span className="text-sm text-neutral-400">Starting task…</span>
        {error ? (
          <span className="text-xs text-red-400">{error}</span>
        ) : null}
      </div>
    );
  }

  const Icon =
    task.status === "succeeded"
      ? CheckCircle2
      : task.status === "failed"
        ? XCircle
        : Loader2;
  const tone =
    task.status === "succeeded"
      ? "text-white"
      : task.status === "failed"
        ? "text-red-400"
        : "text-neutral-400";
  const isRunning = task.status === "pending" || task.status === "running";

  return (
    <div className="card space-y-3 p-4">
      <div className="flex items-center gap-3 text-sm">
        <Icon
          size={16}
          className={tone + (isRunning ? " animate-spin" : "")}
        />
        <span className="font-semibold text-white">
          {task.kind.charAt(0).toUpperCase() + task.kind.slice(1)} task
        </span>
        <span className="ml-auto text-xs uppercase tracking-wide text-neutral-600">
          {task.status}
        </span>
        {isRunning ? (
          <button
            className="btn-ghost text-xs"
            onClick={() => api.cancelTask(task.task_id).catch(() => {})}
          >
            Cancel
          </button>
        ) : null}
      </div>
      <div className="text-sm text-neutral-400">
        {task.progress.label || "Working…"}
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-neutral-800">
        <div
          className={`h-full transition-all ${
            task.status === "failed"
              ? "bg-red-500"
              : task.status === "succeeded"
                ? "bg-white"
                : "bg-neutral-400"
          }`}
          style={{
            width: `${
              task.status === "succeeded"
                ? 100
                : Math.max(2, Math.min(100, task.progress.percent))
            }%`,
          }}
        />
      </div>
      {task.error ? (
        <pre className="max-h-40 overflow-auto rounded bg-red-950/40 p-2 text-xs text-red-200">
          {task.error}
        </pre>
      ) : null}
      {task.progress.log.length > 0 ? (
        <details className="text-xs">
          <summary className="cursor-pointer text-neutral-500 hover:text-neutral-300">
            Log ({task.progress.log.length})
          </summary>
          <div className="mt-2 max-h-48 space-y-0.5 overflow-auto rounded bg-black/80 p-2 font-mono text-[11px] text-neutral-400">
            {task.progress.log.slice(-100).map((line, i) => (
              <div key={i}>{line}</div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}
