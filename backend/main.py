"""
LocalCoder AI Agent - FastAPI Backend
Production-grade local-first AI coding assistant
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.routes import agent, health, projects, git, terminal
from db.database import init_db
from context.indexer import RepositoryIndexer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    logger.info("🚀 LocalCoder Agent starting up...")
    await init_db()
    logger.info("✅ Database initialized")
    yield
    logger.info("🛑 LocalCoder Agent shutting down...")


app = FastAPI(
    title="LocalCoder AI Agent",
    description="Privacy-first autonomous coding assistant running locally",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://localhost:5173", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Register routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(git.router, prefix="/api/git", tags=["git"])
app.include_router(terminal.router, prefix="/api/terminal", tags=["terminal"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
