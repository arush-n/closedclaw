FROM python:3.12-slim

LABEL org.opencontainers.image.name="closedclaw/server"
LABEL org.opencontainers.image.description="Closedclaw privacy-first AI memory middleware server"

WORKDIR /app

# Install system deps for cryptography / argon2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy source
COPY src/closedclaw/ /app/src/closedclaw/

# Install the package with all optional deps (ollama, mem0, etc.)
RUN pip install --no-cache-dir \
    "fastapi>=0.109.0" \
    "uvicorn[standard]>=0.27.0" \
    "pydantic>=2.5.0" \
    "pydantic-settings>=2.1.0" \
    "httpx>=0.26.0" \
    "typer[all]>=0.9.0" \
    "rich>=13.7.0" \
    "anyio>=4.2.0" \
    "cryptography>=42.0.0" \
    "argon2-cffi>=23.1.0" \
    "sqlalchemy>=2.0.0" \
    "numpy>=1.24.0" \
    "ollama>=0.1.0" \
    "starlette>=0.36.0"

# Add source to Python path
ENV PYTHONPATH="/app/src"

# Config and data volumes
VOLUME ["/config", "/data"]

# Default closedclaw port
EXPOSE 8765

# Run the server — bind 0.0.0.0 inside Docker
CMD ["uvicorn", "closedclaw.api.app:app", "--host", "0.0.0.0", "--port", "8765", "--log-level", "info"]
