/**
 * API seeding helpers — populate demo data for screenshot and GIF capture.
 *
 * Runs on the host against the live stack (localhost:8000).
 * Uses native fetch; call from beforeAll in spec files.
 */

const BASE = "http://localhost:8000/v1";

const DEMO_DOC_CONTENT = `# Support Knowledge Base

## Refund Policy
Customers may request a full refund within 30 days of purchase. To initiate a
refund, email support@example.com with the order number. Refunds are processed
within 5 business days to the original payment method.

## Account Management
### Changing your password
1. Go to Settings → Account.
2. Click "Change password."
3. Enter your current password and a new password (8+ characters).
4. Click Save.

### Cancelling your subscription
Subscriptions can be cancelled any time from the Billing page. You retain
access until the end of the current billing period. No partial refunds are
issued for mid-cycle cancellations.

## Technical Support
Our support team is available Monday–Friday, 9 AM–6 PM EST.
Response time: ≤4 hours for Pro subscribers, ≤24 hours for free accounts.

## Frequently Asked Questions
**Q: Can I export my data?**
A: Yes. Go to Settings → Data export and choose CSV or JSON. Exports are
   available for 48 hours after generation.

**Q: Do you support SSO?**
A: SAML 2.0 and OAuth2 SSO is available on Enterprise plans.
`;

const DEMO_DATASET_JSONL = [
  {
    messages: [
      { role: "user", content: "My order arrived damaged. What should I do?" },
      {
        role: "assistant",
        content:
          "I'm sorry to hear your order arrived damaged. Please email support@example.com with your order number and a photo of the damage. We'll arrange a replacement or full refund within 2 business days.",
      },
    ],
  },
  {
    messages: [
      { role: "user", content: "How do I upgrade my plan?" },
      {
        role: "assistant",
        content:
          "To upgrade your plan, go to Settings → Billing and click 'Upgrade'. Choose the plan that fits your needs and confirm payment. The upgrade takes effect immediately.",
      },
    ],
  },
  {
    messages: [
      { role: "user", content: "Can I add a team member to my account?" },
      {
        role: "assistant",
        content:
          "Yes! Go to Settings → Team and click 'Invite member'. Enter their email address and select a role. They'll receive an invitation link valid for 48 hours.",
      },
    ],
  },
  {
    messages: [
      { role: "user", content: "What's the response time for support tickets?" },
      {
        role: "assistant",
        content:
          "Pro subscribers receive a response within 4 hours during business hours (Mon–Fri, 9 AM–6 PM EST). Free accounts have a 24-hour SLA. For urgent issues, Pro subscribers can use our live chat.",
      },
    ],
  },
  {
    messages: [
      { role: "user", content: "I forgot my password. How do I reset it?" },
      {
        role: "assistant",
        content:
          "On the login page, click 'Forgot password?' and enter your email. You'll receive a reset link within a few minutes. The link expires after 1 hour. If you don't see the email, check your spam folder.",
      },
    ],
  },
].map((row) => JSON.stringify(row)).join("\n");

export interface SeedResult {
  token: string;
  ragProjectId: string;
  finetuneProjectId: string;
  emptyProjectId: string;
}

async function post(path: string, body: unknown, token?: string) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`POST ${path} → ${res.status}: ${txt}`);
  }
  return res.json();
}

async function get(path: string, token: string) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`GET ${path} → ${res.status}: ${txt}`);
  }
  return res.json();
}

async function uploadFile(
  projectId: string,
  token: string,
  filename: string,
  content: string,
  contentType = "text/markdown",
) {
  const blob = new Blob([content], { type: contentType });
  const form = new FormData();
  form.append("file", blob, filename);
  const res = await fetch(`${BASE}/projects/${projectId}/files`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`File upload → ${res.status}: ${txt}`);
  }
  return res.json();
}

async function uploadDataset(
  projectId: string,
  token: string,
  filename: string,
  content: string,
) {
  const blob = new Blob([content], { type: "application/jsonlines" });
  const form = new FormData();
  form.append("file", blob, filename);
  const res = await fetch(`${BASE}/projects/${projectId}/datasets`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Dataset upload → ${res.status}: ${txt}`);
  }
  return res.json();
}

async function pollFileIndexed(
  projectId: string,
  fileId: string,
  token: string,
  maxWaitMs = 30_000,
) {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const files: { id: string; status: string }[] = await get(
      `/projects/${projectId}/files`,
      token,
    );
    const f = files.find((x) => x.id === fileId);
    if (f?.status === "indexed") return;
    if (f?.status === "failed") throw new Error(`File ${fileId} indexing failed`);
    await new Promise((r) => setTimeout(r, 1500));
  }
  console.warn(`File ${fileId} did not reach 'indexed' within ${maxWaitMs}ms — continuing`);
}

export async function seedDemoData(): Promise<SeedResult> {
  // 1. Login
  const { access_token: token } = await post("/auth/login", {
    email: "admin@example.com",
    password: "admin12345",
  });

  const me = await get("/auth/me", token);
  const teamId = me.teams[0].id;

  // 2. Wipe existing projects so each run produces a clean 3-project state.
  const existing: { id: string }[] = await get(
    `/projects?team_id=${teamId}`,
    token,
  );
  await Promise.all(
    existing.map((p) =>
      fetch(`${BASE}/projects/${p.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      }),
    ),
  );

  const createProject = (
    name: string,
    type: "rag" | "finetune",
    description: string,
  ) =>
    post(
      "/projects",
      { name, type, base_model: "qwen2.5-0.5b-instruct", description, team_id: teamId },
      token,
    );

  // 2. Create three projects
  const [ragProject, finetuneProject, emptyProject] = await Promise.all([
    createProject(
      "Support Knowledge Base",
      "rag",
      "Answers support questions from our internal policy docs with citations.",
    ),
    createProject(
      "Customer Tone Adapter",
      "finetune",
      "Fine-tunes the model to match our support team writing style.",
    ),
    createProject(
      "Invoice Extractor",
      "finetune",
      "Structured extraction from invoice images (vision fine-tune, coming soon).",
    ),
  ]);

  // 3. Upload a document to the RAG project and wait for indexing
  const fileResp = await uploadFile(
    ragProject.id,
    token,
    "support-kb.md",
    DEMO_DOC_CONTENT,
  );
  await pollFileIndexed(ragProject.id, fileResp.id, token);

  // 4. Create endpoint for the RAG project (indexing must be done first)
  await post(`/projects/${ragProject.id}/endpoint`, {}, token);

  // 5. Generate an API key
  await post(`/projects/${ragProject.id}/keys`, { name: "demo-key" }, token);

  // 6. Upload a dataset to the fine-tune project
  await uploadDataset(
    finetuneProject.id,
    token,
    "customer-tone.jsonl",
    DEMO_DATASET_JSONL,
  );

  return {
    token,
    ragProjectId: ragProject.id,
    finetuneProjectId: finetuneProject.id,
    emptyProjectId: emptyProject.id,
  };
}
