# LocalCoder AI Agent — Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY backend/ ./backend/
COPY cli/ ./cli/
COPY pyproject.toml .
COPY .env.example .env

# Install CLI
RUN pip install -e . --no-deps

# Create data directory
RUN mkdir -p /root/.localcoder

EXPOSE 8765

CMD ["python", "-m", "backend"]
