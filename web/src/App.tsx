import { Route, Routes } from "react-router-dom";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import JobDetail from "@/pages/JobDetail";
import Freeform from "@/pages/Freeform";
import Searches from "@/pages/Searches";
import NotFound from "@/pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/jobs/:jobId" element={<JobDetail />} />
        <Route path="/freeform" element={<Freeform />} />
        <Route path="/searches" element={<Searches />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
