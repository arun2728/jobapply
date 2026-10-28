import { useEffect, useState } from "react";
import { Loader2, Mail, X } from "lucide-react";
import {
  useActiveTaskFor,
  useEmailHint,
  useProviders,
  useStartEmail,
  useTaskPoll,
} from "@/lib/hooks";
import type { EmailDraft } from "@/lib/types";

interface Props {
  jobId: string;
  open: boolean;
  onClose: () => void;
  defaultRecipient?: string;
  isTailored?: boolean;
}

export default function EmailModal({
  jobId,
  open,
  onClose,
  defaultRecipient,
  isTailored,
}: Props) {
  const hint = useEmailHint(open ? jobId : undefined);
  const providers = useProviders();
  const [recipient, setRecipient] = useState(defaultRecipient ?? "");
  const [context, setContext] = useState("");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const start = useStartEmail(jobId);
  const { task } = useTaskPoll(taskId);
  const live = useActiveTaskFor(jobId, ["email"]);

  useEffect(() => {
    if (open && hint.data?.primary_email && !recipient) {
      setRecipient(hint.data.primary_email);
    }
    if (open && hint.data?.subject_line && !context) {
      setContext(`Use subject line: ${hint.data.subject_line}`);
    }
  }, [open, hint.data]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open || !providers.data) return;
    setProvider(providers.data.active_provider);
    setModel(providers.data.active_model);
  }, [open, providers.data]);

  useEffect(() => {
    if (!open) return;
    if (taskId) return;
    if (live.task) setTaskId(live.task.task_id);
  }, [open, live.task, taskId]);

  if (!open) return null;
  const draft = task?.result as EmailDraft | undefined;
  const meta = providers.data?.providers.find((p) => p.name === provider);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipient.trim() || !provider.trim() || !model.trim()) return;
    try {
      const t = await start.mutateAsync({
        recipient: recipient.trim(),
        additional_info: context.trim(),
        provider: provider.trim(),
        model: model.trim(),
      });
      setTaskId(t.task_id);
    } catch {
      // surfaced via mutation error state
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className="card w-full max-w-2xl space-y-4 border-neutral-700 p-6">
        <div className="flex items-center gap-2 text-base font-semibold text-white">
          <Mail size={18} className="text-neutral-400" />
          Draft application email
          <button
            className="ml-auto text-neutral-500 hover:text-white"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {!draft ? (
          <form onSubmit={onSubmit} className="space-y-4">
            <div
              className={
                "rounded-md border px-3 py-2 text-xs " +
                (isTailored
                  ? "border-neutral-700 bg-neutral-900 text-neutral-300"
                  : "border-yellow-800/40 bg-yellow-950/20 text-yellow-200")
              }
            >
              {isTailored
                ? "Tailored resume + cover letter detected — the draft will reference them as attachments."
                : "No tailored resume yet — the draft will be grounded in the JD + your profile and won't claim attachments. Tailor first if you want a polished email referencing your tailored docs."}
            </div>
            <label className="block">
              <span className="label">Recipient email</span>
              <input
                className="input"
                type="email"
                placeholder="recruiter@acme.com"
                value={recipient}
                onChange={(e) => setRecipient(e.target.value)}
                required
              />
              {hint.data?.primary_email ? (
                <p className="mt-1 text-xs text-neutral-500">
                  Detected from JD:{" "}
                  <span className="font-mono">
                    {hint.data.primary_email}
                  </span>
                </p>
              ) : null}
            </label>
            <label className="block">
              <span className="label">
                Additional context (referrals, availability, …)
              </span>
              <textarea
                className="input min-h-[88px]"
                placeholder="Referred by Bob — available to start in two weeks."
                value={context}
                onChange={(e) => setContext(e.target.value)}
              />
              {hint.data?.subject_line ? (
                <p className="mt-1 text-xs text-neutral-500">
                  Recruiter requested subject:{" "}
                  <span className="font-mono">{hint.data.subject_line}</span>
                </p>
              ) : null}
            </label>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="label">Provider</span>
                <select
                  className="input"
                  value={provider}
                  disabled={
                    providers.isLoading ||
                    start.isPending ||
                    task?.status === "running"
                  }
                  onChange={(e) => {
                    const next = e.target.value;
                    setProvider(next);
                    const m = providers.data?.providers.find(
                      (p) => p.name === next,
                    );
                    if (m) setModel(m.default_model);
                  }}
                >
                  {providers.data?.providers.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.name}
                      {p.configured ? "" : " (not configured)"}
                      {p.has_credentials ? "" : " — no credentials"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="label">Model</span>
                <input
                  className="input font-mono text-sm"
                  value={model}
                  placeholder={meta?.fallback_model}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={start.isPending || task?.status === "running"}
                  required
                />
              </label>
            </div>
            {meta && !meta.has_credentials ? (
              <p className="-mt-1 text-xs text-red-400">
                No API key found for {provider}. The request will fail
                unless you set one via{" "}
                <code className="font-mono">jobapply config</code> or an
                env var.
              </p>
            ) : meta && model !== meta.default_model ? (
              <p className="-mt-1 text-xs text-neutral-500">
                Override — your{" "}
                <code className="font-mono">jobapply.toml</code> default
                for <span className="font-mono">{provider}</span> is{" "}
                <span className="font-mono">{meta.default_model}</span>.
              </p>
            ) : (
              <p className="-mt-1 text-xs text-neutral-600">
                Defaults loaded from{" "}
                <code className="font-mono">jobapply.toml</code>. Change
                them for this draft only.
              </p>
            )}
            {task && task.status !== "succeeded" ? (
              <div className="flex items-center gap-2 text-sm text-neutral-400">
                <Loader2 size={14} className="animate-spin text-neutral-400" />
                {task.progress.label || "Drafting…"}
              </div>
            ) : null}
            {start.isError ? (
              <p className="text-sm text-red-400">
                {String(start.error?.message ?? start.error)}
              </p>
            ) : null}
            {task?.status === "failed" ? (
              <pre className="max-h-32 overflow-auto rounded bg-red-950/40 p-2 text-xs text-red-200">
                {task.error}
              </pre>
            ) : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="btn-secondary"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn-primary"
                disabled={
                  start.isPending ||
                  task?.status === "running" ||
                  providers.isLoading ||
                  !provider.trim() ||
                  !model.trim()
                }
              >
                {start.isPending || task?.status === "running" ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Mail size={16} />
                )}
                Generate email
              </button>
            </div>
          </form>
        ) : (
          <div className="space-y-3">
            <div className="rounded-md border border-neutral-800 bg-black p-3 text-sm">
              <div className="text-xs text-neutral-500">To</div>
              <div className="text-white">{draft.to}</div>
              <div className="mt-2 text-xs text-neutral-500">Subject</div>
              <div className="text-white">{draft.subject}</div>
              <div className="mt-2 text-xs text-neutral-500">Body</div>
              <pre className="whitespace-pre-wrap font-sans text-white">
                {draft.body}
              </pre>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                className="btn-secondary"
                onClick={() => {
                  navigator.clipboard
                    ?.writeText(draft.text)
                    .catch(() => {});
                }}
              >
                Copy to clipboard
              </button>
              <a
                className="btn-primary"
                href={`mailto:${encodeURIComponent(draft.to)}?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(draft.body)}`}
              >
                Open in mail client
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
