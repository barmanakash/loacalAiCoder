import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot,
  CheckCircle2,
  ChevronRight,
  Circle,
  FileCode2,
  FolderOpen,
  GitBranch,
  Loader2,
  MessageSquare,
  Play,
  RefreshCw,
  Send,
  Settings,
  Terminal,
  X,
  XCircle,
} from "lucide-react";
import { api } from "./api/client";
import { useStore } from "./store";
import type { AgentState, Task } from "./types";

// ── Utilities ─────────────────────────────────────────────────────────────────

const stateColor: Record<AgentState, string> = {
  IDLE: "text-gray-400",
  UNDERSTANDING: "text-blue-400",
  PLANNING: "text-purple-400",
  EXECUTING: "text-yellow-400",
  VALIDATING: "text-cyan-400",
  COMPLETED: "text-green-400",
  FAILED: "text-red-400",
};

const stateIcon: Record<AgentState, React.ReactNode> = {
  IDLE:          <Circle size={12} />,
  UNDERSTANDING: <Loader2 size={12} className="animate-spin" />,
  PLANNING:      <Loader2 size={12} className="animate-spin" />,
  EXECUTING:     <Loader2 size={12} className="animate-spin" />,
  VALIDATING:    <Loader2 size={12} className="animate-spin" />,
  COMPLETED:     <CheckCircle2 size={12} />,
  FAILED:        <XCircle size={12} />,
};

// ── Components ────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: AgentState }) {
  return (
    <span className={`flex items-center gap-1 text-xs font-mono ${stateColor[status]}`}>
      {stateIcon[status]} {status}
    </span>
  );
}

function TaskSteps({ task }: { task: Task }) {
  return (
    <div className="mt-3 space-y-1">
      {task.steps.map((s, i) => (
        <div
          key={i}
          className={`flex items-start gap-2 text-xs px-3 py-1 rounded ${
            s.success ? "bg-green-950/40 text-green-300" : "bg-red-950/40 text-red-300"
          }`}
        >
          {s.success ? (
            <CheckCircle2 size={10} className="mt-0.5 shrink-0" />
          ) : (
            <XCircle size={10} className="mt-0.5 shrink-0" />
          )}
          <div>
            <span className="font-medium">{s.step}</span>
            {s.output && (
              <pre className="text-gray-400 mt-0.5 whitespace-pre-wrap">{s.output}</pre>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function MessageBubble({ role, content }: { role: string; content: string }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center mr-2 shrink-0 mt-0.5">
          <Bot size={14} />
        </div>
      )}
      <div
        className={`max-w-3xl px-4 py-3 rounded-xl text-sm leading-relaxed ${
          isUser
            ? "bg-indigo-600 text-white"
            : "bg-gray-800 text-gray-100"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children }) {
                const lang = /language-(\w+)/.exec(className || "")?.[1];
                return (
                  <pre className="bg-gray-900 rounded p-3 my-2 overflow-x-auto text-xs">
                    <code>{children}</code>
                  </pre>
                );
              },
            }}
          >
            {content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}

function ChatPanel() {
  const { messages, isStreaming, addMessage, setStreaming, projectPath, setCurrentTask, addTask } =
    useStore();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt || isStreaming) return;
    setInput("");

    addMessage({ role: "user", content: prompt });
    setStreaming(true);

    try {
      const task = await api.runTask({ prompt, project_path: projectPath });
      setCurrentTask(task);
      addTask(task);

      const reply = task.result || task.error || "Task completed.";
      addMessage({ role: "assistant", content: reply });
    } catch (e: any) {
      addMessage({
        role: "assistant",
        content: `**Error:** ${e?.message || "Request failed"}`,
      });
    } finally {
      setStreaming(false);
    }
  }, [input, isStreaming, projectPath]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 gap-4">
            <Bot size={48} className="text-indigo-500" />
            <div className="text-center">
              <h2 className="text-xl font-semibold text-gray-300 mb-2">LocalCoder AI Agent</h2>
              <p className="text-sm text-gray-500">Local-first autonomous coding assistant</p>
              <div className="mt-6 grid grid-cols-2 gap-2 text-xs">
                {[
                  "Fix all failing tests",
                  "Refactor this module to use async/await",
                  "Add type hints to all functions",
                  "Create a REST API for user management",
                ].map((ex) => (
                  <button
                    key={ex}
                    onClick={() => setInput(ex)}
                    className="text-left px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 hover:border-indigo-500 transition-colors"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} role={m.role} content={m.content} />
        ))}
        {isStreaming && (
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-4">
            <Loader2 size={14} className="animate-spin text-indigo-400" />
            <span>Agent working...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-800 px-4 py-3">
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Describe what you want the agent to do..."
            className="flex-1 bg-gray-800 text-gray-100 rounded-xl px-4 py-3 text-sm resize-none min-h-[44px] max-h-32 border border-gray-700 focus:border-indigo-500 focus:outline-none placeholder-gray-500"
            rows={1}
            disabled={isStreaming}
          />
          <button
            onClick={send}
            disabled={isStreaming || !input.trim()}
            className="w-10 h-10 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors shrink-0"
          >
            {isStreaming ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
          </button>
        </div>
        <p className="text-xs text-gray-600 mt-1 ml-1">Shift+Enter for newline · Enter to send</p>
      </div>
    </div>
  );
}

function TasksPanel() {
  const { taskHistory, setCurrentTask, currentTask } = useStore();
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    api.listTasks(30).then(setTasks).catch(() => {});
  }, []);

  const allTasks = [...taskHistory, ...tasks].filter(
    (t, i, arr) => arr.findIndex((x) => x.task_id === t.task_id) === i
  );

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-300">Task History</h2>
        <button
          onClick={() => api.listTasks(30).then(setTasks).catch(() => {})}
          className="text-gray-500 hover:text-gray-300"
        >
          <RefreshCw size={14} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto divide-y divide-gray-800">
        {allTasks.length === 0 && (
          <p className="text-gray-600 text-xs text-center py-8">No tasks yet</p>
        )}
        {allTasks.map((t) => (
          <button
            key={t.task_id}
            onClick={() => setCurrentTask(t)}
            className={`w-full text-left px-4 py-3 hover:bg-gray-800 transition-colors ${
              currentTask?.task_id === t.task_id ? "bg-gray-800" : ""
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <StatusDot status={t.status} />
              <span className="text-xs text-gray-600 font-mono">{t.task_id.slice(0, 8)}</span>
            </div>
            <p className="text-xs text-gray-300 line-clamp-2">{t.result || "pending..."}</p>
            <p className="text-xs text-gray-600 mt-1">{t.files_changed} file(s) changed</p>
          </button>
        ))}
      </div>

      {/* Current task detail */}
      {currentTask && (
        <div className="border-t border-gray-800 p-4 max-h-64 overflow-y-auto">
          <div className="flex items-center justify-between mb-2">
            <StatusDot status={currentTask.status} />
            <button
              onClick={() => setCurrentTask(null)}
              className="text-gray-600 hover:text-gray-400"
            >
              <X size={14} />
            </button>
          </div>
          {currentTask.result && (
            <p className="text-xs text-gray-300 mb-2">{currentTask.result}</p>
          )}
          {currentTask.error && (
            <p className="text-xs text-red-400 mb-2">{currentTask.error}</p>
          )}
          <TaskSteps task={currentTask} />
        </div>
      )}
    </div>
  );
}

function RepoPanel() {
  const { projectPath, setProjectPath, repoInfo, setRepoInfo } = useStore();
  const [scanning, setScanning] = useState(false);

  const scan = async () => {
    setScanning(true);
    try {
      const info = await api.scanRepo(projectPath);
      setRepoInfo(info);
    } catch (e) {
      console.error(e);
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-gray-300 mb-2">Project</h2>
        <div className="flex gap-2">
          <input
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            className="flex-1 bg-gray-800 text-gray-300 text-xs px-3 py-1.5 rounded border border-gray-700 focus:border-indigo-500 focus:outline-none"
            placeholder="/path/to/project"
          />
          <button
            onClick={scan}
            disabled={scanning}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 rounded text-xs transition-colors"
          >
            {scanning ? <Loader2 size={12} className="animate-spin" /> : "Scan"}
          </button>
        </div>
      </div>

      {repoInfo && (
        <div className="px-4 py-3 space-y-3 overflow-y-auto flex-1">
          <div>
            <p className="text-xs text-gray-500 mb-1">Languages</p>
            <div className="flex flex-wrap gap-1">
              {Object.entries(repoInfo.languages).map(([lang, count]) => (
                <span key={lang} className="text-xs px-2 py-0.5 bg-indigo-900/50 text-indigo-300 rounded-full">
                  {lang} ({count})
                </span>
              ))}
            </div>
          </div>
          {repoInfo.frameworks.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Frameworks</p>
              <div className="flex flex-wrap gap-1">
                {repoInfo.frameworks.map((f) => (
                  <span key={f} className="text-xs px-2 py-0.5 bg-purple-900/50 text-purple-300 rounded-full">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="text-xs text-gray-500 space-y-1">
            <p>Total files: <span className="text-gray-300">{repoInfo.total_files}</span></p>
            <p>Total lines: <span className="text-gray-300">{repoInfo.total_lines.toLocaleString()}</span></p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Layout ───────────────────────────────────────────────────────────────

export default function App() {
  const { activeTab, setActiveTab, sidebarOpen, toggleSidebar } = useStore();
  const [health, setHealth] = useState<{ ok: boolean; model: string }>({
    ok: false,
    model: "...",
  });

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth({ ok: h.llm_available, model: h.llm_model }))
      .catch(() => setHealth({ ok: false, model: "offline" }));
  }, []);

  const tabs = [
    { id: "chat" as const,  icon: <MessageSquare size={16} />, label: "Chat" },
    { id: "tasks" as const, icon: <Play size={16} />, label: "Tasks" },
    { id: "files" as const, icon: <FileCode2 size={16} />, label: "Repo" },
  ];

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 font-sans overflow-hidden">
      {/* Sidebar */}
      <div
        className={`flex flex-col border-r border-gray-800 transition-all duration-200 ${
          sidebarOpen ? "w-72" : "w-0 overflow-hidden"
        }`}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Bot size={14} />
          </div>
          <span className="font-bold text-sm">LocalCoder</span>
          <span className="ml-auto text-xs font-mono text-gray-600">v1.0</span>
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-1 p-2">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                activeTab === t.id
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </nav>

        {/* Sidebar content */}
        <div className="flex-1 overflow-hidden">
          {activeTab === "tasks" && <TasksPanel />}
          {activeTab === "files" && <RepoPanel />}
        </div>

        {/* Status */}
        <div className="border-t border-gray-800 px-4 py-3 flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${health.ok ? "bg-green-400" : "bg-red-400"}`} />
          <span className="text-xs text-gray-500 truncate">{health.model}</span>
        </div>
      </div>

      {/* Main */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Topbar */}
        <header className="flex items-center gap-3 px-4 py-2 border-b border-gray-800 shrink-0">
          <button
            onClick={toggleSidebar}
            className="text-gray-500 hover:text-gray-300 p-1"
          >
            <ChevronRight
              size={16}
              className={`transition-transform ${sidebarOpen ? "rotate-180" : ""}`}
            />
          </button>
          <div className="flex gap-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs transition-colors ${
                  activeTab === t.id
                    ? "bg-gray-800 text-gray-100"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <span className={`text-xs ${health.ok ? "text-green-400" : "text-red-400"}`}>
              {health.ok ? "● LLM ready" : "● LLM offline"}
            </span>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-hidden">
          {activeTab === "chat" && <ChatPanel />}
          {activeTab === "tasks" && (
            <div className="h-full flex items-center justify-center text-gray-600 text-sm">
              Select a task from the sidebar
            </div>
          )}
          {activeTab === "files" && (
            <div className="h-full flex items-center justify-center text-gray-600 text-sm">
              Use the sidebar to scan your project
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
