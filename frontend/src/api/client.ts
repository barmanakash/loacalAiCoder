import axios from "axios";
import type { HealthStatus, RepoInfo, Task, TaskRequest } from "../types";

const BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8765";

const http = axios.create({ baseURL: BASE, timeout: 600_000 });

export const api = {
  health: (): Promise<HealthStatus> =>
    http.get("/api/health").then((r) => r.data),

  runTask: (req: TaskRequest): Promise<Task> =>
    http.post("/api/agent/task", req).then((r) => r.data),

  getTask: (id: string): Promise<Task> =>
    http.get(`/api/agent/task/${id}`).then((r) => r.data),

  cancelTask: (id: string): Promise<void> =>
    http.delete(`/api/agent/task/${id}`).then(() => undefined),

  listTasks: (limit = 20): Promise<Task[]> =>
    http.get("/api/agent/tasks", { params: { limit } }).then((r) => r.data),

  scanRepo: (path: string): Promise<RepoInfo> =>
    http.post("/api/repo/scan", { path }).then((r) => r.data),

  indexRepo: (path: string): Promise<{ indexed_chunks: number }> =>
    http.post("/api/repo/index", { path }).then((r) => r.data),

  chat: (messages: { role: string; content: string }[]): Promise<string> =>
    http.post("/api/chat", { messages }).then((r) => r.data.content),

  streamUrl: () => `${BASE}/api/chat/stream`,
};
