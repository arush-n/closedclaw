FROM python:3.12-slim

LABEL org.opencontainers.image.name="closedclaw/control-bridge"
LABEL org.opencontainers.image.description="Closedclaw control bridge — mediates openclaw access"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Config is mounted as a volume
VOLUME ["/config", "/data"]

EXPOSE 9000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000", "--log-level", "info"]
