import { create } from "zustand";
import type { AgentState, Message, RepoInfo, Task } from "../types";

interface AppState {
  // Chat
  messages: Message[];
  isStreaming: boolean;
  addMessage: (msg: Message) => void;
  setStreaming: (v: boolean) => void;
  clearMessages: () => void;

  // Task
  currentTask: Task | null;
  taskHistory: Task[];
  setCurrentTask: (t: Task | null) => void;
  addTask: (t: Task) => void;

  // Project
  projectPath: string;
  setProjectPath: (p: string) => void;

  // Repo
  repoInfo: RepoInfo | null;
  setRepoInfo: (r: RepoInfo | null) => void;

  // UI
  activeTab: "chat" | "files" | "terminal" | "diff" | "tasks";
  setActiveTab: (tab: AppState["activeTab"]) => void;
  sidebarOpen: boolean;
  toggleSidebar: () => void;
}

export const useStore = create<AppState>((set) => ({
  messages: [],
  isStreaming: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setStreaming: (v) => set({ isStreaming: v }),
  clearMessages: () => set({ messages: [] }),

  currentTask: null,
  taskHistory: [],
  setCurrentTask: (t) => set({ currentTask: t }),
  addTask: (t) =>
    set((s) => ({ taskHistory: [t, ...s.taskHistory].slice(0, 50) })),

  projectPath: ".",
  setProjectPath: (p) => set({ projectPath: p }),

  repoInfo: null,
  setRepoInfo: (r) => set({ repoInfo: r }),

  activeTab: "chat",
  setActiveTab: (tab) => set({ activeTab: tab }),
  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}));
