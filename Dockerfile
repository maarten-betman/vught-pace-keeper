# =============================================================================
# Stage 1: Builder - Install dependencies and build assets
# =============================================================================
FROM python:3.13-slim AS builder

# Install build dependencies for GeoDjango
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Create virtual environment and install production dependencies only
RUN uv venv /opt/venv && \
    uv sync --frozen --no-dev

# Download and setup Tailwind CLI
RUN curl -sL https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 \
    -o /usr/local/bin/tailwindcss && \
    chmod +x /usr/local/bin/tailwindcss

# Copy source code for Tailwind build
COPY src/ ./src/
COPY tailwind.config.js ./

# Build Tailwind CSS
RUN tailwindcss -i src/vught_pace_keeper/static/css/input.css \
    -o src/vught_pace_keeper/static/css/output.css --minify


# =============================================================================
# Stage 2: Production - Minimal runtime image
# =============================================================================
FROM python:3.13-slim AS production

LABEL org.opencontainers.image.title="Vught Pace Keeper"
LABEL org.opencontainers.image.description="Marathon training plan management with Strava integration"

# Install runtime dependencies only (no build tools)
# Using package names from Debian Bookworm (python:3.13-slim base)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal32 \
    libgeos-c1v5 \
    libproj25 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source with built assets
COPY --from=builder /app/src ./src

# Copy manage.py and docker configuration
COPY manage.py ./
COPY docker/entrypoint.sh ./entrypoint.sh
COPY docker/gunicorn.conf.py ./gunicorn.conf.py

# Make entrypoint executable
RUN chmod +x ./entrypoint.sh

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080 \
    DJANGO_SETTINGS_MODULE=vught_pace_keeper.settings

# Collect static files during build (requires dummy settings)
RUN SECRET_KEY=build-time-secret \
    DATABASE_URL=sqlite:///dummy.db \
    DEBUG=False \
    ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

# Create directories and set permissions
RUN mkdir -p /app/staticfiles /app/media && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port (Digital Ocean default is 8080)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health/ || exit 1

# Entrypoint
ENTRYPOINT ["./entrypoint.sh"]

# Default command: Gunicorn
CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "vught_pace_keeper.wsgi:application"]
