import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ExternalLink,
  FileText,
  Hammer,
  Loader2,
  Pencil,
} from "lucide-react";
import { useCompileArtifact } from "@/lib/hooks";
import { api } from "@/lib/api";
import type { JobRecord } from "@/lib/types";

interface PreviewItem {
  /** Filename of the rendered PDF (e.g. ``resume.pdf``). */
  pdf: string;
  /** Filename of the LaTeX source the editor / compile route opens. */
  source: string;
  label: string;
}

const ITEMS: readonly PreviewItem[] = [
  { pdf: "resume.pdf", source: "resume.tex", label: "Resume" },
  {
    pdf: "cover_letter.pdf",
    source: "cover_letter.tex",
    label: "Cover letter",
  },
] as const;

interface Props {
  job: JobRecord;
}

/** Tabbed PDF preview for a tailored job's resume + cover letter.
 *
 *  Renders each PDF in an ``<iframe>`` (the browser's built-in PDF
 *  viewer) with Edit / Download / Compile actions in the toolbar.
 *  When the LaTeX source exists but the PDF doesn't (e.g. the user
 *  ran ``--no-pdf``), we show a "Compile now" button that triggers
 *  the same backend route the editor uses.
 *
 *  We deliberately keep the per-file UI homogenous: the editor uses
 *  the same ``api.compileArtifact`` so users get identical behaviour
 *  whether they click Compile from this preview or from inside the
 *  full-screen editor.
 */
export default function ArtifactPreview({ job }: Props) {
  const available = job.available_artifacts ?? {};
  const [activeIdx, setActiveIdx] = useState(() => {
    // Land the user on whichever tab actually has content; resume
    // first, fall back to cover letter.
    if (available["resume.pdf"] || available["resume.tex"]) return 0;
    if (available["cover_letter.pdf"] || available["cover_letter.tex"])
      return 1;
    return 0;
  });
  // Cache-buster for the iframe URL — without this Chromium happily
  // serves the stale PDF after a recompile because the URL is
  // identical. Bumped on mount and after every successful compile.
  const [version, setVersion] = useState(() => Date.now());

  const item = ITEMS[activeIdx];
  const compile = useCompileArtifact(job.job_id, item.source);

  const onCompile = async () => {
    try {
      await compile.mutateAsync();
      setVersion(Date.now());
    } catch {
      // surfaced via compile.error in the toolbar status row
    }
  };

  const hasPdf = Boolean(available[item.pdf]);
  const hasSource = Boolean(available[item.source]);
  const pdfUrl = `${api.artifactUrl(job.job_id, item.pdf)}?v=${version}`;

  return (
    <section className="card flex flex-col p-0">
      <div className="flex items-center gap-1 border-b border-slate-800 px-3 py-2">
        {ITEMS.map((it, i) => {
          const enabled =
            Boolean(available[it.pdf]) || Boolean(available[it.source]);
          return (
            <button
              key={it.pdf}
              className={
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors " +
                (i === activeIdx
                  ? "bg-slate-800 text-slate-100"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100") +
                (enabled ? "" : " opacity-50")
              }
              onClick={() => setActiveIdx(i)}
              disabled={!enabled && i !== activeIdx}
              title={
                enabled
                  ? `Preview ${it.label.toLowerCase()}`
                  : `${it.label} not generated yet`
              }
            >
              <span className="mr-1.5 inline-flex items-center">
                <FileText size={14} />
              </span>
              {it.label}
            </button>
          );
        })}
        <Toolbar
          jobId={job.job_id}
          item={item}
          hasPdf={hasPdf}
          hasSource={hasSource}
          compiling={compile.isPending}
          onCompile={onCompile}
        />
      </div>

      {compile.isError ? (
        <div className="flex items-start gap-2 border-b border-rose-700/40 bg-rose-900/10 px-3 py-2 text-xs text-rose-200">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <span>
            Compile failed:{" "}
            {String((compile.error as Error)?.message ?? "unknown error")}
          </span>
        </div>
      ) : compile.isSuccess ? (
        <div className="flex items-center gap-2 border-b border-brand-700/40 bg-brand-900/10 px-3 py-2 text-xs text-brand-200">
          <CheckCircle2 size={14} /> PDF rebuilt via{" "}
          <span className="font-mono">{compile.data?.backend}</span>.
        </div>
      ) : null}

      <PreviewBody
        jobId={job.job_id}
        item={item}
        hasPdf={hasPdf}
        hasSource={hasSource}
        pdfUrl={pdfUrl}
      />
    </section>
  );
}

interface ToolbarProps {
  jobId: string;
  item: PreviewItem;
  hasPdf: boolean;
  hasSource: boolean;
  compiling: boolean;
  onCompile: () => void;
}

function Toolbar({
  jobId,
  item,
  hasPdf,
  hasSource,
  compiling,
  onCompile,
}: ToolbarProps) {
  return (
    <div className="ml-auto flex items-center gap-2">
      {hasSource ? (
        <Link
          to={`/jobs/${jobId}/edit/${item.source}`}
          className="btn-secondary text-xs"
          title={`Open the live LaTeX editor for ${item.source}`}
        >
          <Pencil size={12} /> Edit LaTeX
        </Link>
      ) : null}
      {hasSource ? (
        <button
          className="btn-ghost text-xs"
          onClick={onCompile}
          disabled={compiling}
          title="Recompile the .tex source to PDF"
        >
          {compiling ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Hammer size={12} />
          )}
          {hasPdf ? "Recompile" : "Compile"}
        </button>
      ) : null}
      {hasPdf ? (
        <a
          className="btn-ghost text-xs"
          href={api.artifactUrl(jobId, item.pdf)}
          download
          title={`Download ${item.pdf}`}
        >
          <Download size={12} /> Download
        </a>
      ) : null}
      {hasPdf ? (
        <a
          className="btn-ghost text-xs"
          href={api.artifactUrl(jobId, item.pdf)}
          target="_blank"
          rel="noreferrer"
          title="Open PDF in a new tab"
        >
          <ExternalLink size={12} />
        </a>
      ) : null}
    </div>
  );
}

interface PreviewBodyProps {
  jobId: string;
  item: PreviewItem;
  hasPdf: boolean;
  hasSource: boolean;
  pdfUrl: string;
}

function PreviewBody({
  jobId,
  item,
  hasPdf,
  hasSource,
  pdfUrl,
}: PreviewBodyProps) {
  // The iframe key combines pdf name + version so switching tabs
  // and recompiling both force a remount — Chromium's PDF viewer
  // doesn't always honor URL query changes otherwise.
  const iframeKey = useMemo(() => `${item.pdf}-${pdfUrl}`, [item.pdf, pdfUrl]);

  if (hasPdf) {
    return (
      <iframe
        key={iframeKey}
        src={pdfUrl}
        title={`${item.label} preview`}
        className="h-[75vh] w-full bg-slate-950"
      />
    );
  }
  if (hasSource) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-10 text-center">
        <Hammer size={20} className="text-slate-500" />
        <p className="max-w-md text-sm text-slate-300">
          The LaTeX source for{" "}
          <span className="font-mono text-slate-100">{item.source}</span> is on
          disk, but no PDF has been compiled yet. Hit{" "}
          <span className="font-semibold">Compile</span> above to render it
          now, or open the editor to tweak the source first.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            to={`/jobs/${jobId}/edit/${item.source}`}
            className="btn-secondary"
          >
            <Pencil size={14} /> Open LaTeX editor
          </Link>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center justify-center gap-3 p-10 text-center">
      <FileText size={20} className="text-slate-500" />
      <p className="max-w-md text-sm text-slate-400">
        No {item.label.toLowerCase()} has been generated yet for this job.
        Tailor the resume + cover letter from the buttons above.
      </p>
    </div>
  );
}
