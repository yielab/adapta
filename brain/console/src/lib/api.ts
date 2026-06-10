import { getToken, clearSession } from "./session";
import { navigate } from "./router";
import type {
  User,
  Project,
  ProjectType,
  ProjectFile,
  Dataset,
  TrainingJob,
  Endpoint,
  ApiKey,
  ApiKeyCreated,
  UsageResponse,
  ChatCompletion,
} from "./types";

// Same-origin: the console is served by the app under /console/, so /v1/* is a
// relative path → no CORS, no base URL config.
const V1 = "/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  correlationId?: string;
  constructor(status: number, code: string, message: string, correlationId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
  }
}

interface ReqOpts {
  method?: string;
  body?: unknown;
  auth?: boolean;
  raw?: boolean; // body is FormData, don't JSON-encode
}

async function request<T>(path: string, opts: ReqOpts = {}): Promise<T> {
  const { method = "GET", body, auth = true, raw = false } = opts;
  const headers: Record<string, string> = {};
  if (auth) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    if (raw) {
      payload = body as BodyInit;
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }

  const res = await fetch(path, { method, headers, body: payload });

  // 401 → session is dead; drop it and bounce to login (unless we're logging in).
  if (res.status === 401 && auth) {
    clearSession();
    navigate("/login");
    throw new ApiError(401, "unauthorized", "Your session expired. Please sign in again.");
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const err = data?.error ?? {};
    throw new ApiError(
      res.status,
      err.code ?? "error",
      err.message ?? `Request failed (${res.status})`,
      err.correlation_id,
    );
  }
  return data as T;
}

function upload<T>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  return request<T>(path, { method: "POST", body: fd, raw: true });
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export const api = {
  register: (org_name: string, email: string, password: string) =>
    request<User>(`${V1}/auth/register`, { method: "POST", auth: false, body: { org_name, email, password } }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>(`${V1}/auth/login`, { method: "POST", auth: false, body: { email, password } }),
  me: () => request<User>(`${V1}/auth/me`),

  // Projects
  listProjects: (teamId: string) => request<Project[]>(`${V1}/projects?team_id=${encodeURIComponent(teamId)}`),
  createProject: (p: { name: string; type: ProjectType; base_model: string; description?: string; team_id: string }) =>
    request<Project>(`${V1}/projects`, { method: "POST", body: p }),
  getProject: (id: string) => request<Project>(`${V1}/projects/${id}`),
  deleteProject: (id: string) => request<void>(`${V1}/projects/${id}`, { method: "DELETE" }),

  // Files (RAG)
  listFiles: (pid: string) => request<ProjectFile[]>(`${V1}/projects/${pid}/files`),
  uploadFile: (pid: string, file: File) => upload<{ id: string; filename: string; status: string }>(`${V1}/projects/${pid}/files`, file),
  deleteFile: (pid: string, fid: string) => request<void>(`${V1}/projects/${pid}/files/${fid}`, { method: "DELETE" }),

  // Datasets (fine-tune)
  listDatasets: (pid: string) => request<Dataset[]>(`${V1}/projects/${pid}/datasets`),
  uploadDataset: (pid: string, file: File) => upload<{ id: string; name: string; status: string }>(`${V1}/projects/${pid}/datasets`, file),
  getDataset: (pid: string, did: string) => request<Dataset>(`${V1}/projects/${pid}/datasets/${did}`),
  synthesize: (pid: string, opts: { n_pairs_per_chunk?: number; max_chunks?: number; system_prompt?: string }) =>
    request<{ dataset_id: string; status: string; message: string }>(`${V1}/projects/${pid}/datasets/synthesize`, { method: "POST", body: opts }),

  // Jobs
  listJobs: (pid: string) => request<TrainingJob[]>(`${V1}/projects/${pid}/jobs`),
  createJob: (pid: string, dataset_id: string, training_config?: Record<string, unknown>) =>
    request<TrainingJob>(`${V1}/projects/${pid}/jobs`, { method: "POST", body: { dataset_id, training_config } }),
  getJob: (pid: string, jid: string) => request<TrainingJob>(`${V1}/projects/${pid}/jobs/${jid}`),

  // Endpoint
  getEndpoint: (pid: string) => request<Endpoint>(`${V1}/projects/${pid}/endpoint`),
  createEndpoint: (pid: string) => request<Endpoint>(`${V1}/projects/${pid}/endpoint`, { method: "POST" }),

  // Keys
  listKeys: (pid: string) => request<ApiKey[]>(`${V1}/projects/${pid}/keys`),
  createKey: (pid: string, name: string) => request<ApiKeyCreated>(`${V1}/projects/${pid}/keys`, { method: "POST", body: { name } }),
  revokeKey: (pid: string, kid: string) => request<void>(`${V1}/projects/${pid}/keys/${kid}`, { method: "DELETE" }),

  // Usage
  getUsage: (pid: string) => request<UsageResponse>(`${V1}/projects/${pid}/usage`),

  // Chat (uses a scoped brn_ key, NOT the JWT — auth:false + manual header)
  chat: (slug: string, brnKey: string, messages: { role: string; content: string }[]) =>
    fetch(`${V1}/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${brnKey}` },
      body: JSON.stringify({ model: slug, messages, stream: false }),
    }).then(async (res) => {
      const data = await res.json();
      if (!res.ok) {
        const e = data?.error ?? {};
        throw new ApiError(res.status, e.code ?? "error", e.message ?? "Chat failed", e.correlation_id);
      }
      return data as ChatCompletion;
    }),
};
