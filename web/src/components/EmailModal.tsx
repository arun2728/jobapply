import { useEffect, useState } from "react";
import { Loader2, Mail, X } from "lucide-react";
import { useStartEmail, useEmailHint, useTaskPoll } from "@/lib/hooks";
import type { EmailDraft } from "@/lib/types";

interface Props {
  jobId: string;
  open: boolean;
  onClose: () => void;
  defaultRecipient?: string;
}

/** Modal that drafts and shows the application email. The recipient
 *  defaults to whatever the JD-extractor parsed out of the JD body
 *  (so direct-recruiter postings don't require user input). */
export default function EmailModal({
  jobId,
  open,
  onClose,
  defaultRecipient,
}: Props) {
  const hint = useEmailHint(open ? jobId : undefined);
  const [recipient, setRecipient] = useState(defaultRecipient ?? "");
  const [context, setContext] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const start = useStartEmail(jobId);
  const { task } = useTaskPoll(taskId);

  useEffect(() => {
    if (open && hint.data?.primary_email && !recipient) {
      setRecipient(hint.data.primary_email);
    }
    if (open && hint.data?.subject_line && !context) {
      setContext(`Use subject line: ${hint.data.subject_line}`);
    }
  }, [open, hint.data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;
  const draft = task?.result as EmailDraft | undefined;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipient.trim()) return;
    try {
      const t = await start.mutateAsync({
        recipient: recipient.trim(),
        additional_info: context.trim(),
      });
      setTaskId(t.task_id);
    } catch {
      // surfaced via mutation error state
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
      <div className="card w-full max-w-2xl space-y-4 border-slate-700 p-6">
        <div className="flex items-center gap-2 text-base font-semibold text-slate-100">
          <Mail size={18} className="text-brand-400" />
          Draft application email
          <button
            className="ml-auto text-slate-400 hover:text-slate-100"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {!draft ? (
          <form onSubmit={onSubmit} className="space-y-4">
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
                <p className="mt-1 text-xs text-slate-400">
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
                <p className="mt-1 text-xs text-slate-400">
                  Recruiter requested subject:{" "}
                  <span className="font-mono">{hint.data.subject_line}</span>
                </p>
              ) : null}
            </label>
            {task && task.status !== "succeeded" ? (
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <Loader2 size={14} className="animate-spin text-brand-400" />
                {task.progress.label || "Drafting…"}
              </div>
            ) : null}
            {start.isError ? (
              <p className="text-sm text-rose-400">
                {String(start.error?.message ?? start.error)}
              </p>
            ) : null}
            {task?.status === "failed" ? (
              <pre className="max-h-32 overflow-auto rounded bg-rose-900/40 p-2 text-xs text-rose-100">
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
                disabled={start.isPending || task?.status === "running"}
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
            <div className="rounded-md border border-slate-700 bg-slate-950/40 p-3 text-sm">
              <div className="text-xs text-slate-400">To</div>
              <div className="text-slate-100">{draft.to}</div>
              <div className="mt-2 text-xs text-slate-400">Subject</div>
              <div className="text-slate-100">{draft.subject}</div>
              <div className="mt-2 text-xs text-slate-400">Body</div>
              <pre className="whitespace-pre-wrap font-sans text-slate-100">
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
