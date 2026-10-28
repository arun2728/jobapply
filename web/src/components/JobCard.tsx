import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Building2,
  ExternalLink,
  FileCheck2,
  Loader2,
  Mail,
  MapPin,
} from "lucide-react";
import {
  formatScore,
  formatStatus,
  pickAcceptableUrl,
  shortHostname,
} from "@/lib/format";
import { useActiveTaskFor, useLastTaskFor } from "@/lib/hooks";
import type { JobRecord } from "@/lib/types";
import Markdown from "./Markdown";

interface Props {
  job: JobRecord;
  selected?: boolean;
  onToggle?: (checked: boolean) => void;
}

export default function JobCard({ job, selected, onToggle }: Props) {
  const status = formatStatus(job.status);
  const url = pickAcceptableUrl(job);
  const host = shortHostname(url);
  const isTailored = job.status === "done" || !!job.tailored_resume;
  const recipient = job.application?.primary_email;
  const hasEmailDraft = Boolean(job.available_artifacts?.["email.txt"]);
  const live = useActiveTaskFor(job.job_id);
  const liveKind = live.task?.kind;
  // We only surface the *last* task when it's a failure and nothing
  // is currently running for this job — succeeded runs already
  // manifest as the resume/email artifacts. ``run`` is excluded so
  // that batch failures reported on a peer job don't pollute every
  // card in the batch.
  const lastTask = useLastTaskFor(job.job_id);
  const failedTask =
    !live.task &&
    lastTask &&
    lastTask.status === "failed" &&
    lastTask.kind !== "run"
      ? lastTask
      : null;

  return (
    <div
      className={`card flex flex-col gap-3 p-4 transition-colors ${
        selected ? "ring-2 ring-neutral-500" : "hover:border-neutral-700"
      } ${live.task ? "border-neutral-600 ring-1 ring-neutral-600" : ""}`}
    >
      <div className="flex items-start gap-3">
        {onToggle ? (
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 accent-white"
            checked={!!selected}
            onChange={(e) => onToggle(e.target.checked)}
            aria-label="Select for batch run"
          />
        ) : null}
        <div className="min-w-0 flex-1">
          <Link
            to={`/jobs/${job.job_id}`}
            className="block truncate text-base font-semibold text-white hover:text-neutral-300"
          >
            {job.title || "Untitled role"}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-500">
            {job.company ? (
              <span className="flex items-center gap-1">
                <Building2 size={12} />
                {job.company}
              </span>
            ) : null}
            {job.location ? (
              <span className="flex items-center gap-1">
                <MapPin size={12} />
                {job.location}
              </span>
            ) : null}
            {host ? (
              <span className="flex items-center gap-1">
                <ExternalLink size={12} />
                {host}
              </span>
            ) : null}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          {live.task ? (
            <span className="badge bg-neutral-800 text-neutral-200 ring-1 ring-neutral-700">
              <Loader2 size={10} className="mr-1 animate-spin" />
              {liveKind === "email"
                ? "Drafting email"
                : liveKind === "run"
                  ? "Tailoring (batch)"
                  : "Tailoring"}
            </span>
          ) : failedTask ? (
            <span
              className="badge bg-red-500/10 text-red-400 ring-1 ring-red-500/30"
              title={(failedTask.error || "").slice(0, 600)}
            >
              <AlertTriangle size={10} className="mr-1" />
              {failedTask.kind === "email"
                ? "Email failed"
                : "Tailor failed"}
            </span>
          ) : (
            <span className={"badge " + status.className}>{status.label}</span>
          )}
          {job.fit ? (
            <span className="text-xs text-neutral-500">
              fit{" "}
              <span className="font-mono text-neutral-300">
                {formatScore(job.fit.score)}
              </span>
            </span>
          ) : null}
        </div>
      </div>
      {live.task ? (
        <div className="-mt-1 space-y-1">
          <div className="h-1 overflow-hidden rounded-full bg-neutral-800">
            <div
              className="h-full rounded-full bg-white transition-all"
              style={{
                width: `${Math.max(8, Math.min(100, live.percent || 12))}%`,
              }}
            />
          </div>
          <div className="text-[11px] uppercase tracking-wide text-neutral-400">
            {live.label}
          </div>
        </div>
      ) : null}
      {job.fit?.rationale ? (
        <p className="line-clamp-2 text-sm text-neutral-500">
          {job.fit.rationale}
        </p>
      ) : job.description ? (
        <Markdown
          compact
          className="line-clamp-2 text-sm leading-snug text-neutral-600"
        >
          {job.description.slice(0, 600)}
        </Markdown>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {liveKind === "tailor" || liveKind === "run" ? (
          <span className="flex items-center gap-1 text-neutral-300">
            <Loader2 size={12} className="animate-spin" /> Tailoring resume…
          </span>
        ) : isTailored ? (
          <span className="flex items-center gap-1 text-neutral-300">
            <FileCheck2 size={12} /> Resume + cover ready
          </span>
        ) : (
          <span className="text-neutral-600">No resume yet</span>
        )}
        {liveKind === "email" ? (
          <span className="flex items-center gap-1 text-neutral-400">
            <Loader2 size={12} className="animate-spin" /> Drafting email…
          </span>
        ) : hasEmailDraft ? (
          <span className="flex items-center gap-1 text-neutral-400">
            <Mail size={12} /> Email drafted
          </span>
        ) : recipient ? (
          <span className="flex items-center gap-1 text-neutral-400">
            <Mail size={12} /> {recipient}
          </span>
        ) : null}
        <Link
          to={`/jobs/${job.job_id}`}
          className="ml-auto text-neutral-500 hover:text-white"
        >
          Details →
        </Link>
      </div>
    </div>
  );
}
