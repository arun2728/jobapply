import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Eye,
  Hammer,
  Loader2,
  RotateCcw,
  Save,
} from "lucide-react";
import CodeMirror from "@uiw/react-codemirror";
import { StreamLanguage } from "@codemirror/language";
import { stex } from "@codemirror/legacy-modes/mode/stex";
import { EditorView } from "@codemirror/view";
import {
  useArtifactText,
  useCompileArtifact,
  useJob,
  useSaveArtifact,
} from "@/lib/hooks";
import { api } from "@/lib/api";

// Whitelist mirrors the FastAPI ``EDITABLE_ARTIFACTS`` set.
const TABS = [
  { name: "resume.tex", label: "Resume (LaTeX)" },
  { name: "cover_letter.tex", label: "Cover letter (LaTeX)" },
  { name: "resume.md", label: "Resume (Markdown)" },
  { name: "cover_letter.md", label: "Cover letter (Markdown)" },
] as const;

const PDF_MAP: Record<string, string | null> = {
  "resume.tex": "resume.pdf",
  "cover_letter.tex": "cover_letter.pdf",
  "resume.md": null,
  "cover_letter.md": null,
};

type ArtifactName = (typeof TABS)[number]["name"];

function isEditable(name: string): name is ArtifactName {
  return TABS.some((t) => t.name === name);
}

export default function ArtifactEditor() {
  const { jobId, name } = useParams<{ jobId: string; name: string }>();
  const navigate = useNavigate();
  const job = useJob(jobId);

  useEffect(() => {
    if (name && !isEditable(name)) {
      navigate(`/jobs/${jobId}/edit/resume.tex`, { replace: true });
    }
  }, [name, jobId, navigate]);

  if (!jobId || !name || !isEditable(name)) return null;

  return <Editor jobId={jobId} name={name} job={job} />;
}

interface EditorProps {
  jobId: string;
  name: ArtifactName;
  job: ReturnType<typeof useJob>;
}

function Editor({ jobId, name, job }: EditorProps) {
  const text = useArtifactText(jobId, name);
  const save = useSaveArtifact(jobId, name);
  const compile = useCompileArtifact(jobId, name);

  const [draft, setDraft] = useState<string>("");
  const baselineRef = useRef<string>("");
  const [pdfVersion, setPdfVersion] = useState<number>(() => Date.now());

  useEffect(() => {
    if (text.data !== undefined) {
      setDraft(text.data);
      baselineRef.current = text.data;
    }
  }, [text.data]);

  const dirty = draft !== baselineRef.current;
  const pdfName = PDF_MAP[name];
  const pdfAvailable = Boolean(
    pdfName && job.data?.available_artifacts?.[pdfName],
  );

  const onSave = async () => {
    const snap = draft;
    await save.mutateAsync(snap);
    baselineRef.current = snap;
  };

  const onSaveAndCompile = async () => {
    const snap = draft;
    if (snap !== baselineRef.current) {
      await save.mutateAsync(snap);
      baselineRef.current = snap;
    }
    if (pdfName) {
      await compile.mutateAsync();
      setPdfVersion(Date.now());
    }
  };

  const onRevert = () => {
    setDraft(baselineRef.current);
  };

  const extensions = useMemo(() => {
    const exts = [
      EditorView.lineWrapping,
      EditorView.theme({
        "&": { fontSize: "13px" },
        ".cm-content": { fontFamily: "ui-monospace, SFMono-Regular, monospace" },
      }),
    ];
    if (name.endsWith(".tex")) {
      exts.push(StreamLanguage.define(stex));
    }
    return exts;
  }, [name]);

  const tabName = TABS.find((t) => t.name === name)?.label ?? name;

  return (
    <div className="flex h-[calc(100vh-230px)] min-h-[520px] flex-col gap-3 overflow-hidden">
      <div className="flex flex-wrap items-center gap-2">
        <Link to={`/jobs/${jobId}`} className="btn-ghost">
          <ArrowLeft size={14} /> Back to job
        </Link>
        <h1 className="text-base font-semibold text-white">
          {job.data?.title || job.data?.company || jobId}
          <span className="ml-2 font-mono text-xs text-neutral-600">
            {tabName}
          </span>
        </h1>
        <span
          className={
            "ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium " +
            (dirty
              ? "bg-yellow-500/10 text-yellow-200 ring-1 ring-yellow-500/30"
              : "bg-neutral-800 text-neutral-500")
          }
        >
          {dirty ? "unsaved changes" : "in sync with disk"}
        </span>
      </div>

      <nav className="flex flex-wrap gap-1 border-b border-neutral-800 pb-1 text-sm">
        {TABS.map((t) => (
          <Link
            key={t.name}
            to={`/jobs/${jobId}/edit/${t.name}`}
            className={
              "rounded-md px-3 py-1.5 transition-colors " +
              (t.name === name
                ? "bg-neutral-800 text-white"
                : "text-neutral-500 hover:bg-neutral-900 hover:text-neutral-100")
            }
          >
            {t.label}
          </Link>
        ))}
      </nav>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card flex min-h-0 flex-col overflow-hidden p-0">
          <div className="flex flex-shrink-0 items-center gap-2 border-b border-neutral-800 px-3 py-2">
            <Hammer size={14} className="text-neutral-500" />
            <span className="text-xs uppercase tracking-wide text-neutral-500">
              Source
            </span>
            <div className="ml-auto flex items-center gap-2">
              <button
                className="btn-ghost text-xs"
                onClick={onRevert}
                disabled={!dirty || save.isPending}
              >
                <RotateCcw size={12} /> Revert
              </button>
              <button
                className="btn-secondary text-xs"
                onClick={onSave}
                disabled={!dirty || save.isPending}
              >
                {save.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Save size={12} />
                )}
                Save
              </button>
              {pdfName ? (
                <button
                  className="btn-primary text-xs"
                  onClick={onSaveAndCompile}
                  disabled={save.isPending || compile.isPending}
                >
                  {compile.isPending ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Hammer size={12} />
                  )}
                  Save &amp; compile PDF
                </button>
              ) : null}
            </div>
          </div>

          {text.isLoading ? (
            <div className="flex flex-1 items-center justify-center gap-2 text-sm text-neutral-500">
              <Loader2 size={16} className="animate-spin" /> Loading source…
            </div>
          ) : text.error ? (
            <div className="flex flex-1 items-center gap-2 p-4 text-sm text-red-400">
              <AlertTriangle size={16} />{" "}
              {String((text.error as Error)?.message ?? "Failed to load")}
            </div>
          ) : (
            <div className="min-h-0 flex-1">
              <CodeMirror
                value={draft}
                onChange={(v) => setDraft(v)}
                theme="dark"
                height="100%"
                style={{ height: "100%" }}
                extensions={extensions}
                basicSetup={{
                  lineNumbers: true,
                  highlightActiveLine: true,
                  foldGutter: true,
                  bracketMatching: true,
                  closeBrackets: true,
                  highlightSelectionMatches: false,
                }}
              />
            </div>
          )}

          <StatusFooter
            saveError={save.error as Error | null}
            saveSuccess={save.isSuccess && !dirty}
            compileError={compile.error as Error | null}
            compileSuccess={compile.isSuccess}
            backend={compile.data?.backend}
          />
        </div>

        <div className="card flex min-h-0 flex-col overflow-hidden p-0">
          <div className="flex flex-shrink-0 items-center gap-2 border-b border-neutral-800 px-3 py-2">
            <Eye size={14} className="text-neutral-500" />
            <span className="text-xs uppercase tracking-wide text-neutral-500">
              {pdfName ? `Preview · ${pdfName}` : "Preview"}
            </span>
            {pdfAvailable && pdfName ? (
              <a
                className="ml-auto text-xs text-neutral-400 hover:text-white"
                href={api.artifactUrl(jobId, pdfName)}
                target="_blank"
                rel="noreferrer"
              >
                Open in new tab ↗
              </a>
            ) : null}
          </div>
          {pdfName && pdfAvailable ? (
            <iframe
              key={`${pdfName}-${pdfVersion}`}
              src={`${api.artifactUrl(jobId, pdfName)}?v=${pdfVersion}`}
              className="min-h-0 w-full flex-1 bg-black"
              title={`${pdfName} preview`}
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 overflow-auto p-6 text-center text-sm text-neutral-500">
              <Hammer size={20} className="text-neutral-600" />
              <p className="max-w-xs">
                {pdfName
                  ? "No PDF on disk yet. Click "
                  : "Markdown sources don't compile to PDF directly. Edit the .tex file or "}
                <span className="font-semibold text-neutral-300">
                  {pdfName
                    ? "Save & compile PDF"
                    : "use the markdown tab in the artifacts list."}
                </span>
                {pdfName ? " to render this source." : ""}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface FooterProps {
  saveError: Error | null;
  saveSuccess: boolean;
  compileError: Error | null;
  compileSuccess: boolean;
  backend?: string;
}

function StatusFooter({
  saveError,
  saveSuccess,
  compileError,
  compileSuccess,
  backend,
}: FooterProps) {
  const hasMessage =
    saveError || saveSuccess || compileError || compileSuccess;
  if (!hasMessage) return null;

  return (
    <div className="flex-shrink-0 border-t border-neutral-800 px-3 py-2 text-xs">
      {compileError ? (
        <div className="flex items-start gap-2 text-red-400">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <span>{compileError.message}</span>
        </div>
      ) : compileSuccess ? (
        <div className="flex items-center gap-2 text-neutral-300">
          <CheckCircle2 size={14} />
          PDF rebuilt via{" "}
          <span className="font-mono">{backend || "tex_to_pdf"}</span>.
        </div>
      ) : saveError ? (
        <div className="flex items-start gap-2 text-red-400">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <span>{saveError.message}</span>
        </div>
      ) : saveSuccess ? (
        <div className="flex items-center gap-2 text-neutral-300">
          <CheckCircle2 size={14} /> Saved to disk.
        </div>
      ) : null}
    </div>
  );
}
