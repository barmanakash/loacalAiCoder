local AI Agent


# LocalCoder AI Agent

> **Privacy-first autonomous AI coding assistant — runs entirely on your machine.**

```
 _                   _  _____           _
| |    ___   ___ __ _| |/ ____|___   __| | ___ _ __
| |   / _ \ / __/ _` | | |   / _ \ / _` |/ _ \ '__|
| |__| (_) | (_| (_| | | |__| (_) | (_| |  __/ |
|_____\___/ \___\__,_|_|\____\___/ \__,_|\___|_|

v1.0.0 — Local-first • Offline-capable • Zero cloud
```

---

## What is LocalCoder?

LocalCoder is a production-grade autonomous coding agent that runs **100% locally** on your machine. It understands your entire codebase, writes and edits code, executes terminal commands, manages git, runs tests, and fixes bugs — all without sending a single byte to the cloud.

**Inspired by Codex and Devin, built for privacy.**

---

## Features

### 🔍 Repository Intelligence
- Full repository scanning and file indexing
- Language and framework auto-detection (Python, TypeScript, Go, Rust, 20+ more)
- Dependency analysis (requirements.txt, package.json, Cargo.toml, etc.)
- Semantic search over your entire codebase via ChromaDB

### 🤖 Autonomous Agent Loop
```
User Request → UNDERSTANDING → PLANNING → EXECUTING → VALIDATING → COMPLETED
                                                    ↑         ↓
                                                    └─ RETRY ←┘ (on failure)
```

### 🛠 Tool Suite
| Tool | Capabilities |
|------|-------------|
| **File Agent** | Read, create, modify, delete files; unified diffs; rollback |
| **Terminal Agent** | Execute commands with timeout, output capture, sandbox |
| **Git Agent** | Status, diff, LLM-generated commit messages, branches |
| **Testing Agent** | Auto-detect pytest/jest/vitest/cargo test; run & fix failures |
| **Coding Agent** | Generate, refactor, fix bugs, add types, create tests |

### 🧠 Memory System
- **Short-term**: Current task, conversation history, active files
- **Long-term**: Developer preferences, project rules, architecture decisions (SQLite)

### 🔐 Permission System
| Level | Capability |
|-------|------------|
| 0 | Read and search only |
| 1 | Edit files (with approval) |
| 2 | Delete / install packages (with confirmation) |
| 3 | Restricted system actions |

### 📦 Rollback & Snapshots
Every file modified during a task is snapshotted before editing. Full rollback in one command.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, FastAPI, async/await |
| Agent | Custom loop with LangGraph-compatible design |
| LLM | Ollama (Qwen2.5-Coder, DeepSeek-Coder, Llama 3) |
| Database | SQLite via aiosqlite |
| Vector Search | ChromaDB (LanceDB optional) |
| Frontend | React 18, TypeScript, Tailwind CSS |
| Desktop | Tauri (optional) |
| CLI | Click + Rich |

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend)
- [Ollama](https://ollama.com) installed and running

### 1. Install
```bash
git clone https://github.com/yourname/localcoder
cd localcoder
bash setup.sh
```

### 2. Start the backend
```bash
source .venv/bin/activate
python -m backend
# API available at http://127.0.0.1:8765
```

### 3. Start the frontend
```bash
cd frontend
npm run dev
# UI available at http://localhost:5173
```

### 4. Use the CLI
```bash
# Initialize LocalCoder in your project
localcoder init /path/to/your/project

# Run a task
localcoder run "Fix all failing tests" --path /path/to/project

# Interactive chat
localcoder chat --path /path/to/project

# Review recent activity
localcoder review

# Rollback a task
localcoder rollback <task-id>

# Index repository for semantic search
localcoder index --path /path/to/project
```

---

## API Reference

### Submit a Task
```http
POST /api/agent/task
Content-Type: application/json

{
  "prompt": "Fix failing tests and add type hints",
  "project_path": "/absolute/path/to/project",
  "permission_level": 1,
  "context": {}
}
```

**Response:**
```json
{
  "task_id": "abc123",
  "status": "COMPLETED",
  "files_changed": 3,
  "result": "Fixed 2 failing tests and added type hints to 5 functions",
  "steps": [
    {"step": "Analyzed repository", "success": true, "output": "..."},
    {"step": "Modified src/api.py", "success": true, "output": "..."}
  ]
}
```

### Other Endpoints
```
GET  /api/health              — Health check + LLM status
GET  /api/agent/tasks         — List task history
GET  /api/agent/task/{id}     — Get task details
DELETE /api/agent/task/{id}   — Cancel running task
POST /api/repo/scan           — Scan repository
POST /api/repo/index          — Index for semantic search
POST /api/repo/search         — Semantic code search
POST /api/chat                — Direct LLM chat
POST /api/chat/stream         — Streaming chat (SSE)
GET  /api/memory/{key}        — Get memory value
POST /api/memory/set          — Set memory value
GET  /api/llm/info            — LLM configuration
```

---

## LLM Configuration

Edit `.env` to switch models:

```bash
# Qwen2.5-Coder (default, best for code)
OLLAMA_MODEL=qwen2.5-coder:7b

# DeepSeek-Coder (excellent alternative)
OLLAMA_MODEL=deepseek-coder:6.7b

# Llama 3.1 (general purpose)
OLLAMA_MODEL=llama3.1:8b-instruct-q4_0

# Use llama.cpp server instead
LLM_PROVIDER=llama_cpp
OLLAMA_BASE_URL=http://localhost:8080
```

---

## Project Structure

```
localcoder/
├── backend/
│   ├── api/
│   │   └── app.py              # FastAPI application + all routes
│   ├── agent/
│   │   ├── agent_loop.py       # Core autonomous agent loop
│   │   ├── task_manager.py     # Task creation, tracking, cancellation
│   │   └── llm_provider.py     # LLM abstraction (Ollama, llama.cpp)
│   ├── tools/
│   │   ├── file_agent.py       # File read/create/modify/delete/diff
│   │   ├── terminal_agent.py   # Safe command execution
│   │   ├── git_agent.py        # Git operations + AI commit messages
│   │   ├── testing_agent.py    # Test detection, execution, fix-retry
│   │   └── repo_intelligence.py # Language/framework/dep detection
│   ├── memory/
│   │   ├── memory_manager.py   # Short + long term memory
│   │   ├── context_engine.py   # ChromaDB indexing + semantic search
│   │   └── snapshot_manager.py # File snapshots + rollback
│   ├── models/
│   │   └── types.py            # Pydantic models and enums
│   └── core/
│       ├── config.py           # Settings (pydantic-settings)
│       ├── database.py         # Async SQLite layer
│       ├── llm.py              # LLM client (Ollama/llama.cpp)
│       ├── logging.py          # Structured logging (structlog)
│       └── permissions.py      # Permission + approval system
├── frontend/
│   └── src/
│       ├── App.tsx             # Main UI (Chat, Tasks, Repo panels)
│       ├── api/client.ts       # API client (axios)
│       ├── store/index.ts      # Zustand state management
│       └── types/index.ts      # TypeScript types
├── cli/
│   └── main.py                 # CLI (localcoder chat/run/review/init)
├── tests/
│   ├── conftest.py             # Fixtures, mock LLM, temp projects
│   ├── test_file_agent.py
│   ├── test_terminal_agent.py
│   ├── test_repo_intelligence.py
│   └── test_api.py
├── requirements.txt
├── pyproject.toml
├── setup.sh
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
pytest tests/ -v -m "not slow"   # Skip slow tests
pytest tests/test_file_agent.py  # Single file
```

---

## Docker

```bash
# Start everything
docker compose up -d

# View logs
docker compose logs -f backend

# Stop
docker compose down
```

---

## Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| Phase 1 | ✅ | Backend, Agent loop, LLM, File tools, Terminal tools |
| Phase 2 | ✅ | Memory, Git agent, Testing agent, Context engine |
| Phase 3 | 🔄 | Desktop UI (Tauri), Plugins, Multi-agent coordination |

### Planned Plugins
- **Docker** — container management
- **Database** — schema inspection, query generation
- **AWS/Cloud** — infrastructure as code (opt-in, explicit)
- **Kubernetes** — deployment management

---

## Security

- **No cloud upload** by default (`CLOUD_UPLOAD_ENABLED=false`)
- **Local storage** only — all data stays in `~/.localcoder/`
- **Sandbox execution** — commands run in project directory only
- **Permission levels** — explicit approval for destructive operations
- **Path escape prevention** — all file operations validated against project root
- **Command blocking** — dangerous patterns (rm -rf /, fork bombs) blocked at parse time

---

## License

MIT — see LICENSE file.

---

*LocalCoder is not affiliated with OpenAI, Anthropic, or any cloud provider. It is designed to run entirely on your hardware.*
#
