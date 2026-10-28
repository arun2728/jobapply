import { useEffect, useState } from "react";
import { Loader2, Wand2, X } from "lucide-react";
import { useProviders } from "@/lib/hooks";

export interface TailorOptions {
  provider: string;
  model: string;
  no_pdf: boolean;
  /** Only meaningful when ``showForce`` is true (batch mode); the
   *  parent forwards this to the run endpoint to re-tailor jobs
   *  already in ``done`` status. */
  force: boolean;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onConfirm: (options: TailorOptions) => Promise<void> | void;
  pending?: boolean;
  title?: string;
  jobTitle?: string;
  jobCount?: number;
}

export default function TailorModal({
  open,
  onClose,
  onConfirm,
  pending,
  title,
  jobTitle,
  jobCount,
}: Props) {
  const providers = useProviders();
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [noPdf, setNoPdf] = useState(false);
  const [force, setForce] = useState(false);
  const isBatch = typeof jobCount === "number";

  useEffect(() => {
    if (!open || !providers.data) return;
    setProvider(providers.data.active_provider);
    setModel(providers.data.active_model);
  }, [open, providers.data]);

  if (!open) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pending) return;
    if (!provider.trim() || !model.trim()) return;
    await onConfirm({
      provider: provider.trim(),
      model: model.trim(),
      no_pdf: noPdf,
      force,
    });
  };

  const meta = providers.data?.providers.find((p) => p.name === provider);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <form
        onSubmit={submit}
        className="card w-full max-w-lg space-y-4 border-neutral-700 p-6"
      >
        <div className="flex items-center gap-2 text-base font-semibold text-white">
          <Wand2 size={18} className="text-neutral-400" />
          {title ??
            (isBatch
              ? "Tailor selected jobs"
              : "Tailor resume + cover letter")}
          <button
            type="button"
            className="ml-auto text-neutral-500 hover:text-white"
            onClick={onClose}
            aria-label="Close"
            disabled={pending}
          >
            <X size={18} />
          </button>
        </div>
        {isBatch ? (
          <p className="text-sm text-neutral-500">
            About to tailor{" "}
            <span className="font-medium text-neutral-200">
              {jobCount} {jobCount === 1 ? "job" : "jobs"}
            </span>{" "}
            in sequence. Each one will run resume + cover-letter agents
            against your <code className="font-mono">profile.json</code>.
          </p>
        ) : jobTitle ? (
          <p className="text-sm text-neutral-500">
            Tailoring for{" "}
            <span className="font-medium text-neutral-200">{jobTitle}</span>.
          </p>
        ) : null}

        <label className="block">
          <span className="label">Provider</span>
          <select
            className="input"
            value={provider}
            disabled={providers.isLoading || pending}
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
          {meta && !meta.has_credentials ? (
            <p className="mt-1 text-xs text-red-400">
              No API key found for this provider. The request will fail
              unless you set one via{" "}
              <code className="font-mono">jobapply config</code> or an env
              var.
            </p>
          ) : null}
        </label>

        <label className="block">
          <span className="label">Model</span>
          <input
            className="input font-mono text-sm"
            value={model}
            placeholder={meta?.fallback_model}
            onChange={(e) => setModel(e.target.value)}
            disabled={pending}
            required
          />
          {meta && model !== meta.default_model ? (
            <p className="mt-1 text-xs text-neutral-500">
              Override — your{" "}
              <code className="font-mono">jobapply.toml</code> default for{" "}
              <span className="font-mono">{provider}</span> is{" "}
              <span className="font-mono">{meta.default_model}</span>.
            </p>
          ) : (
            <p className="mt-1 text-xs text-neutral-600">
              Default loaded from{" "}
              <code className="font-mono">jobapply.toml</code>. Change it for
              this run only.
            </p>
          )}
        </label>

        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm text-neutral-400">
            <input
              type="checkbox"
              className="accent-white"
              checked={noPdf}
              onChange={(e) => setNoPdf(e.target.checked)}
              disabled={pending}
            />
            Skip PDF rendering (markdown + LaTeX only — faster)
          </label>
          {isBatch ? (
            <label className="flex items-center gap-2 text-sm text-neutral-400">
              <input
                type="checkbox"
                className="accent-white"
                checked={force}
                onChange={(e) => setForce(e.target.checked)}
                disabled={pending}
              />
              Force re-tailor even if already done
            </label>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            className="btn-secondary"
            onClick={onClose}
            disabled={pending}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={
              pending ||
              providers.isLoading ||
              !provider.trim() ||
              !model.trim()
            }
          >
            {pending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Wand2 size={14} />
            )}
            Start tailoring
          </button>
        </div>
      </form>
    </div>
  );
}
