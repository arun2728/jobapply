import { Link } from "react-router-dom";
import {
  Building2,
  ExternalLink,
  FileCheck2,
  Mail,
  MapPin,
} from "lucide-react";
import {
  formatScore,
  formatStatus,
  pickAcceptableUrl,
  shortHostname,
} from "@/lib/format";
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

  return (
    <div
      className={`card flex flex-col gap-3 p-4 transition-colors ${
        selected ? "ring-2 ring-brand-400/60" : "hover:border-slate-700"
      }`}
    >
      <div className="flex items-start gap-3">
        {onToggle ? (
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 accent-brand-500"
            checked={!!selected}
            onChange={(e) => onToggle(e.target.checked)}
            aria-label="Select for batch run"
          />
        ) : null}
        <div className="min-w-0 flex-1">
          <Link
            to={`/jobs/${job.job_id}`}
            className="block truncate text-base font-semibold text-slate-100 hover:text-brand-300"
          >
            {job.title || "Untitled role"}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
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
          <span className={"badge " + status.className}>{status.label}</span>
          {job.fit ? (
            <span className="text-xs text-slate-400">
              fit{" "}
              <span className="font-mono text-slate-200">
                {formatScore(job.fit.score)}
              </span>
            </span>
          ) : null}
        </div>
      </div>
      {job.fit?.rationale ? (
        <p className="line-clamp-2 text-sm text-slate-400">
          {job.fit.rationale}
        </p>
      ) : job.description ? (
        <Markdown
          compact
          className="line-clamp-2 text-sm leading-snug text-slate-500"
        >
          {job.description.slice(0, 600)}
        </Markdown>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {isTailored ? (
          <span className="flex items-center gap-1 text-brand-300">
            <FileCheck2 size={12} /> Resume + cover ready
          </span>
        ) : (
          <span className="text-slate-500">No resume yet</span>
        )}
        {recipient ? (
          <span className="flex items-center gap-1 text-amber-300">
            <Mail size={12} /> {recipient}
          </span>
        ) : null}
        <Link
          to={`/jobs/${job.job_id}`}
          className="ml-auto text-brand-400 hover:text-brand-200"
        >
          Details →
        </Link>
      </div>
    </div>
  );
}
