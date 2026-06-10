// Mirrors the response shapes in specs/openapi.yaml. Kept hand-written and small
// (the console only consumes a subset); the server is the source of truth.

export type Role = "admin" | "member" | "viewer";
export type ProjectType = "rag" | "finetune";

export interface TeamSummary {
  id: string;
  name: string;
  role: Role;
}

export interface User {
  id: string;
  email: string;
  org_id: string;
  teams: TeamSummary[];
}

export interface Project {
  id: string;
  name: string;
  type: ProjectType;
  status: string;
  base_model: string;
  description: string | null;
  team_id: string;
  created_at: string;
}

export type FileStatus = "pending" | "processing" | "indexed" | "failed";
export interface ProjectFile {
  id: string;
  filename: string;
  status: FileStatus;
  num_chunks: number | null;
  size_bytes: number;
  uploaded_at: string;
}

export type DatasetStatus = "uploaded" | "validating" | "valid" | "invalid";
export interface Dataset {
  id: string;
  name: string;
  status: DatasetStatus;
  num_samples: number | null;
  validation_error: string | null;
  created_at: string;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export interface TrainingJob {
  id: string;
  status: JobStatus;
  progress: number;
  logs: string | null;
  adapter_path: string | null;
  eval_score: number | null;
  eval_passed: boolean | null;
  error_message: string | null;
  created_at: string;
}

export interface Endpoint {
  id: string;
  slug: string;
  status: string;
  base_model: string;
  adapter_path: string | null;
  project_type: ProjectType;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  is_active: boolean;
  created_at: string;
}

export interface ApiKeyCreated {
  id: string;
  name: string;
  key: string; // full key — shown once
  prefix: string;
}

export interface UsageDay {
  day: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  request_count: number;
}

export interface UsageResponse {
  project_id: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_requests: number;
  days: UsageDay[];
}

export interface Citation {
  index?: number;
  source?: string;
  text?: string;
  [k: string]: unknown;
}

export interface ChatCompletion {
  id: string;
  choices: { index: number; message: { role: string; content: string }; finish_reason: string }[];
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  citations?: Citation[];
}
