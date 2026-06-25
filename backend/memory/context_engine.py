"""
LocalCoder — Context Engine.
Repository indexer, semantic search, embeddings via ChromaDB or LanceDB.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

import aiofiles

from backend.core.config import VectorStore, settings
from backend.core.llm import get_llm
from backend.core.logging import get_logger

log = get_logger(__name__)

CHUNK_SIZE    = settings.CHUNK_SIZE
CHUNK_OVERLAP = settings.CHUNK_OVERLAP
TOP_K         = settings.TOP_K_RESULTS

INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".swift", ".c", ".cpp", ".h", ".cs", ".html", ".css",
    ".yaml", ".yml", ".json", ".toml", ".md", ".sh", ".sql",
}

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "target",
}


def _chunk_text(text: str, path: str) -> list[dict]:
    """Split text into overlapping chunks."""
    lines = text.splitlines(keepends=True)
    chunks = []
    current, current_len, start_line = [], 0, 1

    for i, line in enumerate(lines, start=1):
        current.append(line)
        current_len += len(line)
        if current_len >= CHUNK_SIZE:
            chunk_text = "".join(current)
            chunks.append({
                "text":       chunk_text,
                "path":       path,
                "start_line": start_line,
                "end_line":   i,
            })
            # overlap
            overlap_lines = current[-max(1, len(current) // 4):]
            current = list(overlap_lines)
            current_len = sum(len(l) for l in current)
            start_line = i - len(current) + 1

    if current:
        chunks.append({
            "text":       "".join(current),
            "path":       path,
            "start_line": start_line,
            "end_line":   start_line + len(current),
        })

    return chunks


class ContextEngine:
    """
    Builds a semantic index over the repository and answers natural-language
    queries with the most relevant code chunks.
    """

    def __init__(self, project_root: str) -> None:
        self.root   = Path(project_root).resolve()
        self.llm    = get_llm()
        self._store = self._init_store()

    def _init_store(self):
        if settings.VECTOR_STORE == VectorStore.CHROMA:
            return self._init_chroma()
        return self._init_lance()

    def _init_chroma(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(settings.VECTOR_DIR / "chroma"))
            col_name = "repo_" + hashlib.md5(str(self.root).encode()).hexdigest()[:8]
            return client.get_or_create_collection(
                name=col_name,
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            log.warning("context.chroma_not_installed")
            return None

    def _init_lance(self):
        try:
            import lancedb
            db = lancedb.connect(str(settings.VECTOR_DIR / "lance"))
            return db
        except ImportError:
            log.warning("context.lancedb_not_installed")
            return None

    def _should_skip(self, path: Path) -> bool:
        return any(part in IGNORE_DIRS for part in path.relative_to(self.root).parts)

    async def index_repo(self, force: bool = False) -> int:
        """Walk repo and index all code files. Returns # chunks indexed."""
        if self._store is None:
            log.warning("context.no_vector_store")
            return 0

        total = 0
        for file_path in self.root.rglob("*"):
            if self._should_skip(file_path):
                continue
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in INDEXABLE_EXTENSIONS:
                continue
            if file_path.stat().st_size > 500_000:
                continue

            try:
                async with aiofiles.open(file_path, encoding="utf-8", errors="ignore") as f:
                    content = await f.read()
            except Exception:
                continue

            rel = str(file_path.relative_to(self.root))
            chunks = _chunk_text(content, rel)

            for chunk in chunks:
                try:
                    embedding = await self.llm.embed(chunk["text"])
                    await self._upsert(chunk, embedding)
                    total += 1
                except Exception as exc:
                    log.debug("context.embed_error", path=rel, error=str(exc))

        log.info("context.indexed", chunks=total, root=str(self.root))
        return total

    async def _upsert(self, chunk: dict, embedding: list[float]) -> None:
        if self._store is None:
            return
        chunk_id = hashlib.md5(
            f"{chunk['path']}:{chunk['start_line']}".encode()
        ).hexdigest()

        # ChromaDB
        if hasattr(self._store, "upsert"):
            self._store.upsert(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk["text"]],
                metadatas=[{"path": chunk["path"], "start": chunk["start_line"]}],
            )

    async def search(self, query: str, top_k: int = TOP_K) -> list[dict]:
        """Semantic search over indexed repository."""
        if self._store is None:
            return []
        try:
            q_embed = await self.llm.embed(query)

            if hasattr(self._store, "query"):   # ChromaDB
                results = self._store.query(
                    query_embeddings=[q_embed],
                    n_results=min(top_k, self._store.count() or 1),
                    include=["documents", "metadatas", "distances"],
                )
                out = []
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    out.append({
                        "text":  doc,
                        "path":  meta.get("path"),
                        "score": 1 - dist,
                    })
                return out
        except Exception as exc:
            log.error("context.search_error", error=str(exc))
        return []

    async def get_relevant_context(self, query: str, max_chars: int = 8000) -> str:
        """Return formatted code context for LLM prompt."""
        results = await self.search(query)
        if not results:
            return ""

        parts = ["Relevant code context from repository:\n"]
        total = 0
        for r in results:
            snippet = f"\n# File: {r['path']}\n{r['text']}\n"
            if total + len(snippet) > max_chars:
                break
            parts.append(snippet)
            total += len(snippet)

        return "".join(parts)
