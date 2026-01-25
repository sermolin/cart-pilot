# =============================================================================
# Builder stage: Install dependencies
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies (if needed for native extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# =============================================================================
# Runtime stage: Minimal production image
# =============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/appuser/.local/bin:$PATH \
    PYTHONPATH=/app \
    TRANSPORT=sse

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose port for SSE transport
EXPOSE 8003

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8003/health', timeout=5).raise_for_status()" || exit 1

# Run the MCP server
# Transport mode is controlled by TRANSPORT env var:
# - 'sse': HTTP/SSE for Docker (default in container)
# - 'stdio': stdin/stdout for local use with AI agents
CMD ["python", "-m", "app.main"]
