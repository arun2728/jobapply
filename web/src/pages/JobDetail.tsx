import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Building2,
  Download,
  ExternalLink,
  FileCheck2,
  Loader2,
  Mail,
  MapPin,
  Trash2,
  Wand2,
} from "lucide-react";
import {
  useDeleteJob,
  useJob,
  useStartTailor,
  useTaskPoll,
} from "@/lib/hooks";
import {
  formatScore,
  formatStatus,
  pickAcceptableUrl,
  shortHostname,
} from "@/lib/format";
import EmailModal from "@/components/EmailModal";
import TaskProgress from "@/components/TaskProgress";
import { api } from "@/lib/api";

const ARTIFACTS_PRIMARY = [
  { name: "resume.pdf", label: "Resume PDF" },
  { name: "cover_letter.pdf", label: "Cover letter PDF" },
];
const ARTIFACTS_SOURCES = [
  { name: "resume.md", label: "resume.md" },
  { name: "resume.tex", label: "resume.tex" },
  { name: "cover_letter.md", label: "cover_letter.md" },
  { name: "cover_letter.tex", label: "cover_letter.tex" },
  { name: "email.txt", label: "email.txt" },
  { name: "job.json", label: "job.json" },
];

export default function JobDetail() {
  const { jobId } = useParams();
  const job = useJob(jobId);
  const tailor = useStartTailor(jobId ?? "");
  const deleteJob = useDeleteJob();
  const [tailorTaskId, setTailorTaskId] = useState<string | null>(null);
  const tailorTask = useTaskPoll(tailorTaskId);
  const [emailOpen, setEmailOpen] = useState(false);

  if (!jobId) return null;
  if (job.isLoading) {
    return (
      <div className="card flex items-center gap-2 p-6 text-sm text-slate-300">
        <Loader2 size={16} className="animate-spin" /> Loading…
      </div>
    );
  }
  if (job.error || !job.data) {
    return (
      <div className="card p-6 text-sm">
        <p className="text-rose-300">
          Couldn't load this job:{" "}
          {String((job.error as Error)?.message ?? "missing")}
        </p>
        <Link to="/" className="btn-ghost mt-3">
          <ArrowLeft size={14} /> Back to jobs
        </Link>
      </div>
    );
  }

  const j = job.data;
  const status = formatStatus(j.status);
  const url = pickAcceptableUrl(j);
  const host = shortHostname(url);
  const isTailored = j.status === "done" || !!j.tailored_resume;
  const available = j.available_artifacts ?? {};

  const onTailor = async () => {
    try {
      const t = await tailor.mutateAsync({});
      setTailorTaskId(t.task_id);
    } catch {
      // shown via mutation state below
    }
  };

  const onDelete = async () => {
    if (!confirm(`Remove '${j.title}' from this workspace?`)) return;
    await deleteJob.mutateAsync(j.job_id);
    window.location.href = "/";
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Link to="/" className="btn-ghost">
          <ArrowLeft size={14} /> Back
        </Link>
        <span className={"badge " + status.className}>{status.label}</span>
        {j.fit ? (
          <span className="text-xs text-slate-400">
            Fit{" "}
            <span className="font-mono text-slate-200">
              {formatScore(j.fit.score)}
            </span>
          </span>
        ) : null}
        <button
          className="btn-ghost ml-auto text-rose-300 hover:bg-rose-900/30"
          onClick={onDelete}
          disabled={deleteJob.isPending}
        >
          <Trash2 size={14} /> Remove
        </button>
      </div>

      <header className="card space-y-3 p-5">
        <h1 className="text-xl font-bold tracking-tight text-slate-50">
          {j.title || "Untitled role"}
        </h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-400">
          {j.company ? (
            <span className="flex items-center gap-1">
              <Building2 size={14} />
              {j.company}
            </span>
          ) : null}
          {j.location ? (
            <span className="flex items-center gap-1">
              <MapPin size={14} />
              {j.location}
            </span>
          ) : null}
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-brand-300 hover:text-brand-200"
            >
              <ExternalLink size={14} />
              {host || "Apply"}
            </a>
          ) : null}
        </div>
        {j.fit?.rationale ? (
          <p className="text-sm text-slate-300">
            <span className="font-semibold text-slate-200">Fit:</span>{" "}
            {j.fit.rationale}
          </p>
        ) : null}
        {j.fit?.missing_keywords && j.fit.missing_keywords.length > 0 ? (
          <p className="text-xs text-slate-500">
            <span className="text-slate-400">Missing keywords:</span>{" "}
            {j.fit.missing_keywords.join(", ")}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            className="btn-primary"
            onClick={onTailor}
            disabled={tailor.isPending || tailorTask.task?.status === "running"}
          >
            {tailor.isPending || tailorTask.task?.status === "running" ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Wand2 size={14} />
            )}
            {isTailored ? "Re-tailor" : "Tailor resume + cover letter"}
          </button>
          <button
            className="btn-secondary"
            onClick={() => setEmailOpen(true)}
            disabled={!isTailored}
            title={
              isTailored
                ? "Draft a recruiter email"
                : "Tailor first to enable the email drafter."
            }
          >
            <Mail size={14} /> Draft email
          </button>
        </div>
      </header>

      {tailorTaskId ? (
        <TaskProgress
          taskId={tailorTaskId}
          onDone={() => job.refetch()}
        />
      ) : null}
      {tailor.isError ? (
        <div className="card border-rose-700/40 bg-rose-900/10 p-4 text-sm text-rose-300">
          {String(tailor.error?.message ?? tailor.error)}
        </div>
      ) : null}

      {isTailored ? (
        <section className="card space-y-3 p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <FileCheck2 size={16} className="text-brand-400" />
            Generated artifacts
          </div>
          <div className="flex flex-wrap gap-2">
            {ARTIFACTS_PRIMARY.map((a) =>
              available[a.name] ? (
                <a
                  key={a.name}
                  href={api.artifactUrl(j.job_id, a.name)}
                  className="btn-primary"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Download size={14} />
                  {a.label}
                </a>
              ) : null,
            )}
          </div>
          <details className="text-sm">
            <summary className="cursor-pointer text-slate-400 hover:text-slate-200">
              Sources & raw files
            </summary>
            <div className="mt-2 flex flex-wrap gap-2">
              {ARTIFACTS_SOURCES.filter((a) => available[a.name]).map((a) => (
                <a
                  key={a.name}
                  href={api.artifactUrl(j.job_id, a.name)}
                  className="btn-ghost text-xs"
                  target="_blank"
                  rel="noreferrer"
                >
                  {a.label}
                </a>
              ))}
            </div>
          </details>
        </section>
      ) : (
        <section className="card border-dashed p-5 text-sm text-slate-400">
          No tailored resume yet. Click <span className="font-semibold text-slate-200">Tailor resume + cover letter</span> above to generate one.
        </section>
      )}

      <section className="card space-y-3 p-5">
        <h2 className="text-sm font-semibold text-slate-200">
          Job description
        </h2>
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded bg-slate-950/40 p-3 font-sans text-sm text-slate-200">
          {(j.description || "").trim() || "(empty)"}
        </pre>
      </section>

      {j.tailored_resume ? (
        <section className="card space-y-3 p-5">
          <h2 className="text-sm font-semibold text-slate-200">Tailored resume preview</h2>
          {j.tailored_resume.summary ? (
            <p className="text-sm text-slate-300">{j.tailored_resume.summary}</p>
          ) : null}
          {j.tailored_resume.skills && j.tailored_resume.skills.length > 0 ? (
            <p className="text-sm text-slate-400">
              <span className="text-slate-500">Skills: </span>
              {j.tailored_resume.skills.join(", ")}
            </p>
          ) : null}
          {(j.tailored_resume.experience ?? []).map((role, i) => (
            <div key={i} className="rounded border border-slate-800 p-3">
              <div className="text-sm font-semibold text-slate-100">
                {role.role}{" "}
                <span className="text-slate-400">@ {role.company}</span>
                {role.dates ? (
                  <span className="ml-2 text-xs text-slate-500">
                    {role.dates}
                  </span>
                ) : null}
              </div>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-300">
                {(role.bullets ?? []).map((b, k) => (
                  <li key={k}>{b}</li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ) : null}

      {emailOpen ? (
        <EmailModal
          jobId={j.job_id}
          open={emailOpen}
          onClose={() => setEmailOpen(false)}
          defaultRecipient={j.application?.primary_email ?? ""}
        />
      ) : null}
    </div>
  );
}
