export type AgentState =
  | "IDLE"
  | "UNDERSTANDING"
  | "PLANNING"
  | "EXECUTING"
  | "VALIDATING"
  | "COMPLETED"
  | "FAILED";

export interface TaskStep {
  step: string;
  success: boolean;
  output: string;
  error?: string;
}

export interface Task {
  task_id: string;
  status: AgentState;
  result?: string;
  error?: string;
  files_changed: number;
  steps: TaskStep[];
  created_at: string;
  updated_at: string;
}

export interface TaskRequest {
  prompt: string;
  project_path?: string;
  permission_level?: number;
}

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: number;
}

export interface RepoInfo {
  root: string;
  languages: Record<string, number>;
  frameworks: string[];
  total_files: number;
  total_lines: number;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  version: string;
  llm_provider: string;
  llm_model: string;
  llm_available: boolean;
}
