# =============================================================================
# Dockerfile — Reverse Document Generator Flask/Gunicorn Container Build
# =============================================================================
#
# Production container image for the AI-powered Technical Specification
# generator Flask API server. Built on Ubuntu 24.04 with Python 3.12,
# Node.js 20 (MCP/Figma integration), and Chrome (Figma DevTools Protocol).
#
# Adapted from the original Cloud Run Job Dockerfile:
#   - KEY CHANGE: Entrypoint migrated from `python main.py` to Gunicorn WSGI
#   - All system dependencies, security patches, and runtimes preserved
#
# Build:  docker build -t reverse-document-generator .
# Run:    docker run -p 8080:8080 --env-file .env reverse-document-generator
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Base image — Ubuntu 24.04 LTS (Noble Numbat)
# ---------------------------------------------------------------------------
FROM ubuntu:24.04 AS base

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Python environment settings for container optimization
#   PYTHONDONTWRITEBYTECODE=1 — Prevents .pyc files (reduces image size)
#   PYTHONUNBUFFERED=1 — Ensures logs are flushed immediately to stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# ---------------------------------------------------------------------------
# Stage 2: System dependencies and security patches
# ---------------------------------------------------------------------------

# Apply all available security patches first
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get dist-upgrade -y

# Install core system packages required for build and runtime:
#   - python3.12, python3.12-venv, python3-pip: Python 3.12 runtime and package manager
#   - build-essential, python3.12-dev: Compilation toolchain for native Python extensions
#   - curl, wget: HTTP utilities for downloading external resources
#   - git: Version control (required for repository operations and pip git dependencies)
#   - ca-certificates: SSL certificate authorities for HTTPS connections
#   - gnupg: GPG for verifying package signatures (Node.js, Chrome repos)
#   - unzip: Archive extraction utility
#   - libffi-dev, libssl-dev: Foreign function interface and SSL development headers
#   - software-properties-common: Manages additional apt repositories
RUN apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    build-essential \
    curl \
    wget \
    git \
    ca-certificates \
    gnupg \
    unzip \
    libffi-dev \
    libssl-dev \
    software-properties-common && \
    # Set python3.12 as the default python3
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# ---------------------------------------------------------------------------
# Stage 3: Node.js 20 LTS installation (required for MCP/Figma integration)
# ---------------------------------------------------------------------------
# Node.js is required by:
#   - langchain-mcp-adapters (MCP SDK bridge to LangChain agents)
#   - Figma Chrome DevTools Protocol integration
#   - MCP server process management
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    # Verify Node.js installation
    node --version && \
    npm --version

# ---------------------------------------------------------------------------
# Stage 4: Chrome/Chromium installation (required for Figma DevTools Protocol)
# ---------------------------------------------------------------------------
# Chromium is required for the Figma integration via Chrome DevTools Protocol.
# The headless browser enables extraction of design system information from
# Figma files during document generation.
RUN apt-get install -y --no-install-recommends \
    chromium-browser \
    fonts-liberation \
    libappindicator3-1 \
    libasound2t64 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils && \
    # Set Chrome environment variable for Puppeteer/CDP compatibility
    echo "export CHROME_BIN=/usr/bin/chromium-browser" >> /etc/environment

# Environment variable for Chrome binary location
ENV CHROME_BIN=/usr/bin/chromium-browser \
    CHROMIUM_FLAGS="--no-sandbox --headless --disable-gpu --disable-dev-shm-usage"

# ---------------------------------------------------------------------------
# Stage 5: Clean up apt caches to reduce image size
# ---------------------------------------------------------------------------
RUN apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ---------------------------------------------------------------------------
# Stage 6: Application setup
# ---------------------------------------------------------------------------

# Set the working directory for the application
WORKDIR /app

# Copy requirements.txt first for optimal Docker layer caching.
# This ensures that pip install is only re-run when dependencies change,
# not when application code changes.
COPY requirements.txt .

# Install Python dependencies from requirements.txt.
# The requirements.txt includes the private registry URL as the first line:
#   --extra-index-url https://us-east1-python.pkg.dev/blitzy-platform-stage/python-us-east1/simple/
# This resolves blitzy-platform-shared and blitzy-utils from Google Artifact Registry.
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy the entire application source code into the container
COPY . .

# ---------------------------------------------------------------------------
# Stage 7: Security hardening — Non-root user execution
# ---------------------------------------------------------------------------
# Create a dedicated non-root user for running the application.
# This is a critical security measure that:
#   - Prevents container escape attacks from gaining root access
#   - Follows the principle of least privilege
#   - Complies with container security best practices and CIS benchmarks
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser && \
    # Grant the app user ownership of the application directory
    chown -R appuser:appgroup /app

# Switch to the non-root user for all subsequent operations
USER appuser

# ---------------------------------------------------------------------------
# Stage 8: Container configuration and entrypoint
# ---------------------------------------------------------------------------

# Expose the Flask/Gunicorn HTTP port (Cloud Run default)
EXPOSE 8080

# Health check for container orchestration platforms (Cloud Run, Kubernetes).
# Probes the /health endpoint every 30 seconds with a 10-second timeout.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Entrypoint: Launch the Flask application via Gunicorn WSGI server.
#
# KEY CHANGE FROM SOURCE:
#   Original Cloud Run Job:  CMD ["python", "main.py"]
#   New Flask/Gunicorn:      CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
#
# Gunicorn reads its configuration from gunicorn.conf.py which specifies:
#   - Bind address: 0.0.0.0:8080
#   - Worker count, timeouts, logging
#   - Process management settings
# The wsgi:app reference points to the Flask application instance created
# by create_app() in wsgi.py.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
