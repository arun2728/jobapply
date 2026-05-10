import { NavLink, Outlet } from "react-router-dom";
import {
  Briefcase,
  ClipboardList,
  History,
  PenSquare,
} from "lucide-react";
import { useStatus } from "@/lib/hooks";
import clsx from "clsx";

const navItems = [
  { to: "/", label: "Jobs", icon: ClipboardList, end: true },
  { to: "/freeform", label: "Paste JD", icon: PenSquare },
  { to: "/searches", label: "History", icon: History },
];

export default function Layout() {
  const status = useStatus();
  const total = status.data?.workspace_total_jobs ?? 0;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand-500/20 text-brand-300">
              <Briefcase size={18} />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight">
                JobApply
              </div>
              <div className="text-xs text-slate-500">
                {status.data ? (
                  <>
                    <span className="font-mono">{total}</span>{" "}
                    {total === 1 ? "job" : "jobs"} ·{" "}
                    <span className="text-slate-400">
                      {status.data.provider}/{status.data.model}
                    </span>
                  </>
                ) : (
                  "loading…"
                )}
              </div>
            </div>
          </div>
          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-slate-800 text-white"
                      : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100",
                  )
                }
              >
                <item.icon size={16} />
                <span className="hidden sm:inline">{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-10">
        <Outlet />
      </main>
      <footer className="border-t border-slate-800 px-4 py-4 text-center text-xs text-slate-500 sm:px-6">
        Workspace:{" "}
        <span className="font-mono">{status.data?.workspace ?? "…"}</span> ·
        Profile:{" "}
        {status.data?.profile_loaded ? (
          <span className="text-brand-300">{status.data.profile_name}</span>
        ) : (
          <span className="text-amber-300">
            not loaded — run `jobapply init`
          </span>
        )}
      </footer>
    </div>
  );
}
