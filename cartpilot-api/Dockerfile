# =============================================================================
# Builder stage: Install dependencies and build artifacts
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
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
    PYTHONPATH=/app

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code (before switching user to ensure proper ownership)
COPY --chown=appuser:appuser . .

# Make entrypoint script executable and ensure it's owned by appuser
RUN chmod +x scripts/docker-entrypoint.sh && \
    chown appuser:appuser scripts/docker-entrypoint.sh

# Ensure alembic and other scripts are accessible
RUN chmod +x scripts/*.sh 2>/dev/null || true

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5).raise_for_status()" || exit 1

# Run the application via entrypoint script
ENTRYPOINT ["scripts/docker-entrypoint.sh"]
