# ================================================================
# Async Research Assistant — Multi-stage Dockerfile (+1 bonus)
# ================================================================

# ---- Build stage ----
FROM python:3.12-slim AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim
LABEL org.opencontainers.image.description="AIENG Final Project — Async Research Assistant"
LABEL org.opencontainers.image.source="https://github.com/emiljafarov3841/async-research-assistant"

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .

# Create non-root user and cache directory
RUN useradd --create-home appuser && \
    mkdir -p /app/.cache /app/artefacts && \
    chown -R appuser /app
USER appuser

# Offline demo as default — override for live mode or CLI usage
CMD ["python", "demo_ai.py", "--offline"]
