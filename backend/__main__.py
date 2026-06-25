"""Start the LocalCoder API server."""

import uvicorn
from backend.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "backend.api.app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )
