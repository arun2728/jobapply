import { lazy, Suspense } from "react";
import { Loader2 } from "lucide-react";
import { Route, Routes } from "react-router-dom";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import JobDetail from "@/pages/JobDetail";
import Freeform from "@/pages/Freeform";
import Searches from "@/pages/Searches";
import NotFound from "@/pages/NotFound";

// CodeMirror pulls in ~400 KB of JS, so we code-split the editor
// page — users only pay that bundle cost when they actually open it.
const ArtifactEditor = lazy(() => import("@/pages/ArtifactEditor"));

function EditorFallback() {
  return (
    <div className="card flex items-center gap-2 p-6 text-sm text-slate-300">
      <Loader2 size={16} className="animate-spin" /> Loading editor…
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/jobs/:jobId" element={<JobDetail />} />
        <Route
          path="/jobs/:jobId/edit/:name"
          element={
            <Suspense fallback={<EditorFallback />}>
              <ArtifactEditor />
            </Suspense>
          }
        />
        <Route path="/freeform" element={<Freeform />} />
        <Route path="/searches" element={<Searches />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
