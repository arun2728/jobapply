import { useState } from "react";
import { Loader2, PenSquare, Wand2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useStartFreeform, useStatus, useTaskPoll } from "@/lib/hooks";
import TaskProgress from "@/components/TaskProgress";

/** Paste-JD route. Submits the description to /api/freeform; on
 *  success the new job lands in the workspace catalog and we redirect
 *  to its detail page. */
export default function Freeform() {
  const status = useStatus();
  const start = useStartFreeform();
  const navigate = useNavigate();
  const [taskId, setTaskId] = useState<string | null>(null);
  const { task } = useTaskPoll(taskId);

  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [skills, setSkills] = useState("");
  const [description, setDescription] = useState("");
  const profileLoaded = status.data?.profile_loaded ?? false;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (description.trim().length < 20) return;
    try {
      const t = await start.mutateAsync({
        description,
        title: title.trim() || undefined,
        company: company.trim() || undefined,
        location: location.trim() || undefined,
        skills: skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setTaskId(t.task_id);
    } catch {
      // shown via mutation error state
    }
  };

  // When the freeform task succeeds, redirect to the new job.
  if (task?.status === "succeeded") {
    const job = (task.result as { job?: { job_id?: string } })?.job;
    if (job?.job_id) {
      // We use a microtask to let TaskProgress render its final state
      // briefly before we navigate away.
      setTimeout(() => navigate(`/jobs/${job.job_id}`), 600);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <PenSquare size={20} className="text-brand-400" /> Paste a job
          description
        </h1>
        <p className="text-sm text-slate-400">
          Drop in a JD from anywhere — LinkedIn, an email, a recruiter's PDF
          you've copy-pasted. We'll tailor your resume + cover letter and
          add it to your workspace.
        </p>
      </div>

      {!profileLoaded ? (
        <div className="card border-amber-700/40 bg-amber-900/10 p-4 text-sm text-amber-200">
          profile.json must be configured first. Run{" "}
          <code className="font-mono">jobapply init --resume &lt;path&gt;</code>.
        </div>
      ) : null}

      <form onSubmit={onSubmit} className="card space-y-4 p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <label>
            <span className="label">Title (optional)</span>
            <input
              className="input"
              placeholder="Senior Backend Engineer"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label>
            <span className="label">Company (optional)</span>
            <input
              className="input"
              placeholder="Acme"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
          </label>
          <label>
            <span className="label">Location (optional)</span>
            <input
              className="input"
              placeholder="Remote / SF"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </label>
        </div>
        <label>
          <span className="label">
            Skills to emphasize (optional, comma-separated)
          </span>
          <input
            className="input"
            placeholder="Python, Kubernetes"
            value={skills}
            onChange={(e) => setSkills(e.target.value)}
          />
        </label>
        <label>
          <span className="label">Job description</span>
          <textarea
            className="input min-h-[280px] font-mono text-sm"
            placeholder="Paste the full JD here…"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
          />
          <span className="mt-1 block text-xs text-slate-500">
            Minimum 20 characters. We auto-detect application emails / subject
            lines from the body.
          </span>
        </label>
        {start.isError ? (
          <p className="text-sm text-rose-400">
            {String(start.error?.message ?? start.error)}
          </p>
        ) : null}
        <div className="flex justify-end">
          <button
            type="submit"
            className="btn-primary"
            disabled={
              start.isPending ||
              task?.status === "running" ||
              description.trim().length < 20 ||
              !profileLoaded
            }
          >
            {start.isPending || task?.status === "running" ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Wand2 size={16} />
            )}
            Tailor & add to workspace
          </button>
        </div>
      </form>

      {taskId ? <TaskProgress taskId={taskId} /> : null}
    </div>
  );
}
