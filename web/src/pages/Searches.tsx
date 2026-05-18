import { Loader2, History } from "lucide-react";
import { useSearches } from "@/lib/hooks";
import { relativeTime } from "@/lib/format";

export default function Searches() {
  const q = useSearches();
  if (q.isLoading) {
    return (
      <div className="card flex items-center gap-2 p-6 text-sm text-slate-400">
        <Loader2 size={16} className="animate-spin" /> Loading…
      </div>
    );
  }
  const rows = q.data?.searches ?? [];
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <History size={20} className="text-brand-400" />
        <h1 className="text-2xl font-bold tracking-tight">Search history</h1>
      </div>
      {rows.length === 0 ? (
        <div className="card p-8 text-center text-sm text-slate-400">
          No searches yet. Run one from the Jobs page.
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/70 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-2 text-left">#</th>
                <th className="px-4 py-2 text-left">Command</th>
                <th className="px-4 py-2 text-left">Started</th>
                <th className="px-4 py-2 text-left">Provider / Model</th>
                <th className="px-4 py-2 text-right">Fetched</th>
                <th className="px-4 py-2 text-right text-brand-300">New</th>
                <th className="px-4 py-2 text-right text-amber-300">Dup</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rows.map((r) => {
                const titles = (r.search_input?.titles as string[]) ?? [];
                return (
                  <tr key={r.id} className="hover:bg-slate-900/50">
                    <td className="px-4 py-2 text-xs text-slate-400">
                      #{r.id}
                    </td>
                    <td className="px-4 py-2">
                      <div className="font-medium text-slate-100">
                        {r.command}
                      </div>
                      {titles.length ? (
                        <div className="text-xs text-slate-400">
                          {titles.join(", ")}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-4 py-2 text-xs text-slate-400">
                      {relativeTime(r.started_at)}
                    </td>
                    <td className="px-4 py-2 text-xs text-slate-400">
                      {r.provider || "—"}
                      {r.model ? ` / ${r.model}` : ""}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs">
                      {r.fetched}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-brand-300">
                      {r.new_jobs}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-amber-300">
                      {r.duplicate_jobs}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
