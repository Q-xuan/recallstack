const BASE = "/api";

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const apiKey = localStorage.getItem("repowiki_api_key");
  if (apiKey) headers["x-api-key"] = apiKey;
  return headers;
}

export interface ScanRequest {
  path?: string;
  url?: string;
  language?: string;
  model?: string;
}

export interface ProjectInfo {
  id: string;
  name: string;
  status: string;
  total_files: number;
  total_lines: number;
  error?: string;
}

export interface WikiStructure {
  project_name: string;
  sidebar: SidebarItem[];
  pages: PageMeta[];
}

export interface SidebarItem {
  title: string;
  page_id: string;
  children?: SidebarItem[];
}

export interface PageMeta {
  id: string;
  title: string;
  order: number;
  parent_id: string;
}

export interface WikiPage {
  id: string;
  title: string;
  content: string;
}

export async function scanProject(req: ScanRequest): Promise<ProjectInfo> {
  const res = await fetch(`${BASE}/scan`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(req),
  });
  return res.json();
}

export function streamScanProgress(
  projectId: string,
  onProgress: (step: string) => void,
  onDone: (status: string) => void,
) {
  const es = new EventSource(`${BASE}/project/${projectId}/status`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.step) onProgress(data.step);
    if (data.status) {
      onDone(data.status);
      es.close();
    }
    if (data.error) {
      onDone("error");
      es.close();
    }
  };
  es.onerror = () => {
    es.close();
    onDone("error");
  };
  return es;
}

export async function getWiki(projectId: string): Promise<WikiStructure> {
  const res = await fetch(`${BASE}/project/${projectId}/wiki`, { headers: getHeaders() });
  return res.json();
}

export async function getPage(projectId: string, pageId: string): Promise<WikiPage> {
  const res = await fetch(`${BASE}/project/${projectId}/wiki/${pageId}`, { headers: getHeaders() });
  return res.json();
}

export async function getFileContent(projectId: string, filePath: string) {
  const res = await fetch(`${BASE}/project/${projectId}/file/${filePath}`, { headers: getHeaders() });
  return res.json();
}

export interface ChatOptions {
  question?: string;
  mode?: "chat" | "inline_explain";
  selection?: string;
  wiki_page_id?: string;
  wiki_page_title?: string;
  surrounding_text?: string;
}

export interface CodeReference {
  path: string;
  line_start: number;
  line_end: number;
  snippet?: string;
}

export function streamChat(
  projectId: string,
  questionOrOptions: string | ChatOptions,
  onChunk: (data: any) => void,
  onDone: () => void,
  onError?: (message: string) => void,
) {
  const body: ChatOptions =
    typeof questionOrOptions === "string"
      ? { question: questionOrOptions, mode: "chat" }
      : { mode: "chat", ...questionOrOptions };

  fetch(`${BASE}/project/${projectId}/chat`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
  })
    .then(async (res) => {
      const contentType = res.headers.get("content-type") || "";
      // error payloads return JSON object instead of SSE
      if (!res.ok || contentType.includes("application/json")) {
        let message = "Request failed";
        try {
          const data = await res.json();
          message = data.error || data.detail || message;
        } catch {
          message = res.statusText || message;
        }
        onError?.(message);
        onDone();
        return;
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) {
        onError?.("No response body");
        onDone();
        return;
      }

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);
              if (data.done) onDone();
            } catch {
              /* ignore partial JSON */
            }
          }
        }
      }
      onDone();
    })
    .catch((err) => {
      onError?.(err?.message || "Network error");
      onDone();
    });
}
