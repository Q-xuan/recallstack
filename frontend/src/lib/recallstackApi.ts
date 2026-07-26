const BASE = "/api/recallstack";

type ErrorBody = {
  detail?: {
    message?: string;
    code?: string;
    details?: Record<string, unknown>;
  };
  message?: string;
};

class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function errorMessage(detail: unknown, fallback: string): string {
  if (!detail || typeof detail !== "object") return fallback;
  const body = detail as ErrorBody;
  if (body.detail && typeof body.detail.message === "string") return body.detail.message;
  if (typeof body.message === "string") return body.message;
  if (typeof body.detail === "string") return body.detail;
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      detail = { message: res.statusText };
    }
    throw new ApiError(errorMessage(detail, `Request failed (${res.status})`), res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface Repository {
  id: string;
  name: string;
  source_type: string;
  source_location: string;
  default_branch: string;
  created_at: string;
  updated_at: string;
}

export interface Version {
  id: string;
  repository_id: string;
  commit_sha: string;
  content_hash: string;
  status: string;
  error_message?: string | null;
  has_wiki?: boolean;
  created_at: string;
  completed_at?: string | null;
}

export interface SourceRef {
  path: string;
  start_line?: number;
  end_line?: number;
  symbol?: string;
  commit_sha?: string;
}

export interface Concept {
  id: string;
  repository_id: string;
  repository_version_id: string;
  slug: string;
  title: string;
  description: string;
  difficulty: number;
  importance: number;
  source_references: SourceRef[];
  content_hash: string;
  stale: boolean;
  why_learn?: string;
  estimated_minutes?: number;
  wiki_page_id?: string | null;
  mastery_score?: number | null;
  next_review_at?: string | null;
}

export interface ConceptEdge {
  id: string;
  source_concept_id: string;
  target_concept_id: string;
  relation_type: string;
}

export interface WikiPage {
  id: string;
  title: string;
  content: string;
  parent_id?: string;
  order?: number;
  concept_id?: string | null;
  concept_slug?: string | null;
}

export interface WikiSidebarItem {
  title: string;
  page_id: string;
  children: WikiSidebarItem[];
}

export interface Wiki {
  repository_id: string;
  repository_version_id: string;
  project_name: string;
  pages: WikiPage[];
  sidebar: WikiSidebarItem[];
}

export interface LearningPathNode {
  id: string;
  concept_id: string;
  position: number;
  reason: string;
  concept?: Concept | null;
}

export interface LearningPath {
  id: string;
  repository_version_id: string;
  title: string;
  description: string;
  estimated_minutes: number;
  nodes: LearningPathNode[];
}

export interface EvidenceSnippet extends SourceRef {
  snippet?: string;
  available?: boolean;
}

export interface LearningItem {
  id: string;
  concept_id: string;
  item_type: string;
  prompt: string;
  difficulty: number;
  source_references: SourceRef[];
  stale: boolean;
  evidence_snippets?: EvidenceSnippet[];
}

export interface HintResponse {
  level: number;
  content: string;
  revealed_answer: boolean;
}

export interface SessionQueueItem {
  id: string;
  item_type: string;
  prompt: string;
  difficulty: number;
  stale: boolean;
  attempted: boolean;
}

export interface SessionQueue {
  mode: "concept" | "review";
  concept_id: string;
  concept_title: string;
  repository_id: string;
  item_ids: string[];
  position: number;
  total: number;
  current_item_id: string;
  next_item_id?: string | null;
  prev_item_id?: string | null;
  remaining_count: number;
  completed_count: number;
  items: SessionQueueItem[];
  current_item?: LearningItem | null;
}

export interface AttemptResult {
  id: string;
  learning_item_id: string;
  answer: string;
  score: number;
  confidence: number;
  hints_used: Array<Record<string, unknown>>;
  duration_seconds: number;
  evaluation: {
    score: number;
    covered_points: string[];
    missing_points: string[];
    misconceptions: string[];
    source_evidence: SourceRef[];
    feedback: string;
    suggested_revision: string;
    follow_up_question: string;
    evaluation_source?: string;
  };
  fsrs_rating: number | null;
  revealed_answer: boolean;
  created_at: string;
  mastery_score?: number | null;
  next_review_at?: string | null;
  expected_answer_outline?: string | null;
  evaluation_source?: string | null;
  concept_id?: string | null;
  next_item_id?: string | null;
  session?: SessionQueue | null;
}

export interface DueReview {
  concept_id: string;
  title: string;
  mastery_score: number;
  next_review_at?: string | null;
  stale: boolean;
  item_id?: string | null;
}

export interface Dashboard {
  due_review_count: number;
  learning_concept_count: number;
  interval_review_count: number;
  code_trace_count: number;
  current_repository?: Repository | null;
  recent_concepts: Concept[];
  weak_concepts: Concept[];
  due_reviews: DueReview[];
  progress_percent: number;
}

export interface FsRoot {
  name: string;
  path: string;
}

export interface FsEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface FsListResult {
  path: string;
  parent: string | null;
  directories: FsEntry[];
  files: FsEntry[];
  is_windows: boolean;
}


export const recallstackApi = {
  health: () => request<{ status: string }>("/health"),
  listRepositories: () => request<Repository[]>("/repositories"),
  createRepository: (body: {
    name?: string;
    source_type: "local" | "github";
    source_location: string;
    default_branch?: string;
  }) =>
    request<Repository>("/repositories", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getRepository: (id: string) => request<Repository>(`/repositories/${id}`),
  analyze: (id: string, wait = true) =>
    request<Version>(`/repositories/${id}/analyze?wait=${wait ? "true" : "false"}`, {
      method: "POST",
    }),
  latestVersion: (id: string) => request<Version>(`/repositories/${id}/versions/latest`),
  wiki: (id: string) => request<Wiki>(`/repositories/${id}/wiki`),
  wikiPage: (id: string, pageId: string) =>
    request<WikiPage>(`/repositories/${id}/wiki/pages/${encodeURIComponent(pageId)}`),
  concepts: (id: string) =>
    request<{ concepts: Concept[]; edges: ConceptEdge[] }>(`/repositories/${id}/concepts`),
  learningPath: (id: string) => request<LearningPath>(`/repositories/${id}/learning-path`),
  getConcept: (id: string) => request<Concept>(`/concepts/${id}`),
  listItems: (conceptId: string) => request<LearningItem[]>(`/concepts/${conceptId}/items`),
  getItem: (itemId: string) => request<LearningItem>(`/items/${itemId}`),
  conceptSession: (conceptId: string) =>
    request<SessionQueue>(`/sessions/concept/${conceptId}`),
  reviewSession: (conceptId?: string) => {
    const q = new URLSearchParams();
    if (conceptId) q.set("concept_id", conceptId);
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return request<SessionQueue>(`/sessions/review${suffix}`);
  },
  itemSession: (itemId: string, mode: "concept" | "review" = "concept") =>
    request<SessionQueue>(`/sessions/item/${itemId}?mode=${mode}`),
  hint: (
    itemId: string,
    body: { current_level: number; hints_used: Array<Record<string, unknown>> }
  ) =>
    request<HintResponse>(`/items/${itemId}/hint`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reveal: (
    itemId: string,
    body: { current_level: number; hints_used: Array<Record<string, unknown>> }
  ) =>
    request<HintResponse>(`/items/${itemId}/reveal`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  submitAttempt: (
    itemId: string,
    body: {
      answer: string;
      confidence: number;
      hints_used: Array<Record<string, unknown>>;
      duration_seconds: number;
      revealed_answer: boolean;
    },
    mode: "concept" | "review" = "concept"
  ) =>
    request<AttemptResult>(`/items/${itemId}/attempts?mode=${mode}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  dueReviews: () => request<DueReview[]>("/reviews/due"),
  dashboard: () => request<Dashboard>("/dashboard"),
  listFsRoots: () => request<{ roots: FsRoot[] }>("/fs/roots"),
  listFsDirectory: (path?: string) => {
    const q = new URLSearchParams();
    if (path) q.set("path", path);
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return request<FsListResult>(`/fs/list${suffix}`);
  },
  sourceSnippet: (params: {
    repository_id: string;
    path: string;
    start_line?: number;
    end_line?: number;
  }) => {
    const q = new URLSearchParams();
    q.set("repository_id", params.repository_id);
    q.set("path", params.path);
    if (params.start_line) q.set("start_line", String(params.start_line));
    if (params.end_line) q.set("end_line", String(params.end_line));
    return request<{ path: string; start_line: number; end_line: number; content: string }>(
      `/source?${q.toString()}`
    );
  },
};
