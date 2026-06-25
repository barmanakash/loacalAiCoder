#!/usr/bin/env bash
# LocalCoder AI Agent — Setup Script
# Run: bash setup.sh

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║     LocalCoder AI Agent Setup         ║"
echo "  ║     Privacy-First Coding Assistant    ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── Check Prerequisites ───────────────────────────────────────────────────────

info "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || error "Python 3.10+ is required"
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python $PYTHON_VERSION found"

command -v node >/dev/null 2>&1 || warn "Node.js not found — frontend won't build"
command -v npm >/dev/null 2>&1 || warn "npm not found — frontend won't build"

# Check Ollama
if command -v ollama >/dev/null 2>&1; then
    info "Ollama found"
else
    warn "Ollama not found. Install from https://ollama.com"
    warn "After installing, run: ollama pull qwen2.5-coder:7b"
fi

# ── Python Virtual Environment ────────────────────────────────────────────────

if [ ! -d ".venv" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv .venv
fi

info "Activating virtual environment..."
source .venv/bin/activate

info "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ── Environment Config ────────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
    info "Creating .env from template..."
    cp .env.example .env
    warn "Edit .env to configure your LLM settings"
fi

# ── Frontend ──────────────────────────────────────────────────────────────────

if command -v npm >/dev/null 2>&1; then
    info "Installing frontend dependencies..."
    cd frontend
    npm install -q
    cd ..
    info "Frontend dependencies installed"
fi

# ── CLI Install ───────────────────────────────────────────────────────────────

info "Installing LocalCoder CLI..."
pip install -e . -q 2>/dev/null || true

# ── Pull LLM Model ────────────────────────────────────────────────────────────

if command -v ollama >/dev/null 2>&1; then
    info "Pulling default model (qwen2.5-coder:7b)..."
    ollama pull qwen2.5-coder:7b || warn "Model pull failed — run manually: ollama pull qwen2.5-coder:7b"

    info "Pulling embedding model (nomic-embed-text)..."
    ollama pull nomic-embed-text || warn "Embedding model pull failed"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "  ${GREEN}✓ LocalCoder setup complete!${NC}"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Start the backend:"
echo "     source .venv/bin/activate"
echo "     python -m backend"
echo ""
echo "  2. Start the frontend (in another terminal):"
echo "     cd frontend && npm run dev"
echo ""
echo "  3. Or use the CLI:"
echo "     localcoder init ."
echo "     localcoder run \"Fix all failing tests\""
echo "     localcoder chat"
echo ""
echo "  4. Or open http://localhost:5173 in your browser"
echo ""
