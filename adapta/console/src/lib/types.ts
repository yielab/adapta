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
  endpoint: EndpointSummaryData;
  keys_active: number;
  usage_7d: UsageSummaryData;
  last_activity_at: string | null;
}

// E5.4: what the vision base reads per page; property order is the chunk-header order.
export interface ExtractionSchema {
  title?: string | null;
  properties: Record<string, Record<string, unknown>>;
}

export interface Project {
  id: string;
  name: string;
  type: ProjectType;
  status: string;
  base_model: string;
  description: string | null;
  system_prompt: string | null;
  extraction_schema: ExtractionSchema | null;
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
  pages_needing_review?: number;
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
  serve_ram_gb: number | null;
  hf_repo_id: string;
  notes: string;
  /** Weights license id (e.g. "apache-2.0", "qwen-research") — §E1.2 */
  license: string;
  license_url: string;
  /** False for research-only licenses: evaluation only, never the default */
  commercial_use: boolean;
  /** The entry ADAPTA_DEFAULT_MODEL resolves to */
  is_default: boolean;
}

export type DatasetStatus = "uploaded" | "validating" | "valid" | "invalid";
export interface Dataset {
  id: string;
  name: string;
  status: DatasetStatus;
  num_samples: number | null;
  validation_error: string | null;
  created_at: string;
  source_dataset_id: string | null;
  task: string | null;
  kind: "upload" | "rag_eval" | "behavior";
}

export interface DatasetRowsResponse {
  rows: Record<string, unknown>[];
  total: number;
  page: number;
  page_size: number;
}

// Latest RAG-gate result (E5.2); regression is a warning, never a block.
export interface RetrievalQuality {
  run_id: string;
  recall_at_5: number;
  mrr: number;
  n_questions: number;
  run_at: string;
  baseline_recall: number | null;
  delta: number | null;
  regression: boolean;
  running: boolean;
}

export interface RetrievalSummary {
  indexed_chunks: number;
  quality?: RetrievalQuality | null;
}

export interface GoldenSet {
  dataset_id: string;
  name: string;
  num_questions: number;
}

export interface GoldenQuestionResult {
  q: string;
  expected_file: string;
  lang: string | null;
  rank: number | null;
  hit: boolean;
  ms: number;
}

export interface GoldenRun {
  id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  trigger: 'manual' | 'index';
  dataset_id: string | null;
  k: number;
  n_questions: number | null;
  recall_at_5: number | null;
  mrr: number | null;
  p50_ms: number | null;
  baseline_recall: number | null;
  delta: number | null;
  regression: boolean;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  questions: GoldenQuestionResult[];
}

export interface GoldenResults {
  golden_set: GoldenSet | null;
  runs: GoldenRun[];
}

// One held-out row scored by the eval gate (AdapterResponse.eval_metrics.samples).
export interface AdapterEvalSample {
  prompt: string;
  reference: string;
  base: string;
  adapter: string;
}

// The eval gate's verdict (adapta/services/eval_gate.py). Every field is
// optional so a partial/legacy payload never breaks rendering.
export interface AdapterEvalMetrics {
  task?: string;
  n_rows?: number;
  adapter_score?: number;
  base_score?: number;
  delta?: number;
  rule?: string;
  passed?: boolean;
  min_improvement?: number;
  absolute_floor?: number;
  adapter_seconds_per_row?: number;
  base_seconds_per_row?: number;
  samples?: AdapterEvalSample[];
}

export interface Adapter {
  id: string;
  project_id: string;
  name: string;
  base_model: string;
  format: 'gguf' | 'peft';
  sha256: string;
  size_bytes: number;
  eval_dataset_id: string | null;
  status: 'uploaded' | 'processing' | 'passed' | 'failed';
  failure_reason: string | null;
  eval_metrics: AdapterEvalMetrics | null;
  created_at: string;
}

export interface Endpoint {
  id: string;
  slug: string;
  status: string;
  base_model: string;
  modality: string;
  project_type: ProjectType;
  created_at: string;
  retrieval: RetrievalSummary | null;
  adapter: Adapter | null;
}

export interface AdapterEvent {
  id: string;
  endpoint_id: string;
  adapter_id: string | null;
  adapter_name: string | null;
  action: 'promote' | 'rollback';
  actor_user_id: string | null;
  actor_email: string | null;
  eval_metrics: AdapterEvalMetrics | null;
  created_at: string;
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
  score?: number;
  file_id?: string | null;
  page?: number | null;
  ocr?: boolean;
  confidence?: number | null;
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
