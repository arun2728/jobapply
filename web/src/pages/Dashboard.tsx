import { useMemo, useState } from "react";
import { Filter, Loader2, PenSquare, Wand2 } from "lucide-react";
import { Link } from "react-router-dom";
import SearchForm from "@/components/SearchForm";
import JobCard from "@/components/JobCard";
import TaskProgress from "@/components/TaskProgress";
import {
  useJobs,
  useStartRun,
  useStatus,
} from "@/lib/hooks";
import type { JobRecord, TaskRecord } from "@/lib/types";
import clsx from "clsx";

const STATUS_FILTERS = [
  { value: "all", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "done", label: "Tailored" },
  { value: "skipped", label: "Low fit" },
  { value: "failed", label: "Failed" },
];

export default function Dashboard() {
  const status = useStatus();
  const jobs = useJobs();
  const [filter, setFilter] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [searchTask, setSearchTask] = useState<TaskRecord | null>(null);
  const [runTask, setRunTask] = useState<TaskRecord | null>(null);
  const startRun = useStartRun();

  const filtered: JobRecord[] = useMemo(() => {
    const list = jobs.data?.jobs ?? [];
    const q = query.trim().toLowerCase();
    return list.filter((j) => {
      if (filter !== "all" && j.status !== filter) return false;
      if (!q) return true;
      const hay =
        (j.title || "") +
        " " +
        (j.company || "") +
        " " +
        (j.location || "") +
        " " +
        (j.description || "");
      return hay.toLowerCase().includes(q);
    });
  }, [jobs.data, filter, query]);

  const pendingCount = (jobs.data?.jobs ?? []).filter(
    (j) => j.status === "pending",
  ).length;
  const profileLoaded = status.data?.profile_loaded ?? false;

  const toggleSelected = (jobId: string, on: boolean) => {
    setSelected((s) => {
      const next = new Set(s);
      if (on) next.add(jobId);
      else next.delete(jobId);
      return next;
    });
  };

  const onTailorSelected = async () => {
    if (selected.size === 0) return;
    try {
      const t = await startRun.mutateAsync({
        job_ids: Array.from(selected),
      });
      setRunTask(t);
      setSelected(new Set());
    } catch {
      // shown via mutation state
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Jobs</h1>
        <p className="text-sm text-slate-400">
          Run a search, then tailor your resume + cover letter for the roles
          you like.
        </p>
      </div>

      {!profileLoaded ? (
        <div className="card border-amber-700/40 bg-amber-900/10 p-4 text-sm text-amber-200">
          <div className="font-semibold">profile.json not found</div>
          <p className="mt-1 text-amber-100/80">
            Run{" "}
            <code className="rounded bg-slate-900 px-1.5 py-0.5 font-mono text-xs">
              jobapply init --resume &lt;path&gt;
            </code>{" "}
            in this directory before tailoring or scoring.
          </p>
        </div>
      ) : null}

      <SearchForm onTaskStarted={(t) => setSearchTask(t)} />

      {searchTask ? (
        <TaskProgress
          taskId={searchTask.task_id}
          onDone={() => jobs.refetch()}
        />
      ) : null}
      {runTask ? (
        <TaskProgress
          taskId={runTask.task_id}
          onDone={() => jobs.refetch()}
        />
      ) : null}

      <div className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:gap-4">
        <div className="flex flex-1 items-center gap-2">
          <Filter size={16} className="text-slate-400" />
          <input
            className="input flex-1"
            placeholder="Filter by title, company, description…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              className={clsx(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                filter === f.value
                  ? "bg-brand-500/20 text-brand-200"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-100",
              )}
              onClick={() => setFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Link to="/freeform" className="btn-ghost text-sm">
            <PenSquare size={14} />
            Paste JD
          </Link>
          <button
            className="btn-primary"
            disabled={selected.size === 0 || startRun.isPending}
            onClick={onTailorSelected}
          >
            {startRun.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Wand2 size={14} />
            )}
            Tailor selected ({selected.size})
          </button>
        </div>
      </div>

      {jobs.isLoading ? (
        <div className="card flex items-center gap-2 p-6 text-sm text-slate-400">
          <Loader2 size={16} className="animate-spin" /> Loading jobs…
        </div>
      ) : filtered.length === 0 ? (
        <div className="card flex flex-col items-center gap-3 p-10 text-center">
          <div className="text-base font-semibold text-slate-200">
            No jobs match.
          </div>
          <p className="max-w-md text-sm text-slate-400">
            Run a search above, paste a job description, or change the filter
            to see roles. Pending jobs:{" "}
            <span className="font-mono text-slate-200">{pendingCount}</span>.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {filtered.map((job) => (
            <JobCard
              key={job.job_id}
              job={job}
              selected={selected.has(job.job_id)}
              onToggle={(on) => toggleSelected(job.job_id, on)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
