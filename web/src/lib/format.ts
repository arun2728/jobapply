/** Formatting helpers shared by the UI. */

export function formatStatus(status: string): {
  label: string;
  className: string;
} {
  switch (status) {
    case "done":
      return { label: "Tailored", className: "bg-white/10 text-white" };
    case "tailored":
      return { label: "Tailored", className: "bg-white/10 text-white" };
    case "cached":
      return {
        label: "Cached",
        className: "bg-neutral-800 text-neutral-400",
      };
    case "skipped":
      return { label: "Low fit", className: "bg-neutral-800 text-neutral-500" };
    case "failed":
      return { label: "Failed", className: "bg-red-500/10 text-red-400" };
    case "pending":
      return {
        label: "Pending",
        className: "bg-neutral-800 text-neutral-400",
      };
    case "rendered":
      return { label: "Rendered", className: "bg-white/10 text-neutral-300" };
    default:
      return {
        label: status || "Unknown",
        className: "bg-neutral-800 text-neutral-400",
      };
  }
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return (score * 100).toFixed(0) + "%";
}

export function pickAcceptableUrl(job: {
  apply_url?: string | null;
  job_url?: string | null;
}): string | null {
  return job.apply_url || job.job_url || null;
}

export function shortHostname(url: string | null | undefined): string {
  if (!url) return "";
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const t = new Date(iso).getTime();
    const diff = Date.now() - t;
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 48) return `${hr}h ago`;
    const day = Math.floor(hr / 24);
    return `${day}d ago`;
  } catch {
    return "";
  }
}
