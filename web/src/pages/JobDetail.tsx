import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Building2,
  ExternalLink,
  Loader2,
  Mail,
  MapPin,
  Trash2,
  Wand2,
} from "lucide-react";
import {
  useActiveTaskFor,
  useDeleteJob,
  useJob,
  useLastTaskFor,
  useStartTailor,
} from "@/lib/hooks";
import {
  formatScore,
  formatStatus,
  pickAcceptableUrl,
  shortHostname,
} from "@/lib/format";
import ArtifactPreview from "@/components/ArtifactPreview";
import EmailModal from "@/components/EmailModal";
import Markdown from "@/components/Markdown";
import TailorModal, {
  type TailorOptions,
} from "@/components/TailorModal";
import TaskProgress from "@/components/TaskProgress";
import { api } from "@/lib/api";

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
  const [emailOpen, setEmailOpen] = useState(false);
  const [tailorOpen, setTailorOpen] = useState(false);
  const live = useActiveTaskFor(jobId);
  const lastTask = useLastTaskFor(jobId);
  const liveKind = live.task?.kind;
  const isWorking = Boolean(live.task);
  const isTailoring = liveKind === "tailor" || liveKind === "run";
  const isDraftingEmail = liveKind === "email";

  const [stickyTaskId, setStickyTaskId] = useState<string | null>(null);
  useEffect(() => {
    if (live.task) setStickyTaskId(live.task.task_id);
    else if (lastTask && !stickyTaskId) setStickyTaskId(lastTask.task_id);
  }, [live.task?.task_id, lastTask?.task_id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!jobId) return null;
  if (job.isLoading) {
    return (
      <div className="card flex items-center gap-2 p-6 text-sm text-neutral-400">
        <Loader2 size={16} className="animate-spin" /> Loading…
      </div>
    );
  }
  if (job.error || !job.data) {
    return (
      <div className="card p-6 text-sm">
        <p className="text-red-400">
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

  const onConfirmTailor = async (opts: TailorOptions) => {
    try {
      const t = await tailor.mutateAsync({
        provider: opts.provider,
        model: opts.model,
        no_pdf: opts.no_pdf,
      });
      setStickyTaskId(t.task_id);
      setTailorOpen(false);
    } catch {
      // mutation error stays visible in the modal via the spinner state
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
          <span className="text-xs text-neutral-500">
            Fit{" "}
            <span className="font-mono text-neutral-300">
              {formatScore(j.fit.score)}
            </span>
          </span>
        ) : null}
        <button
          className="btn-ghost ml-auto text-red-400 hover:bg-red-950/30"
          onClick={onDelete}
          disabled={deleteJob.isPending}
        >
          <Trash2 size={14} /> Remove
        </button>
      </div>

      <header className="card space-y-3 p-5">
        <h1 className="text-xl font-bold tracking-tight text-white">
          {j.title || "Untitled role"}
        </h1>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-neutral-500">
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
              className="flex items-center gap-1 text-neutral-400 hover:text-white"
            >
              <ExternalLink size={14} />
              {host || "Apply"}
            </a>
          ) : null}
        </div>
        {j.fit?.rationale ? (
          <p className="text-sm text-neutral-400">
            <span className="font-semibold text-neutral-300">Fit:</span>{" "}
            {j.fit.rationale}
          </p>
        ) : null}
        {j.fit?.missing_keywords && j.fit.missing_keywords.length > 0 ? (
          <p className="text-xs text-neutral-600">
            <span className="text-neutral-500">Missing keywords:</span>{" "}
            {j.fit.missing_keywords.join(", ")}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button
            className="btn-primary"
            onClick={() => setTailorOpen(true)}
            disabled={isWorking}
          >
            {isTailoring ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Wand2 size={14} />
            )}
            {isTailoring
              ? liveKind === "run"
                ? "Tailoring (batch)…"
                : "Tailoring…"
              : isTailored
                ? "Re-tailor"
                : "Tailor resume + cover letter"}
          </button>
          <button
            className="btn-secondary"
            onClick={() => setEmailOpen(true)}
            disabled={isWorking}
            title={
              isDraftingEmail
                ? "An email draft is currently being generated for this job."
                : isTailored
                  ? "Draft a recruiter email referencing your tailored resume."
                  : "Draft a short recruiter email from the JD + your profile (no attachments mentioned)."
            }
          >
            {isDraftingEmail ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Mail size={14} />
            )}
            {isDraftingEmail ? "Drafting email…" : "Draft email"}
          </button>
        </div>
      </header>

      {stickyTaskId ? (
        <TaskProgress
          taskId={stickyTaskId}
          onDone={() => job.refetch()}
        />
      ) : null}
      {tailor.isError ? (
        <div className="card border-red-800/40 bg-red-950/20 p-4 text-sm text-red-400">
          {String(tailor.error?.message ?? tailor.error)}
        </div>
      ) : null}

      {isTailored ? (
        <>
          <ArtifactPreview job={j} />
          <details className="card p-4 text-sm">
            <summary className="cursor-pointer text-neutral-500 hover:text-neutral-300">
              Sources &amp; raw files
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
        </>
      ) : (
        <section className="card border-dashed p-5 text-sm text-neutral-500">
          No tailored resume yet. Click <span className="font-semibold text-neutral-200">Tailor resume + cover letter</span> above to generate one.
        </section>
      )}

      <section className="card space-y-3 p-5">
        <h2 className="text-sm font-semibold text-neutral-300">
          Job description
        </h2>
        {(j.description || "").trim() ? (
          <Markdown className="max-h-[60vh] overflow-auto rounded bg-black/40 p-4">
            {j.description!}
          </Markdown>
        ) : (
          <p className="text-sm italic text-neutral-600">(empty)</p>
        )}
      </section>

      {j.tailored_resume ? (
        <section className="card space-y-3 p-5">
          <h2 className="text-sm font-semibold text-neutral-300">Tailored resume preview</h2>
          {j.tailored_resume.summary ? (
            <p className="text-sm text-neutral-400">{j.tailored_resume.summary}</p>
          ) : null}
          {j.tailored_resume.skills && j.tailored_resume.skills.length > 0 ? (
            <p className="text-sm text-neutral-500">
              <span className="text-neutral-600">Skills: </span>
              {j.tailored_resume.skills.join(", ")}
            </p>
          ) : null}
          {(j.tailored_resume.experience ?? []).map((role, i) => (
            <div key={i} className="rounded border border-neutral-800 p-3">
              <div className="text-sm font-semibold text-white">
                {role.role}{" "}
                <span className="text-neutral-500">@ {role.company}</span>
                {role.dates ? (
                  <span className="ml-2 text-xs text-neutral-600">
                    {role.dates}
                  </span>
                ) : null}
              </div>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-neutral-400">
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
          isTailored={isTailored}
        />
      ) : null}
      <TailorModal
        open={tailorOpen}
        onClose={() => setTailorOpen(false)}
        onConfirm={onConfirmTailor}
        pending={tailor.isPending}
        title={isTailored ? "Re-tailor resume + cover letter" : undefined}
        jobTitle={j.title || j.company || j.job_id}
      />
    </div>
  );
}
