import { useState } from "react";
import { Loader2, Search } from "lucide-react";
import { useStartSearch, useStatus } from "@/lib/hooks";
import type { TaskRecord } from "@/lib/types";

interface Props {
  onTaskStarted: (task: TaskRecord) => void;
}

/** Live JobSpy search form. Submits to /api/search and hands the task
 *  record back to the parent so the page can render progress. */
export default function SearchForm({ onTaskStarted }: Props) {
  const status = useStatus();
  const [titles, setTitles] = useState("");
  const [skills, setSkills] = useState("");
  const [location, setLocation] = useState("");
  const [results, setResults] = useState<number | "">("");
  const [score, setScore] = useState(false);
  const [remote, setRemote] = useState(false);
  const [linkedin, setLinkedin] = useState(true);
  const [force, setForce] = useState(false);
  const start = useStartSearch();

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const titleList = titles
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    if (!titleList.length) return;
    const skillsList = skills
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    try {
      const task = await start.mutateAsync({
        titles: titleList,
        skills: skillsList,
        location: location.trim() || undefined,
        remote,
        results_wanted: typeof results === "number" ? results : undefined,
        score,
        linkedin_descriptions: linkedin,
        force,
      });
      onTaskStarted(task);
    } catch {
      // Errors get rendered via the mutation's error state below.
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className="card space-y-4 border-slate-800/80 bg-slate-900/40 p-5"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
        <Search size={16} className="text-brand-400" />
        Search job boards
        <span className="ml-auto text-xs font-normal text-slate-500">
          Sites: {status.data?.sites?.join(", ") ?? "—"}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label>
          <span className="label">Job titles (comma-separated)</span>
          <input
            className="input"
            placeholder="ML Engineer, Backend Engineer"
            value={titles}
            onChange={(e) => setTitles(e.target.value)}
            required
          />
        </label>
        <label>
          <span className="label">Skills (optional)</span>
          <input
            className="input"
            placeholder="Python, Kubernetes"
            value={skills}
            onChange={(e) => setSkills(e.target.value)}
          />
        </label>
        <label>
          <span className="label">Location</span>
          <input
            className="input"
            placeholder="Remote, San Francisco, …"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </label>
        <label>
          <span className="label">Results wanted</span>
          <input
            className="input"
            type="number"
            min={1}
            max={500}
            placeholder={String(status.data?.results_wanted ?? 30)}
            value={results}
            onChange={(e) =>
              setResults(e.target.value ? Number(e.target.value) : "")
            }
          />
        </label>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-300">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={score}
            onChange={(e) => setScore(e.target.checked)}
            className="accent-brand-500"
          />
          Score against profile
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={remote}
            onChange={(e) => setRemote(e.target.checked)}
            className="accent-brand-500"
          />
          Remote-friendly only
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={linkedin}
            onChange={(e) => setLinkedin(e.target.checked)}
            className="accent-brand-500"
          />
          Fetch LinkedIn descriptions
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={force}
            onChange={(e) => setForce(e.target.checked)}
            className="accent-brand-500"
          />
          Force (ignore dedupe)
        </label>
      </div>
      <div className="flex items-center justify-between">
        {start.isError ? (
          <p className="text-sm text-rose-400">
            {String(start.error?.message ?? start.error)}
          </p>
        ) : (
          <p className="text-xs text-slate-500">
            New jobs are added to the workspace; duplicates are skipped.
          </p>
        )}
        <button
          type="submit"
          className="btn-primary"
          disabled={start.isPending}
        >
          {start.isPending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Search size={16} />
          )}
          Search
        </button>
      </div>
    </form>
  );
}
