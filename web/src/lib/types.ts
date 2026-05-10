// Mirrors the FastAPI models in `jobapply/server.py` and the
// JobRecord shape from `jobapply/models.py`. Kept narrow and only
// includes fields the UI actually reads.

export type LedgerStatus =
  | "pending"
  | "tailored"
  | "rendered"
  | "done"
  | "skipped"
  | "failed"
  | "cached";

export interface FitScore {
  score: number;
  rationale?: string;
  missing_keywords?: string[];
  must_haves_present?: string[];
}

export interface ApplicationHints {
  emails?: string[];
  primary_email?: string | null;
  subject_line?: string | null;
  instructions?: string[];
}

export interface JobArtifacts {
  job_json?: string | null;
  resume_md?: string | null;
  resume_pdf?: string | null;
  resume_tex?: string | null;
  resume_latex_pdf?: string | null;
  cover_letter_md?: string | null;
  cover_letter_pdf?: string | null;
  cover_letter_tex?: string | null;
  cover_letter_latex_pdf?: string | null;
  networking_json?: string | null;
}

export interface ContactInfo {
  email?: string;
  phone?: string;
  location?: string;
  portfolio?: string;
  github?: string;
  linkedin?: string;
  medium?: string;
  twitter?: string;
}

export interface ExperienceRole {
  company: string;
  role: string;
  dates?: string;
  bullets?: string[];
}

export interface EducationItem {
  school?: string;
  degree?: string;
  dates?: string;
  gpa?: string;
  coursework?: string;
  details?: string;
}

export interface ProjectItem {
  name: string;
  bullets?: string[];
}

export interface TailoredResume {
  document_title?: string;
  contact_line?: string;
  contact?: ContactInfo;
  summary?: string;
  skills?: string[];
  experience?: ExperienceRole[];
  projects?: ProjectItem[];
  education?: EducationItem[];
}

export interface CoverLetter {
  header?: string;
  opening?: string;
  body?: string;
  closing?: string;
}

export interface JobRecord {
  job_id: string;
  title?: string;
  company?: string;
  location?: string;
  description?: string;
  job_url?: string | null;
  apply_url?: string | null;
  site?: string;
  status: LedgerStatus;
  fit?: FitScore | null;
  application?: ApplicationHints | null;
  tailored_resume?: TailoredResume | null;
  cover_letter?: CoverLetter | null;
  artifacts?: JobArtifacts;
  error?: string | null;
  processed_at?: string | null;
  available_artifacts?: Record<string, string | null>;
  job_dir_relative?: string;
}

export interface JobsListResponse {
  workspace: string;
  total: number;
  jobs: JobRecord[];
}

export interface ServerStatus {
  workspace: string;
  workspace_total_jobs: number;
  profile_path: string | null;
  profile_loaded: boolean;
  profile_name: string;
  provider: string;
  model: string;
  sites: string[];
  results_wanted: number;
  web_dist_present: boolean;
}

export interface SearchHistoryRow {
  id: number;
  command: string;
  search_input: Record<string, unknown>;
  provider: string;
  model: string;
  started_at: string | null;
  finished_at: string | null;
  fetched: number;
  new_jobs: number;
  duplicate_jobs: number;
}

export type TaskStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface TaskRecord {
  task_id: string;
  kind: string;
  status: TaskStatus;
  progress: { label: string; percent: number; log: string[] };
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  metadata: Record<string, unknown>;
}

export interface EmailDraft {
  to: string;
  subject: string;
  body: string;
  text: string;
  saved_to?: string;
}

export interface EmailHint {
  primary_email: string | null;
  subject_line: string | null;
  instructions: string[];
}
