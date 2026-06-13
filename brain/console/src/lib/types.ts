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

// §C2.1: per-project aggregate read-model (returned as `summary` on Project)
export interface FileSummaryData {
  total: number;
  indexed: number;
  chunks: number;
}
export interface DatasetSummaryData {
  total: number;
  valid: number;
}
export interface JobSummaryData {
  total: number;
  running: number;
  last_status: string | null;
  last_eval_score: number | null;
  gate_passed: boolean | null;
}
export interface EndpointSummaryData {
  exists: boolean;
  slug: string | null;
  status: string | null;
}
export interface UsageSummaryData {
  requests: number;
  total_tokens: number;
}
export interface ProjectSummary {
  stage: string;
  files: FileSummaryData;
  datasets: DatasetSummaryData;
  jobs: JobSummaryData;
  endpoint: EndpointSummaryData;
  keys_active: number;
  usage_7d: UsageSummaryData;
  last_activity_at: string | null;
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
  summary: ProjectSummary | null;
}

// §C4.4: DB-backed platform setting entry
export interface SettingEntry {
  key: string;
  label: string;
  group: string;
  value: number;
  source: "override" | "env" | "default";
  default: number;
  min: number;
  max: number;
  description: string;
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

export type Modality = "text" | "vision";
export type BestFor = "knowledge" | "behavior" | "code" | "vision";

// One base-model catalog entry (GET /v1/models) — the SSOT the server
// validates Project.base_model against; drives modality-aware UI (§V5).
export interface BaseModelInfo {
  name: string;
  modality: Modality;
  model_type: string;
  description: string | null;
  use_case: string;
  best_for: BestFor[];
  available: boolean;
  train_vram_gb: number | null;
  serve_ram_gb: number | null;
  hf_repo_id: string;
  notes: string;
}

export type DatasetStatus = "uploaded" | "validating" | "valid" | "invalid";
export interface Dataset {
  id: string;
  name: string;
  status: DatasetStatus;
  num_samples: number | null;
  validation_error: string | null;
  created_at: string;
  modality: Modality;
  num_images: number | null;
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

// OpenAI content-parts (§V4): a wire message's content is plain text or an
// array of text / inline-image parts (vision endpoints only).
export type ChatContentPart =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

export interface WireChatMessage {
  role: string;
  content: string | ChatContentPart[];
}

export interface ChatCompletion {
  id: string;
  choices: { index: number; message: { role: string; content: string }; finish_reason: string }[];
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  citations?: Citation[];
}
