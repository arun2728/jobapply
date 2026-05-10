import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="card p-12 text-center">
      <h1 className="text-2xl font-bold text-slate-100">Page not found</h1>
      <p className="mt-2 text-sm text-slate-400">
        That route doesn't exist (yet).
      </p>
      <Link to="/" className="btn-primary mt-4 inline-flex">
        Back to jobs
      </Link>
    </div>
  );
}
